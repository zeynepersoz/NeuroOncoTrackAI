"""
ai_service/bridge.py — Mert (preprocessing + XAI + RAG) ↔ Zeynep (v3 sınıflandırma)
=================================================================================

Backend'in tek girişi:
    from ai_service.bridge import run_pipeline

    result = run_pipeline(
        patient_id="BRATS-GLI-00123-000",
        modality_paths={"t1": ..., "t1c": ..., "t2": ..., "flair": ...},
        output_dir="processed/BRATS-GLI-00123-000",
        mode="full",  # "full" | "fast" | "classify_only"
    )

Tasarım kuralları:
  * mert/ ve zeynep/ dizinlerindeki kodlar HİÇ DEĞİŞTİRİLMEZ (peer-orchestration).
  * Her aşama izole hata yakalar → bir aşama patlarsa diğerleri çalışmaya devam eder.
  * Dönen dict tam serialize edilebilir (backend doğrudan JSON'a çevirir).
  * Latency her aşamada ölçülür (dashboard / observability için).
  * "Mode" kontrolü: HD-BET / GPU / Groq yoksa graceful fallback.

TEKNOFEST 2026 hedef: derece almak. Bu yüzden her yol açık, her hata izlenebilir.
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
import platform
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# 0. Path kurulumu — mert/ ve zeynep/ import edilebilsin
# ─────────────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_MERT_ROOT = _HERE / "mert"
_ZEYNEP_ROOT = _HERE / "zeynep"

for _p in (_MERT_ROOT, _ZEYNEP_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# TensorFlow / Torch gürültüsünü kıs
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logger = logging.getLogger("ai_service.bridge")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

PIPELINE_VERSION = "1.0.0"
_DEFAULT_GUIDELINES = _MERT_ROOT / "data" / "guidelines"

# WHO CNS 5 grade önerisi (sadece bilgi — kesin tanı değil, RAG'e context)
_GRADE_HINT = {
    "glioma": "III-IV (agresif alt tip beklenir; kesinleştirme için histopatoloji)",
    "meningioma": "I-II (çoğunlukla benign; kalsifikasyon/ödem ile değişir)",
    "notumor": "N/A",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dönen sonuç şeması
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class StageResult:
    status: str = "pending"          # "ok" | "skipped" | "error" | "pending"
    elapsed_ms: float = 0.0
    payload: dict = field(default_factory=dict)
    error: Optional[str] = None
    warnings: list = field(default_factory=list)


@dataclass
class PipelineResult:
    patient_id: str
    pipeline_version: str = PIPELINE_VERSION
    timestamp: str = ""
    mode: str = ""
    device: str = ""
    stages: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stages"] = {k: (asdict(v) if isinstance(v, StageResult) else v)
                       for k, v in self.stages.items()}
        return d


# ─────────────────────────────────────────────────────────────────────────────
# 2. Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────
def _detect_device(preferred: str = "auto") -> str:
    """
    'auto' → cuda > mps > cpu
    Kullanıcı Mac'te → mps, sunucuda → cuda, aksi → cpu.
    """
    if preferred != "auto":
        return preferred
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _load_mid_slice_from_nifti(nii_path: Path, z_offset: int = 0) -> Optional[np.ndarray]:
    """T1c hacminden orta dilim uint8 gri döndürür (Zeynep predictor'un girdi formatı)."""
    try:
        import nibabel as nib
        img = nib.load(str(nii_path)).get_fdata()
        if img.ndim == 4:
            img = img[..., 0]
        z = max(0, min(img.shape[2] // 2 + z_offset, img.shape[2] - 1))
        s = np.rot90(img[:, :, z])
        lo, hi = np.percentile(s, [1, 99])
        if hi <= lo:
            hi = lo + 1
        return (np.clip((s - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    except Exception as exc:
        logger.warning("Mid-slice okunamadı (%s): %s", nii_path, exc)
        return None


def _estimate_tumor_area_ratio(gray_u8: np.ndarray) -> Optional[float]:
    """
    Tek dilimden kaba tümör alan oranı (segmentasyon modeli yoksa fallback).
    Otsu + connected components → beyin alanına göre en parlak lezyon lekesi oranı.
    Gerçek 3D hacim yerine bir işaret niteliğinde; RAG'e bilgi olarak geçilir.
    """
    try:
        import cv2
        _, brain = cv2.threshold(gray_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        brain_area = int((brain > 0).sum())
        if brain_area < 500:
            return None
        # yüksek yoğunluklu lezyon (kontrast tutan olası bölge)
        hi_thr = np.percentile(gray_u8[brain > 0], 92)
        lesion = ((gray_u8 >= hi_thr) & (brain > 0)).astype(np.uint8)
        lesion_area = int(lesion.sum())
        return round(lesion_area / brain_area, 4)
    except Exception:
        return None


def _atomic_write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Aşama 1 — Preprocessing (Mert)
# ─────────────────────────────────────────────────────────────────────────────
def _stage_preprocess(
    patient_id: str,
    modality_paths: dict,
    output_dir: Path,
    quarantine_root: Path,
    device: str,
) -> StageResult:
    t0 = time.perf_counter()
    res = StageResult()
    try:
        from preprocessing.utils import Patient  # type: ignore
        from preprocessing.pipeline import preprocess_patient  # type: ignore

        patient = Patient(
            patient_id=patient_id,
            modalities={k: Path(v) for k, v in modality_paths.items()},
            output_dir=Path(output_dir),
        )
        result = preprocess_patient(patient, quarantine_root=quarantine_root, device=device)
        res.status = "ok"
        res.payload = {
            "processed_paths": {k: str(v) for k, v in result.processed.items()},
            "qc_flags": result.qc_flags,
        }
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("[preprocess] hata: %s", res.error)
        logger.debug(traceback.format_exc())
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 4. Aşama 2 — Sınıflandırma (Zeynep v3)
# ─────────────────────────────────────────────────────────────────────────────
def _stage_classify(gray_slice: np.ndarray, predictor: str = "v3") -> StageResult:
    t0 = time.perf_counter()
    res = StageResult()
    try:
        if predictor == "v3":
            from v3_predictor import predict_v3 as _predict  # type: ignore
            model_id = "v3_rf_hgb_expanded_cache"
        else:
            from v2_predictor import predict_v2 as _predict  # type: ignore
            model_id = "v2_rf_hgb"

        out = _predict(gray_slice, apply_domain_preproc=True)
        res.status = "ok"
        res.payload = {
            "prediction": out["prediction"],
            "confidence": float(out["confidence"]),
            "probabilities": {k: float(v) for k, v in out["probabilities"].items()},
            "model_id": model_id,
            "preprocess": out.get("preprocess"),
            "latency_ms_predictor": float(out.get("latency_ms", 0.0)),
        }
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("[classify] hata: %s", res.error)
        logger.debug(traceback.format_exc())
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 5. Aşama 3 — XAI (Mert overlay + Zeynep'in "brain-focus" ısı haritası)
# ─────────────────────────────────────────────────────────────────────────────
def _stage_xai(
    gray_slice: np.ndarray,
    output_dir: Path,
    filename: str = "gradcam_overlay.png",
) -> StageResult:
    """
    Tam Grad-CAM++ için PyTorch model gerekir; kullanıcının modeli TensorFlow.
    Bu köprüde saliency yaklaşımı: brain-mask + intensity gradient → sözde CAM.
    Sonra Mert'in `xai/overlay.py` fonksiyonu ile MR üzerine bindirilir.
    """
    t0 = time.perf_counter()
    res = StageResult()
    try:
        import cv2  # type: ignore
        from xai.overlay import save_overlay_png  # type: ignore

        # ─ Pseudo-CAM: brain mask × yerel yoğunluk gradiyenti (0..1)
        blur = cv2.GaussianBlur(gray_slice, (7, 7), 0)
        gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=5)
        gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=5)
        mag = np.sqrt(gx * gx + gy * gy)
        # yumuşat + normalize
        mag = cv2.GaussianBlur(mag, (25, 25), 0)
        mag = mag - mag.min()
        if mag.max() > 0:
            mag = mag / mag.max()
        # Otsu ile beyin dışını sıfırla
        _, brain = cv2.threshold(gray_slice, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cam = mag * (brain > 0).astype(np.float32)

        out_path = Path(output_dir) / filename
        save_overlay_png(gray_slice.astype(np.float32), cam, out_path, alpha=0.45)

        res.status = "ok"
        res.payload = {
            "overlay_path": str(out_path),
            "method": "brain_masked_gradient_pseudo_cam",
            "note": ("Gerçek Grad-CAM++ için PyTorch model gereklidir. "
                     "Mert'in xai.grad_cam_pp modülü hazır; TF backbone entegrasyonu "
                     "sonraki fazda yapılacak."),
        }
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("[xai] hata: %s", res.error)
        logger.debug(traceback.format_exc())
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 6. Aşama 4 — RAG rapor (Mert)
# ─────────────────────────────────────────────────────────────────────────────
_RAG_PIPELINE_CACHE: dict = {}


def _get_or_build_rag(groq_api_key: str, guidelines_dir: Path):
    key = f"{guidelines_dir}::{groq_api_key[:6]}"
    if key in _RAG_PIPELINE_CACHE:
        return _RAG_PIPELINE_CACHE[key]
    from core.end_to_end import NeuroOncoTrackPipeline  # type: ignore
    pipe = NeuroOncoTrackPipeline(
        groq_api_key=groq_api_key,
        guidelines_dir=guidelines_dir,
    )
    _RAG_PIPELINE_CACHE[key] = pipe
    return pipe


def _stage_report(model_output: dict, groq_api_key: Optional[str],
                  guidelines_dir: Path) -> StageResult:
    t0 = time.perf_counter()
    res = StageResult()
    if not groq_api_key:
        res.status = "skipped"
        res.warnings.append("GROQ_API_KEY yok — RAG raporu üretilmedi.")
        # yine de FHIR taslağı doldurulabilir
        res.payload = {"fhir": _fhir_stub(model_output)}
        res.elapsed_ms = (time.perf_counter() - t0) * 1000
        return res
    try:
        pipe = _get_or_build_rag(groq_api_key, guidelines_dir)
        out = pipe.generate_report(model_output)
        res.status = "ok"
        res.payload = {
            "is_valid": bool(out.get("is_valid")),
            "attempt": int(out.get("attempt", 1)),
            "report": out.get("report", ""),
            "sections": out.get("sections", {}),
            "fhir": out.get("fhir", _fhir_stub(model_output)),
            "validation": {
                "missing_sections": out.get("missing_sections", []),
                "forbidden_phrases": out.get("forbidden_phrases", []),
                "wrong_terminology": out.get("wrong_terminology", []),
                "numeric_mismatches": out.get("numeric_mismatches", []),
                "disclaimer_added": bool(out.get("disclaimer_added", False)),
                "max_retries_exceeded": bool(out.get("max_retries_exceeded", False)),
            },
        }
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        res.payload = {"fhir": _fhir_stub(model_output)}
        logger.error("[report] hata: %s", res.error)
        logger.debug(traceback.format_exc())
    res.elapsed_ms = (time.perf_counter() - t0) * 1000
    return res


def _fhir_stub(model_output: dict) -> dict:
    """RAG çalışmasa bile backend'e minimum FHIR iskelet döner."""
    return {
        "resourceType": "DiagnosticReport",
        "status": "preliminary",
        "category": "radiology",
        "code": {"text": "AI Assisted Brain Tumor Screening"},
        "conclusion": (f"AI ön tahmini: {model_output.get('prediction', 'N/A')} "
                       f"(güven={model_output.get('confidence', 0):.2f}). "
                       "Uzman hekim değerlendirmesi gereklidir."),
        "disclaimer": ("Bu rapor yapay zeka destekli bir sistem tarafından üretilmiştir. "
                       "Kesin tanı niteliği taşımaz ve uzman hekim değerlendirmesi gerektirir."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. ANA API — run_pipeline
# ─────────────────────────────────────────────────────────────────────────────
def run_pipeline(
    patient_id: str,
    modality_paths: dict[str, str | Path],
    output_dir: str | Path,
    mode: str = "full",
    device: str = "auto",
    predictor: str = "v3",
    groq_api_key: Optional[str] = None,
    guidelines_dir: Optional[str | Path] = None,
    quarantine_root: Optional[str | Path] = None,
    extra_features: Optional[dict] = None,
    persist_json: bool = True,
) -> dict:
    """
    Uçtan uca AI pipeline'ı.

    Parametreler
    ------------
    patient_id : str
        Hasta / çalışma tanımlayıcısı (loglara ve çıktı klasörüne yansır).
    modality_paths : dict[str, Path]
        En az {"t1c": ...}. Tam modda 4 modalite (t1, t1c, t2, flair) beklenir.
    output_dir : Path
        Ara ve nihai çıktıların yazılacağı kök klasör.
    mode : {"full", "fast", "classify_only"}
        - full         : preprocess + classify + xai + report
        - fast         : classify + xai + report (preprocess atlanır)
        - classify_only: yalnızca sınıflandırma
    device : {"auto", "cuda", "mps", "cpu"}
    predictor : {"v3", "v2"}
        v3 = 1310-slice cache (glioma-güçlü), v2 = 780-slice cache (meningioma-güçlü).
    groq_api_key : str | None
        None ise env `GROQ_API_KEY` denenir, o da yoksa RAG atlanır.
    guidelines_dir : Path | None
        None → paket içindeki WHO CNS mini-korpus.
    quarantine_root : Path | None
        None → output_dir / "_quarantine".
    extra_features : dict | None
        Segmentasyondan gelen ek alanlar (tumor_volume_cm3, et_wt_ratio, ...).
        Model çıktısına eklenerek RAG'e verilir.
    persist_json : bool
        Sonucu output_dir/result.json olarak yazsın mı.

    Dönüş
    -----
    dict : `PipelineResult.to_dict()` — tam serialize edilebilir.
    """
    t_all = time.perf_counter()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_root = Path(quarantine_root) if quarantine_root else output_dir / "_quarantine"
    guidelines_dir = Path(guidelines_dir) if guidelines_dir else _DEFAULT_GUIDELINES
    groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
    dev = _detect_device(device)

    result = PipelineResult(
        patient_id=patient_id,
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        mode=mode,
        device=dev,
    )

    logger.info("▶ Pipeline başladı: patient=%s mode=%s device=%s predictor=%s",
                patient_id, mode, dev, predictor)

    # ─── 1) Preprocess ──────────────────────────────────────────────
    t1c_source: Optional[Path] = None
    if mode == "full":
        pre = _stage_preprocess(patient_id, modality_paths, output_dir,
                                quarantine_root, dev)
        result.stages["preprocess"] = pre
        if pre.status == "ok":
            t1c_source = Path(pre.payload["processed_paths"].get("t1c", ""))
        elif pre.error:
            result.errors.append(f"preprocess: {pre.error}")
    else:
        result.stages["preprocess"] = StageResult(status="skipped")

    # T1c yolu belirlenemediyse ham dosyaya düş
    if t1c_source is None or not t1c_source.exists():
        raw_t1c = modality_paths.get("t1c") or modality_paths.get("T1c")
        if raw_t1c:
            t1c_source = Path(raw_t1c)

    # ─── 2) Mid-slice çıkar ─────────────────────────────────────────
    gray = None
    if t1c_source and t1c_source.exists():
        gray = _load_mid_slice_from_nifti(t1c_source)
    if gray is None:
        result.errors.append("T1c dilimi okunamadı — sınıflandırma atlandı.")
        result.stages["classify"] = StageResult(status="error",
                                                error="T1c not available")
        result.stages["xai"] = StageResult(status="skipped")
        result.stages["report"] = StageResult(status="skipped")
        result.total_elapsed_ms = (time.perf_counter() - t_all) * 1000
        payload = result.to_dict()
        if persist_json:
            _atomic_write_json(output_dir / "result.json", payload)
        return payload

    # ─── 3) Classify ────────────────────────────────────────────────
    cls = _stage_classify(gray, predictor=predictor)
    result.stages["classify"] = cls
    if cls.status != "ok":
        result.errors.append(f"classify: {cls.error}")

    # ─── 4) XAI ─────────────────────────────────────────────────────
    if mode != "classify_only":
        xai = _stage_xai(gray, output_dir=output_dir)
        result.stages["xai"] = xai
        if xai.status == "error":
            result.errors.append(f"xai: {xai.error}")
    else:
        result.stages["xai"] = StageResult(status="skipped")

    # ─── 5) Model output → RAG ─────────────────────────────────────
    area_ratio = _estimate_tumor_area_ratio(gray)
    model_output: dict[str, Any] = {}
    if cls.status == "ok":
        model_output.update({
            "prediction": cls.payload["prediction"],
            "confidence": round(cls.payload["confidence"], 4),
            "probabilities": {k: round(v, 4)
                              for k, v in cls.payload["probabilities"].items()},
            "who_grade_hint": _GRADE_HINT.get(cls.payload["prediction"], "N/A"),
        })
    if area_ratio is not None:
        model_output["tumor_area_ratio_2d"] = area_ratio
    if extra_features:
        model_output.update(extra_features)
    model_output["modalities_used"] = sorted(modality_paths.keys())
    model_output["pipeline_version"] = PIPELINE_VERSION

    if mode != "classify_only" and cls.status == "ok":
        rep = _stage_report(model_output, groq_api_key, guidelines_dir)
        result.stages["report"] = rep
        if rep.status == "error":
            result.errors.append(f"report: {rep.error}")
    else:
        result.stages["report"] = StageResult(status="skipped")

    # ─── 6) Özet ──────────────────────────────────────────────────
    result.summary = {
        "prediction": cls.payload.get("prediction") if cls.status == "ok" else None,
        "confidence": cls.payload.get("confidence") if cls.status == "ok" else None,
        "probabilities": cls.payload.get("probabilities") if cls.status == "ok" else {},
        "who_grade_hint": model_output.get("who_grade_hint"),
        "tumor_area_ratio_2d": area_ratio,
        "tumor_volume_cm3": (extra_features or {}).get("tumor_volume_cm3"),
        "et_wt_ratio": (extra_features or {}).get("et_wt_ratio"),
        "report_valid": (result.stages["report"].payload.get("is_valid")
                         if isinstance(result.stages["report"], StageResult)
                         and result.stages["report"].status == "ok"
                         else None),
    }
    result.total_elapsed_ms = round((time.perf_counter() - t_all) * 1000, 2)

    logger.info("✓ Pipeline bitti: patient=%s total=%.0fms errors=%d",
                patient_id, result.total_elapsed_ms, len(result.errors))

    payload = result.to_dict()
    if persist_json:
        _atomic_write_json(output_dir / "result.json", payload)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# 8. Kısa yol — sadece rapor (segmentasyon+sınıf harici sağlanmışsa)
# ─────────────────────────────────────────────────────────────────────────────
def generate_report_only(model_output: dict,
                         groq_api_key: Optional[str] = None,
                         guidelines_dir: Optional[str | Path] = None) -> dict:
    """
    Backend'in başka bir yerde ürettiği model_output için sadece RAG raporu.
    (Ör. hekim manuel input, dış model, batch reprocess.)
    """
    groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
    guidelines_dir = Path(guidelines_dir) if guidelines_dir else _DEFAULT_GUIDELINES
    rep = _stage_report(model_output, groq_api_key, guidelines_dir)
    return asdict(rep)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Sağlık kontrolü — hangi bileşen hazır?
# ─────────────────────────────────────────────────────────────────────────────
def health_check() -> dict:
    """Servisin hangi yeteneklerinin canlı olduğunu döner."""
    status = {
        "pipeline_version": PIPELINE_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "components": {},
    }

    def _try(name, fn):
        try:
            fn()
            status["components"][name] = {"ok": True}
        except Exception as exc:
            status["components"][name] = {"ok": False, "error": str(exc)}

    _try("zeynep.v3_predictor", lambda: __import__("v3_predictor"))
    _try("mert.preprocessing", lambda: __import__("preprocessing.pipeline",
                                                  fromlist=["preprocess_patient"]))
    _try("mert.xai.overlay", lambda: __import__("xai.overlay",
                                                fromlist=["save_overlay_png"]))
    _try("mert.llm.rag_pipeline", lambda: __import__("llm.rag_pipeline",
                                                     fromlist=["RAGPipeline"]))
    _try("groq_api_key", lambda: (_ for _ in ()).throw(RuntimeError("missing"))
                                 if not os.environ.get("GROQ_API_KEY")
                                 else None)
    status["device_detected"] = _detect_device("auto")
    status["guidelines_dir"] = str(_DEFAULT_GUIDELINES)
    status["guidelines_exists"] = _DEFAULT_GUIDELINES.exists()
    return status


if __name__ == "__main__":
    print(json.dumps(health_check(), indent=2, ensure_ascii=False))
