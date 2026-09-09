"""
ai_service/serve.py — FastAPI mikroservis (backend'in çağıracağı iç servis)
============================================================================

Backend planındaki `/ai/*` endpoint'leri buraya HTTP proxy'ler; backend planı
değişmez. Bu servis içeride Zeynep + Mert modüllerini `bridge.run_pipeline`
üzerinden orkestre eder.

Çalıştırma:
    cd NeuroOncoTrack
    uvicorn ai_service.serve:app --host 0.0.0.0 --port 8100 --reload

Endpoint'ler:
    GET  /health                → bileşen durumu
    POST /infer                 → tam pipeline (JSON: patient_id, modality_paths, mode…)
    POST /report                → sadece rapor (JSON: model_output)
    GET  /info                  → versiyon + registry
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, File, UploadFile
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "FastAPI/Pydantic gerekli: pip install fastapi 'uvicorn[standard]' pydantic"
    ) from exc

from .bridge import (
    PIPELINE_VERSION,
    generate_report_only,
    health_check,
    run_pipeline,
)

app = FastAPI(
    title="NeuroOncoTrack-AI Service",
    version=PIPELINE_VERSION,
    description=(
        "Mert (preprocessing + XAI + RAG) ↔ Zeynep (v3 sınıflandırma) "
        "birleşik AI servisi. Backend bu servisi HTTP üzerinden çağırır."
    ),
)


# ─── Startup warm-up ─────────────────────────────────────────────────────────
# TF backbone (MobileNetV2) + RF/HGB pkl yüklemesi ilk /infer çağrısında
# ~3 saniye sürüyor. Sunucu başlatılırken dummy tahmin yaparak bu maliyeti
# önden ödüyoruz → sonraki çağrılar ~100 ms.
# Devre dışı bırakmak için: AI_SERVICE_SKIP_WARMUP=1
@app.on_event("startup")
async def _warmup_on_startup() -> None:
    if os.environ.get("AI_SERVICE_SKIP_WARMUP") == "1":
        return
    try:
        from .warmup import warm_v3
        stats = warm_v3()
        print(
            f"[serve] warm-up ok: cold={stats['first_predict_ms']}ms "
            f"warm={stats['second_predict_ms']}ms"
        )
    except Exception as exc:  # pragma: no cover
        print(f"[serve] warm-up başarısız (kritik değil): {exc}")


# ─── Şemalar ────────────────────────────────────────────────────────────────
class InferRequest(BaseModel):
    patient_id: str = Field(..., examples=["BRATS-GLI-00123-000"])
    modality_paths: dict[str, str] = Field(
        ..., description="Anahtarlar: t1, t1c, t2, flair (en az t1c zorunlu).",
    )
    output_dir: str = Field(..., description="Ara ve nihai çıktı kök klasörü.")
    mode: str = Field("full", description='"full" | "fast" | "classify_only"')
    device: str = Field("auto", description='"auto" | "cuda" | "mps" | "cpu"')
    predictor: str = Field("v3", description='"v3" | "v2"')
    groq_api_key: Optional[str] = Field(None, description="Yoksa env değişkenine düşer.")
    guidelines_dir: Optional[str] = None
    quarantine_root: Optional[str] = None
    extra_features: Optional[dict] = Field(
        None,
        description="Örn: {'tumor_volume_cm3': 45.2, 'et_wt_ratio': 0.42}",
    )


class ReportRequest(BaseModel):
    model_output: dict = Field(..., description="Sınıf + hacim + ek metrikler.")
    groq_api_key: Optional[str] = None
    guidelines_dir: Optional[str] = None


# ─── Endpoint'ler ───────────────────────────────────────────────────────────
@app.get("/health")
def _health():
    return health_check()


@app.get("/info")
def _info():
    return {
        "service": "NeuroOncoTrack-AI",
        "version": PIPELINE_VERSION,
        "supported_modes": ["full", "fast", "classify_only"],
        "supported_predictors": ["v3", "v2"],
        "supported_devices": ["auto", "cuda", "mps", "cpu"],
        "notes": (
            "v3 = 1310-slice cache (glioma-güçlü). "
            "v2 = 780-slice cache (meningioma-güçlü). "
            "full mode 4 modaliteli NIfTI ve HD-BET gerektirir."
        ),
    }


@app.post("/infer")
def _infer(req: InferRequest):
    if "t1c" not in {k.lower() for k in req.modality_paths.keys()}:
        raise HTTPException(status_code=400, detail="En az t1c modalitesi zorunlu.")
    try:
        return run_pipeline(
            patient_id=req.patient_id,
            modality_paths=req.modality_paths,
            output_dir=req.output_dir,
            mode=req.mode,
            device=req.device,
            predictor=req.predictor,
            groq_api_key=req.groq_api_key,
            guidelines_dir=req.guidelines_dir,
            quarantine_root=req.quarantine_root,
            extra_features=req.extra_features,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"pipeline_error: {exc}")


@app.post("/report")
def _report(req: ReportRequest):
    try:
        # LLM-A: RAG taslağı (gpt-oss-120b)
        draft = generate_report_only(
            model_output=req.model_output,
            groq_api_key=req.groq_api_key,
            guidelines_dir=req.guidelines_dir,
        )
        # LLM-B: bağımsız ikinci görüş / doğrulama (gpt-oss-20b) — env ile kapatılabilir
        if os.environ.get("DUAL_LLM", "1") != "0":
            try:
                try:
                    from report_dual import add_second_opinion  # zeynep/ sys.path'te (bridge ekler)
                except ModuleNotFoundError:
                    from zeynep.report_dual import add_second_opinion
                draft = add_second_opinion(
                    model_output=req.model_output,
                    draft_payload=draft,
                    groq_api_key=req.groq_api_key,
                )
            except Exception as exc:  # ikinci görüş kritik değil; taslağı bozma
                print(f"[serve] dual-LLM ikinci görüş atlandı: {exc}")
        return draft
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"report_error: {exc}")


# TR etiketleri (4-sınıf Kaggle sınıflandırıcı)
_CLASS_TR = {
    "glioma": "Gliom", "meningioma": "Menenjiyom",
    "notumor": "Tümör Yok", "pituitary": "Hipofiz",
}


@app.post("/classify")
async def _classify(file: UploadFile = File(...)):
    """2D beyin MR görüntüsü (jpg/png) → 4-sınıf tahmin.

    /infer NIfTI (3D BraTS) bekler; bu endpoint tek dilim 2D görüntü için.
    """
    import numpy as np
    import cv2
    from v3_predictor import predict_v3  # zeynep/ sys.path'te (bridge ekler)

    data = await file.read()
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(status_code=400, detail="Görüntü çözülemedi.")
    try:
        r = predict_v3(arr)
        pred = r["prediction"]
        return {
            "prediction": pred,
            "prediction_tr": _CLASS_TR.get(pred, pred),
            "confidence": r.get("confidence", max(r["probabilities"].values())),
            "probabilities": r["probabilities"],
            "model_id": r.get("model_id", "v3_rf_hgb_kaggle4"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"classify_error: {exc}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("AI_SERVICE_PORT", "8100"))
    uvicorn.run(app, host="0.0.0.0", port=port)
