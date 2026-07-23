"""
ai_service/smoke_test.py — BraTS-GLI verisi ile bridge smoke test
=================================================================

Amaç: Gerçek BraTS-GLI hastası üzerinde bridge.run_pipeline'ı çalıştırıp
her aşamanın çıktısını göstermek. Mert'in preprocess dosya isimlerine
(t1/t1c/t2/flair) BraTS naming'i (t1n/t1c/t2w/t2f) map edilir.

Kullanım:
    python3 ai_service/smoke_test.py
    python3 ai_service/smoke_test.py --patient BraTS-GLI-00005-100 --mode fast
    python3 ai_service/smoke_test.py --mode classify_only
    python3 ai_service/smoke_test.py --health

TF (v3_predictor) Python 3.14'te kurulamıyor — o zaman classify hata verir,
ama diğer aşamalar bilgi verir. TF hazır olduğunda pipeline sonuna kadar çalışır.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# BraTS → Mert modality-name mapping
BRATS_TO_MERT = {
    "t1n": "t1",
    "t1c": "t1c",
    "t2w": "t2",
    "t2f": "flair",
}

DEFAULT_TRAIN_DIR = Path(
    "/Users/zeynepersoz/NeuroOncoTrack/nnUNet_raw/"
    "Dataset001_NeuroOncoTrack/BraTS-GLI/train"
)


def find_brats_case(patient_id: str, train_dir: Path = DEFAULT_TRAIN_DIR) -> dict:
    """
    BraTS-GLI-XXXXX-YYY klasöründeki 4 modaliteyi Mert isimlerine map eder.
    Segmentation (seg) dosyası ayrı döner (extra_features için).
    """
    case_dir = train_dir / patient_id
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Vaka klasörü yok: {case_dir}")

    modality_paths: dict = {}
    seg_path: Path | None = None
    for f in sorted(case_dir.glob("*.nii.gz")):
        stem = f.name.replace(".nii.gz", "")
        # ör: "BraTS-GLI-00005-100-t1c" → "t1c"
        tag = stem.rsplit("-", 1)[-1]
        if tag == "seg":
            seg_path = f
        elif tag in BRATS_TO_MERT:
            modality_paths[BRATS_TO_MERT[tag]] = f

    missing = [m for m in ("t1", "t1c", "t2", "flair") if m not in modality_paths]
    if missing:
        raise RuntimeError(f"{patient_id}: eksik modaliteler {missing}")

    return {"modality_paths": modality_paths, "seg_path": seg_path}


def list_available_cases(train_dir: Path = DEFAULT_TRAIN_DIR) -> list[str]:
    if not train_dir.is_dir():
        return []
    complete = []
    for d in sorted(train_dir.iterdir()):
        if not d.is_dir():
            continue
        tags = {f.name.rsplit("-", 1)[-1].replace(".nii.gz", "")
                for f in d.glob("*.nii.gz")}
        if {"t1n", "t1c", "t2w", "t2f"}.issubset(tags):
            complete.append(d.name)
    return complete


def _tumor_extra_from_seg(seg_path: Path | None) -> dict:
    """Seg maskesinden hızlı ET/WT özellikleri (RAG'e context)."""
    if seg_path is None or not seg_path.exists():
        return {}
    try:
        import nibabel as nib
        import numpy as np
        seg = nib.load(str(seg_path)).get_fdata().astype(np.int32)
        # BraTS etiketleri: 1=NCR, 2=ED, 3=ET (yeni) / 4=ET (eski)
        et = int(((seg == 3) | (seg == 4)).sum())
        wt = int((seg > 0).sum())
        nz_vox = int(seg.size)
        # Voxel boyutunu affine'den al
        hdr = nib.load(str(seg_path)).header
        vx, vy, vz = hdr.get_zooms()[:3]
        vox_ml = float(vx * vy * vz) / 1000.0  # mm³ → cm³
        return {
            "tumor_volume_cm3": round(wt * vox_ml, 2),
            "et_volume_cm3": round(et * vox_ml, 2),
            "et_wt_ratio": round(et / wt, 4) if wt > 0 else 0.0,
            "seg_source": "BraTS ground-truth",
        }
    except Exception as exc:
        return {"seg_error": str(exc)}


def run_smoke(patient_id: str, mode: str, out_root: Path) -> dict:
    from bridge import run_pipeline  # bridge is in the same dir

    case = find_brats_case(patient_id)
    extras = _tumor_extra_from_seg(case["seg_path"])
    out_dir = out_root / patient_id

    print(f"→ Vaka: {patient_id}")
    print(f"  Modaliteler: {list(case['modality_paths'].keys())}")
    if extras:
        print(f"  Seg özellikleri: {extras}")
    print(f"  Çıktı: {out_dir}")
    print(f"  Mode: {mode}")
    print("─" * 60)

    result = run_pipeline(
        patient_id=patient_id,
        modality_paths=case["modality_paths"],
        output_dir=out_dir,
        mode=mode,
        device="auto",
        predictor="v3",
        extra_features=extras or None,
        persist_json=True,
    )
    return result


def print_result(result: dict) -> None:
    print("─" * 60)
    print(f"Pipeline: {result['pipeline_version']}  device={result['device']}")
    print(f"Toplam süre: {result['total_elapsed_ms']:.0f} ms")
    print()
    for name, stage in result["stages"].items():
        status = stage["status"]
        ms = stage["elapsed_ms"]
        marker = {"ok": "✓", "skipped": "○", "error": "✗", "pending": "?"}.get(status, "?")
        line = f"  {marker} {name:<11} {status:<8} {ms:>7.0f} ms"
        if stage.get("error"):
            line += f"  ← {stage['error']}"
        if stage.get("warnings"):
            line += f"  ⚠ {', '.join(stage['warnings'])}"
        print(line)

    print()
    print("Özet:")
    for k, v in result["summary"].items():
        print(f"  {k}: {v}")

    if result["errors"]:
        print()
        print("Hatalar:")
        for e in result["errors"]:
            print(f"  ! {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", default=None,
                    help="BraTS-GLI-XXXXX-YYY (varsayılan: ilk tam vaka)")
    ap.add_argument("--mode", default="fast",
                    choices=["full", "fast", "classify_only"])
    ap.add_argument("--out", default="/Users/zeynepersoz/NeuroOncoTrack/ai_service/_test_out")
    ap.add_argument("--health", action="store_true", help="Sadece health_check bas")
    ap.add_argument("--list", action="store_true", help="Mevcut vakaları listele")
    args = ap.parse_args()

    if args.health:
        from bridge import health_check
        print(json.dumps(health_check(), indent=2, ensure_ascii=False))
        return 0

    if args.list:
        cases = list_available_cases()
        print(f"Tam ({len(cases)}) vaka bulundu:")
        for c in cases[:20]:
            print(f"  {c}")
        if len(cases) > 20:
            print(f"  ... +{len(cases)-20} daha")
        return 0

    if args.patient is None:
        cases = list_available_cases()
        if not cases:
            print("HATA: BraTS-GLI dizininde tam vaka bulunamadı.")
            return 1
        args.patient = cases[0]
        print(f"(otomatik seçildi: {args.patient})")

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    result = run_smoke(args.patient, args.mode, out_root)
    print_result(result)
    print()
    print(f"JSON çıktı: {out_root / args.patient / 'result.json'}")
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
