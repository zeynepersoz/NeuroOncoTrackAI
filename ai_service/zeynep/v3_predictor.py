"""
v3_predictor.py — v2 cache (1310 slice, 710 glioma) ile eğitilmiş predictor

v2_predictor ile aynı arayüz, sadece model dosyaları değişir:
  - rf_brats_v2.pkl (RandomForest, class_weight='balanced', 600 estimators)
  - hgb_brats_v2.pkl (HistGradientBoosting, max_iter=500)

Ensemble ağırlıkları: RF=0.70 + HGB=0.30 (v1'de bulunan optimum).

Group-CV OOF: Acc=0.9405  BAcc=0.9242  F1=0.9321
Glioma recall: 0.9761 (v1 ~0.90'dan büyük artış — external gap'i çözmeli)
"""

from __future__ import annotations
import os, time, json
from pathlib import Path
import numpy as np
import cv2
import joblib

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

_HERE = Path(__file__).resolve().parent
_MODELS = _HERE / "finetuned_models"

CLASS_NAMES = ["glioma", "meningioma", "notumor"]
W_RF = 0.70
W_HGB = 0.30

_CNN = None
_RF = None
_HGB = None

# preprocess'i v2_predictor'dan yeniden kullan
from v2_predictor import (
    _brain_mask_otsu, _kaggle_style_preprocess, _letterbox, _to_grayscale_u8,
)


def _load_cnn():
    global _CNN
    if _CNN is not None: return _CNN
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
        _RF = joblib.load(_MODELS / "rf_brats_v2.pkl")
    return _RF


def _load_hgb():
    global _HGB
    if _HGB is None:
        _HGB = joblib.load(_MODELS / "hgb_brats_v2.pkl")
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


def predict_v3(img: np.ndarray, apply_domain_preproc: bool = True) -> dict:
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
        "model": "v3_rf_hgb_expanded_cache",
        "weights": {"rf": W_RF, "hgb": W_HGB},
        "preprocess": "otsu_clahe_bbox" if apply_domain_preproc else "raw_gray",
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


def predict_v3_multislice(slices: list, apply_domain_preproc: bool = True) -> dict:
    if not slices:
        raise ValueError("En az 1 dilim gerekli.")
    t0 = time.perf_counter()
    per_slice = []
    for s in slices:
        gray = _to_grayscale_u8(s)
        rgb = _kaggle_style_preprocess(gray) if apply_domain_preproc \
              else cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
        per_slice.append(_ensemble_probs(_extract_feats(rgb)))
    avg = np.mean(per_slice, axis=0)
    avg = avg / avg.sum()
    idx = int(np.argmax(avg))
    return {
        "prediction": CLASS_NAMES[idx],
        "confidence": float(avg[idx]),
        "probabilities": {CLASS_NAMES[i]: float(avg[i]) for i in range(len(CLASS_NAMES))},
        "n_slices": len(slices),
        "model": "v3_rf_hgb_expanded_multislice",
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


def get_v3_info() -> dict:
    info = {
        "model_id": "v3_rf_hgb_expanded_cache",
        "components": ["MobileNetV2 (ImageNet)", "RandomForest (v2)", "HistGradientBoosting (v2)"],
        "ensemble_weights": {"rf": W_RF, "hgb": W_HGB},
        "class_names": CLASS_NAMES,
        "input_shape": [128, 128, 3],
        "cache_version": "v2 (1310 slice, 1010 case, 530 yeni glioma)",
    }
    p = _MODELS / "v2_finetune_metrics.json"
    if p.exists():
        with open(p) as f:
            info["metrics"] = json.load(f)
    return info


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(get_v3_info(), indent=2)[:1500])
