"""
app/api/ai_gateway.py — Backend ↔ AI servisleri köprüsü (AI uçları TEK YERDE)
================================================================================
Backend'e AI için eklenen tüm uçlar burada toplanır (kök /api/analyze,
/api/library, /api/report). Ağır iş AI servislerinde; burada model yok.
- 2D referans vakalar (jpg) → :8100 /classify + /report; görüntü images.original.
- 3D referans vakalar (NIfTI) → pod GPU /segment_viz (tünel :8200) → gerçek hacim +
  kesit + tümör overlay.
Not: Yusufcan'ın /api/v1 klinik router'ları olgunlaşınca bu uçlar oraya taşınabilir;
şimdilik entegre demo için tek gateway dosyası.

Env:
    AI_SERVICE_URL   (vars. http://127.0.0.1:8100)  — sınıflandırma + rapor
    AI_SEG_URL       (vars. http://127.0.0.1:8200)  — pod 3D segmentasyon (SSH tüneli)
    NEURO_DEMO_DIR   (vars. .../test_vakalari/goruntuler)
"""
from __future__ import annotations

import base64
import gzip
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile

router = APIRouter(tags=["legacy-ai (yerel test)"])

AI_BASE = os.environ.get("AI_SERVICE_URL", "http://127.0.0.1:8100")
SEG_BASE = os.environ.get("AI_SEG_URL", "http://127.0.0.1:8200")
DEMO_DIR = Path(os.environ.get(
    "NEURO_DEMO_DIR", "/Users/zeynepersoz/NeuroOncoTrack/test_vakalari/goruntuler"))

# 3D referans vakalar (BraTS-MEN-RT T1c NIfTI — hepsi menenjiyom GTV)
_A3 = "/Users/zeynepersoz/Downloads/archive-3"
THREE_D_CASES = {
    "3D_MEN_0402": f"{_A3}/BraTS-MEN-RT-0402-1/BraTS-MEN-RT-0402-1/BraTS-MEN-RT-0402-1_t1c.nii",
    "3D_MEN_0183": f"{_A3}/BraTS2024-MEN-RT-ValidationData/BraTS-MEN-RT-Val-v1/BraTS-MEN-RT-0183-1/BraTS-MEN-RT-0183-1_t1c.nii",
    "3D_MEN_0697": f"{_A3}/BraTS2024-MEN-RT-ValidationData/BraTS-MEN-RT-Val-v1/BraTS-MEN-RT-0697-1/BraTS-MEN-RT-0697-1_t1c.nii",
}

_TR = {"glioma": "Gliom", "meningioma": "Menenjiyom",
       "notumor": "Tümör Yok", "pituitary": "Hipofiz"}
_TR2EN = {v.lower(): k for k, v in _TR.items()}
_TR2EN.update({"gliom": "glioma", "menenjiyom": "meningioma",
               "hipofiz": "pituitary", "tümör yok": "notumor", "tumor yok": "notumor"})


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _resolve_library_path(library_id: str) -> Path:
    name = os.path.basename(library_id or "")
    p = (DEMO_DIR / name).resolve()
    if DEMO_DIR.resolve() not in p.parents or not p.exists():
        raise HTTPException(status_code=404, detail="library image bulunamadı.")
    return p


@router.get("/api/library")
async def case_library():
    """Vaka kütüphanesi (dizi) — 2D jpg demo vakaları + 3D NIfTI referans vakaları."""
    items = []
    if DEMO_DIR.exists():
        for p in sorted(DEMO_DIR.glob("*.jpg")) + sorted(DEMO_DIR.glob("*.png")):
            items.append({"id": p.name, "name": p.stem.replace("_", " "),
                          "description": p.stem, "modality": "MR"})
    # 3D referans vakalar (yalnız dosya mevcutsa)
    labels = {"3D_MEN_0402": "3D Menenjiyom · BraTS 0402",
              "3D_MEN_0183": "3D Menenjiyom · BraTS 0183",
              "3D_MEN_0697": "3D Menenjiyom · BraTS 0697"}
    for cid, path in THREE_D_CASES.items():
        if os.path.exists(path):
            items.append({"id": cid, "name": labels.get(cid, cid),
                          "description": "BraTS-MEN-RT T1c · 3D nnU-Net (GPU)",
                          "modality": "MR 3D", "is_3d": True})
    return items


async def _classify_bytes(data: bytes, filename: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{AI_BASE}/classify",
                              files={"file": (filename or "image.jpg", data, "application/octet-stream")})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"AI /classify hatası: {r.text[:200]}")
    return r.json()


async def _segment_viz(nii_bytes: bytes, name: str) -> dict:
    """Pod GPU 3D segmentasyon (tünel :8200) → hacim + kesit görselleri."""
    gz = gzip.compress(nii_bytes)
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(f"{SEG_BASE}/segment_viz",
                              files={"file": (name + ".gz", gz, "application/gzip")})
    if r.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"3D segmentasyon hatası ({r.status_code}). Pod/tünel açık mı? {r.text[:150]}")
    return r.json()


