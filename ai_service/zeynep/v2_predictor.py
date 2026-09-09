"""
v2_predictor.py — RF + HGB Ağırlıklı Ensemble Predictor (v2)

3-yollu grid search sonucunda en iyi kombinasyon: RF=0.70, HGB=0.30
(GB katkısız çıktı — çıkarıldı). Group-CV: BAcc 0.9389, Acc 0.9449.

Bu modül tamamen bağımsız bir peer wrapper'dır; ana finetuned_inference.py
veya inference.py dokunulmadan kalır.

Kullanım:
    from v2_predictor import predict_v2, predict_v2_multislice, get_v2_info
    result = predict_v2(gray_uint8_image)
"""

from __future__ import annotations
import os, time, json
from pathlib import Path
from typing import Optional
import numpy as np
import cv2
import joblib

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

_HERE = Path(__file__).resolve().parent
_MODELS = _HERE / "finetuned_models"

CLASS_NAMES = ["glioma", "meningioma", "notumor"]

# ─── Ağırlıklar (eval_3way_ensemble.py sonucu) ────────────────────
W_RF = 0.70
W_HGB = 0.30

# Lazy singletons
_CNN = None
_RF = None
_HGB = None


# ─── Preprocessing (finetune_brats ile bit-exact aynı) ────────────
def _brain_mask_otsu(gray_u8: np.ndarray) -> np.ndarray:
    _, m = cv2.threshold(gray_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k, iterations=2)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if num < 2:
        return m
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    brain = (labels == largest).astype(np.uint8) * 255
    return cv2.morphologyEx(
        brain, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)),
    )


