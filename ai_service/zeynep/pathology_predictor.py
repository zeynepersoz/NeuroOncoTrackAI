"""
zeynep/pathology_predictor.py — Histopatoloji doku sınıflandırıcı (ResNet-18)
================================================================================
Zeynep bölümü. NCT-CRC-HE üzerinde eğitilmiş 9-sınıf H&E doku sınıflandırıcı.
Bağımsız test doğruluğu ~%94.8 (tümör epiteli recall 0.98).

9 sınıf: ADI, BACK, DEB, LYM, MUC, MUS, NORM, STR, TUM

Dış API:
  predict_pathology(img)      -> {prediction, prediction_tr, confidence, probabilities, latency_ms}
  get_pathology_info()        -> model meta

Model: finetuned_models/crc_model.pt ({state_dict, classes, model}). torchvision gerekir.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_MODEL_PATH = _HERE / "finetuned_models" / "crc_model.pt"

CLASS_TR = {
    "ADI": "Yağ dokusu", "BACK": "Arka plan", "DEB": "Debris (döküntü)",
    "LYM": "Lenfositler", "MUC": "Müsin", "MUS": "Düz kas",
    "NORM": "Normal mukoza", "STR": "Kanser ilişkili stroma", "TUM": "Tümör epiteli",
}
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_MODEL = None
_CLASSES = None
_DEVICE = None


def _get_device():
    import torch
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load_model():
    global _MODEL, _CLASSES, _DEVICE
    if _MODEL is not None:
        return _MODEL
    if not _MODEL_PATH.exists():
        raise RuntimeError(f"Patoloji modeli yok: {_MODEL_PATH}")
    import torch
    from torchvision import models
    _DEVICE = _get_device()
    ckpt = torch.load(_MODEL_PATH, map_location=_DEVICE, weights_only=False)
    _CLASSES = ckpt["classes"]
    net = models.resnet18(weights=None)
    net.fc = torch.nn.Linear(net.fc.in_features, len(_CLASSES))
    net.load_state_dict(ckpt["state_dict"])
    net.to(_DEVICE).eval()
    _MODEL = net
    return _MODEL


def _preprocess(img_2d: np.ndarray, bgr: bool = True) -> np.ndarray:
    """H&E patch (H,W,3) → (3,224,224) normalize. bgr=True ise cv2 BGR → RGB çevrilir
    (model RGB/PIL ile eğitildi; renk kritik)."""
    import cv2
    if img_2d.ndim == 2:
        img_2d = np.stack([img_2d] * 3, axis=-1)
    if img_2d.shape[2] == 4:
        img_2d = img_2d[:, :, :3]
    if bgr:
        img_2d = img_2d[:, :, ::-1]  # BGR → RGB
    img = cv2.resize(img_2d.astype(np.float32), (224, 224), interpolation=cv2.INTER_AREA)
    if img.max() > 1.5:
        img /= 255.0
    img = (img - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(img, (2, 0, 1)).astype(np.float32)


def predict_pathology(img_2d: np.ndarray) -> dict:
    """Tek H&E patch → 9-sınıf doku tahmini."""
    import torch
    t0 = time.perf_counter()
    model = _load_model()
    x = torch.from_numpy(_preprocess(img_2d))[None].to(_DEVICE)
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)[0].cpu().numpy()
    idx = int(probs.argmax())
    cls = _CLASSES[idx]
    return {
        "prediction": cls,
        "prediction_tr": CLASS_TR.get(cls, cls),
        "confidence": float(probs[idx]),
        "probabilities": {c: float(probs[i]) for i, c in enumerate(_CLASSES)},
        "probabilities_tr": {CLASS_TR.get(c, c): float(probs[i]) for i, c in enumerate(_CLASSES)},
        "model": "resnet18_nct_crc_he",
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


def get_pathology_info() -> dict:
    return {
        "task": "colorectal_histopathology_9class",
        "arch": "ResNet-18 (transfer)",
        "trained_on": "NCT-CRC-HE-100K",
        "test_accuracy": 0.9476,
        "classes": list(CLASS_TR.keys()),
        "classes_tr": CLASS_TR,
        "model_available": _MODEL_PATH.exists(),
    }


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        import cv2
        print(json.dumps(predict_pathology(cv2.imread(sys.argv[1])), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(get_pathology_info(), ensure_ascii=False, indent=2))
