"""
zeynep/classify_viz.py — 2D sınıflandırma + görselleştirmeler (ön işleme + XAI)
================================================================================
Referans/2D vakalarda çalışma alanındaki sekmeler boş kalmasın diye:
  - Ön işleme adımları (original / stripped / corrected / normalized) — GERÇEK cv2
    boru hattı (Otsu beyin maskesi → CLAHE → normalize).
  - Açıklanabilirlik: occlusion saliency ısı haritası (model-agnostik; predict_v3'ü
    ızgara halinde tıkayıp tahmin düşüşünü ölçer — TF+RF/HGB için Grad-CAM alternatifi).

Dış API:
  classify_with_viz(bgr) -> {prediction, prediction_tr, confidence, probabilities,
                             model_id, images:{original,stripped,corrected,normalized,gradcam}}
"""
from __future__ import annotations

import base64
import io

import numpy as np

_CLASS_TR = {"glioma": "Gliom", "meningioma": "Menenjiyom",
             "notumor": "Tümör Yok", "pituitary": "Hipofiz"}


def _jpeg_b64(rgb_or_gray: np.ndarray) -> str:
    import cv2
    arr = rgb_or_gray
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    ok, buf = cv2.imencode(".jpg", arr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return base64.b64encode(buf.tobytes()).decode() if ok else ""


def _preprocess_steps(bgr: np.ndarray):
    """original(bgr) → gray → Otsu beyin maskesi(stripped) → CLAHE(corrected) → normalize."""
    import cv2
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Otsu ile beyin/arka plan ayrımı + en büyük bileşen → skull-strip yaklaşımı
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(th, connectivity=8)
    mask = np.zeros_like(gray)
    if n > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask[lbl == largest] = 255
    else:
        mask[:] = 255
    stripped = cv2.bitwise_and(gray, gray, mask=mask)
    # CLAHE (kontrast dengeleme — bias-correction analoğu)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    corrected = clahe.apply(stripped)
    # Normalize (model girdisi ölçeği) → görselleştirme
    norm = cv2.normalize(corrected, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    norm = cv2.resize(norm, (224, 224), interpolation=cv2.INTER_AREA)
    return {"original": _jpeg_b64(bgr), "stripped": _jpeg_b64(stripped),
            "corrected": _jpeg_b64(corrected), "normalized": _jpeg_b64(norm)}


def _occlusion_saliency(bgr: np.ndarray, pred_idx: int, base_prob: float,
                        grid: int = 6) -> str:
    """Izgara halinde tıkayıp tahmin edilen sınıfın olasılık düşüşünü ölç → ısı haritası."""
    import cv2
    from v3_predictor import predict_v3
    h, w = bgr.shape[:2]
    gh, gw = max(1, h // grid), max(1, w // grid)
    fill = int(bgr.mean())
    heat = np.zeros((grid, grid), dtype=np.float32)
    for i in range(grid):
        for j in range(grid):
            occ = bgr.copy()
            occ[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw] = fill
            try:
                p = predict_v3(occ)["probabilities"]
                occ_prob = list(p.values())[pred_idx]
            except Exception:
                occ_prob = base_prob
            heat[i, j] = max(0.0, base_prob - occ_prob)  # düşüş = önem
    if heat.max() > 1e-6:
        heat = heat / heat.max()
    heat_img = cv2.resize((heat * 255).astype(np.uint8), (w, h), interpolation=cv2.INTER_CUBIC)
    color = cv2.applyColorMap(heat_img, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(bgr, 0.55, color, 0.45, 0)
    return _jpeg_b64(overlay)


def classify_with_viz(bgr: np.ndarray) -> dict:
    from v3_predictor import predict_v3
    r = predict_v3(bgr)
    pred = r["prediction"]
    probs = r["probabilities"]
    pred_idx = list(probs.keys()).index(pred)
    base_prob = float(probs[pred])
    images = _preprocess_steps(bgr)
    try:
        images["gradcam"] = _occlusion_saliency(bgr, pred_idx, base_prob)
    except Exception:
        images["gradcam"] = images.get("normalized", "")
    # ana görüntüleyici overlay'i (2D'de segmentasyon yok → orijinal)
    images["overlay"] = images["original"]
    return {
        "prediction": pred,
        "prediction_tr": _CLASS_TR.get(pred, pred),
        "confidence": r.get("confidence", base_prob),
        "probabilities": probs,
        "model_id": r.get("model_id", "v3_rf_hgb_kaggle4"),
        "images": images,
    }