def _to_grayscale_u8(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype != np.uint8:
        lo, hi = np.percentile(img, [1, 99])
        if hi <= lo:
            hi = lo + 1
        img = (np.clip((img - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    return img


def _kaggle_style_preprocess(slice_u8: np.ndarray) -> np.ndarray:
    mask = _brain_mask_otsu(slice_u8)
    brain = cv2.bitwise_and(slice_u8, slice_u8, mask=mask)
    ys, xs = np.where(mask > 0)
    if len(xs) < 50:
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return cv2.cvtColor(clahe.apply(slice_u8), cv2.COLOR_GRAY2RGB)
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    pad = 8
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(brain.shape[1], x1 + pad)
    y1 = min(brain.shape[0], y1 + pad)
    crop = brain[y0:y1, x0:x1]
    h, w = crop.shape[:2]
    side = max(h, w)
    sq = np.zeros((side, side), dtype=np.uint8)
    py, px = (side - h) // 2, (side - w) // 2
    sq[py:py + h, px:px + w] = crop
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return cv2.cvtColor(clahe.apply(sq), cv2.COLOR_GRAY2RGB)


def _letterbox(img: np.ndarray, size: int = 128) -> np.ndarray:
    h0, w0 = img.shape[:2]
    s = min(size / w0, size / h0)
    nw, nh = max(1, int(w0 * s)), max(1, int(h0 * s))
    r = cv2.resize(img, (nw, nh))
    lb = np.zeros((size, size, 3), dtype=np.uint8)
    py, px = (size - nh) // 2, (size - nw) // 2
    lb[py:py + nh, px:px + nw] = r
    return lb


# ─── Model loaders (lazy) ─────────────────────────────────────────
def _load_cnn():
    global _CNN
    if _CNN is not None:
        return _CNN
    from tensorflow.keras.applications import MobileNetV2
    from tensorflow.keras.layers import GlobalAveragePooling2D
    from tensorflow.keras.models import Model
    base = MobileNetV2(weights="imagenet", include_top=False,
                       input_shape=(128, 128, 3))
    _CNN = Model(inputs=base.input, outputs=GlobalAveragePooling2D()(base.output))
    return _CNN


def _load_rf():
    global _RF
    if _RF is None:
        _RF = joblib.load(_MODELS / "rf_brats_finetuned.pkl")
    return _RF


def _load_hgb():
    global _HGB
    if _HGB is None:
        _HGB = joblib.load(_MODELS / "hgb_brats_finetuned.pkl")
    return _HGB


def _extract_feats(rgb_u8: np.ndarray) -> np.ndarray:
    cnn = _load_cnn()
    lb = _letterbox(rgb_u8, 128).astype(np.float32) / 255.0
    return cnn.predict(np.expand_dims(lb, 0), verbose=0)


def _ensemble_probs(feats: np.ndarray) -> np.ndarray:
    rf = _load_rf()
    hgb = _load_hgb()
    p_rf = rf.predict_proba(feats)[0]
    p_hgb = hgb.predict_proba(feats)[0]
    p = W_RF * p_rf + W_HGB * p_hgb
    return p / p.sum()


# ─── Public API ───────────────────────────────────────────────────
def predict_v2(img: np.ndarray, apply_domain_preproc: bool = True) -> dict:
    """
    Tek dilim inference. `img` uint8 grayscale/BGR olabilir.
    apply_domain_preproc=True → Otsu+CLAHE+BBox (klinik BraTS için).
    """
    t0 = time.perf_counter()
    gray = _to_grayscale_u8(img)
    rgb = _kaggle_style_preprocess(gray) if apply_domain_preproc \
          else cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    feats = _extract_feats(rgb)
    probs = _ensemble_probs(feats)
    idx = int(np.argmax(probs))
    return {
        "prediction": CLASS_NAMES[idx],
        "confidence": float(probs[idx]),
        "probabilities": {CLASS_NAMES[i]: float(probs[i]) for i in range(len(CLASS_NAMES))},
        "model": "v2_rf_hgb_ensemble",
        "weights": {"rf": W_RF, "hgb": W_HGB},
        "preprocess": "otsu_clahe_bbox" if apply_domain_preproc else "raw_gray",
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


def predict_v2_multislice(slices: list, apply_domain_preproc: bool = True) -> dict:
    """Birden fazla dilim → olasılıkları ortalar (volume-level)."""
    if not slices:
        raise ValueError("En az 1 dilim gerekli.")
    t0 = time.perf_counter()
    per_slice = []
    for s in slices:
        gray = _to_grayscale_u8(s)
        rgb = _kaggle_style_preprocess(gray) if apply_domain_preproc \
              else cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        feats = _extract_feats(rgb)
        per_slice.append(_ensemble_probs(feats))
    avg = np.mean(per_slice, axis=0)
    avg = avg / avg.sum()
    idx = int(np.argmax(avg))
    return {
        "prediction": CLASS_NAMES[idx],
        "confidence": float(avg[idx]),
        "probabilities": {CLASS_NAMES[i]: float(avg[i]) for i in range(len(CLASS_NAMES))},
        "per_slice_probabilities": [
            {CLASS_NAMES[i]: float(p[i]) for i in range(len(CLASS_NAMES))}
            for p in per_slice
        ],
        "n_slices": len(slices),
        "model": "v2_rf_hgb_ensemble_multislice",
        "weights": {"rf": W_RF, "hgb": W_HGB},
        "preprocess": "otsu_clahe_bbox" if apply_domain_preproc else "raw_gray",
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


def get_v2_info() -> dict:
    """v2 predictor metadata + eval_3way sonuçları."""
    info = {
        "model_id": "v2_rf_hgb_ensemble",
        "components": ["MobileNetV2 (ImageNet)", "RandomForest", "HistGradientBoosting"],
        "ensemble_weights": {"rf": W_RF, "hgb": W_HGB},
        "class_names": CLASS_NAMES,
        "input_shape": [128, 128, 3],
        "preprocessing": "Otsu brain-mask + CLAHE + BBox crop + letterbox",
    }
    m_path = _MODELS / "ensemble3_metrics.json"
    if m_path.exists():
        with open(m_path) as f:
            m = json.load(f)
        info["group_cv_metrics"] = m.get("best_3way", {})
        info["baselines"] = m.get("solo", {})
    return info


if __name__ == "__main__":
    # Smoke test
    print("=" * 60)
    print(" v2_predictor smoke test")
    print("=" * 60)
    info = get_v2_info()
    print(json.dumps(info, indent=2))

    # Dummy test — cache'den bir sample çek
    cache = _HERE / "cache" / "brats_features_v1.npz"
    if cache.exists():
        print("\n Sentetik gri test görüntüsü ile inference...")
        rng = np.random.default_rng(42)
        dummy = rng.integers(0, 255, size=(240, 240), dtype=np.uint8)
        result = predict_v2(dummy, apply_domain_preproc=False)
        print(f"  → {result['prediction']} (conf={result['confidence']:.3f}, "
              f"latency={result['latency_ms']:.1f}ms)")
        print(f"  → probs: {result['probabilities']}")