async def _report(model_output: dict) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{AI_BASE}/report", json={"model_output": model_output})
    return r.json() if r.status_code == 200 else {}


def _legacy_shape(classification: dict, report: dict, image_name: str,
                  images: dict | None = None) -> dict:
    payload = (report or {}).get("payload", {}) if isinstance(report, dict) else {}
    conf = classification.get("confidence")
    conf_pct = round(conf * 100, 2) if isinstance(conf, (int, float)) else conf
    probs_pct = {k: round(v * 100, 2) for k, v in
                 (classification.get("probabilities") or {}).items()}
    return {
        "prediction": classification.get("prediction"),
        "diagnosis_tr": classification.get("prediction_tr"),
        "confidence": conf_pct,
        "probs": probs_pct,
        "model_id": classification.get("model_id"),
        "volume": None, "tumor_volume_cm3": None,
        "features": {}, "molecular": {},
        "report": payload.get("report"), "sections": payload.get("sections", {}),
        "is_valid": payload.get("is_valid"), "dual_llm": payload.get("dual_llm"),
        "fhir": payload.get("fhir", {}),
        "images": images or {},
        "image_name": image_name,
        "note": "2D demo görüntüsü — hacim (cm³) yalnızca 3D NIfTI vakasında hesaplanır.",
    }


@router.post("/api/analyze")
async def analyze(file: UploadFile | None = File(default=None),
                  library_id: str | None = Form(default=None)):
    """2D jpg (file/library) → sınıflandırma + rapor + görüntü.
    3D referans vakası (library_id ∈ THREE_D_CASES) → pod GPU segmentasyon + hacim + overlay."""

    # ── 3D referans vakası ──────────────────────────────────────────────
    if library_id in THREE_D_CASES:
        path = THREE_D_CASES[library_id]
        if not os.path.exists(path):
            raise HTTPException(404, "3D vaka dosyası bulunamadı.")
        with open(path, "rb") as f:
            nii = f.read()
        viz = await _segment_viz(nii, os.path.basename(path))
        vol = viz.get("volume_cm3")
        model_output = {"prediction": "meningioma", "prediction_tr": "Menenjiyom",
                        "tumor_volume_cm3": vol}
        report = await _report(model_output)
        payload = (report or {}).get("payload", {})
        return {
            "prediction": "meningioma", "diagnosis_tr": "Menenjiyom (GTV)",
            "confidence": None, "probs": {},
            "model_id": viz.get("engine", "nnunet_3d_fullres"),
            "volume": vol, "tumor_volume_cm3": vol,
            "features": {"tumor_voxels": viz.get("tumor_voxels"),
                         "num_tumor_slices": viz.get("num_tumor_slices")},
            "molecular": {},
            "report": payload.get("report"), "sections": payload.get("sections", {}),
            "is_valid": payload.get("is_valid"), "dual_llm": payload.get("dual_llm"),
            "fhir": payload.get("fhir", {}),
            "images": viz.get("images", {}),
            "image_name": os.path.basename(path),
            "note": f"3D nnU-Net segmentasyonu (GPU) — gerçek tümör hacmi {vol} cm³.",
        }

    # ── 2D jpg ──────────────────────────────────────────────────────────
    if file is not None:
        data = await file.read()
        name = file.filename or "upload.jpg"
    elif library_id:
        p = _resolve_library_path(library_id)
        data = p.read_bytes()
        name = p.name
    else:
        raise HTTPException(status_code=400, detail="file veya library_id gerekli.")

    classification = await _classify_bytes(data, name)
    model_output = {"prediction": classification.get("prediction"),
                    "prediction_tr": classification.get("prediction_tr"),
                    "confidence": classification.get("confidence"),
                    "probabilities": classification.get("probabilities", {})}
    report = await _report(model_output)
    # görüntüyü çalışma alanında göster. 2D sınıflandırmada segmentasyon maskesi yok;
    # overlay/normalized'ı da orijinalle doldur ki viewer (varsayılan Overlay modu) MRI'yı göstersin.
    b = _b64(data)
    images = {"original": b, "overlay": b, "normalized": b}
    return _legacy_shape(classification, report, name, images=images)


@router.post("/api/report")
async def legacy_report(body: dict = Body(default={})):
    tr = (body.get("tumor_type") or "").strip().lower()
    pred = _TR2EN.get(tr, body.get("prediction") or "glioma")
    model_output = {"prediction": pred,
                    "prediction_tr": _TR.get(pred, body.get("tumor_type") or pred),
                    "tumor_volume_cm3": body.get("tumor_volume_cm3") or body.get("volume")}
    if body.get("et_wt_ratio"):
        model_output["et_wt_ratio"] = body["et_wt_ratio"]
    report = await _report(model_output)
    payload = (report or {}).get("payload", {}) if isinstance(report, dict) else {}
    return {"report": payload.get("report", ""), "sections": payload.get("sections", {}),
            "fhir": payload.get("fhir", {}), "dual_llm": payload.get("dual_llm"),
            "is_valid": payload.get("is_valid")}
