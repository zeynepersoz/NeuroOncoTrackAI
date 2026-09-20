"""
cnn_predictor.py — MRI'a özel uçtan-uca CNN sınıflandırıcı (efficientnet_b0, torch).
Kaggle 4-sınıf + Trakya Ü. hastane DICOM ile fine-tune edildi (MRI öznitelikleri
öğrenilmiş — donuk ImageNet+RF/HGB'nin aksine). Kaggle Testing %95.8, referans 12/12,
hastane menenjiyom duyarlılığı belirgin daha yüksek. predict_v3 çıktı şemasıyla uyumlu.
Model dosyası finetuned_models/cnn_final.pt (repoda YOK — ayrı paylaşılır).
Not: bu model HAM gri→resize→ImageNet-normalize ister; Otsu/CLAHE ön işleme UYGULANMAZ.
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np

_HERE = Path(__file__).resolve().parent
_CKPT = _HERE / "finetuned_models" / "cnn_final.pt"
CLASS_NAMES = ["glioma", "meningioma", "notumor", "pituitary"]
_MODEL = None
_TF = None
_DEV = None


def cnn_available() -> bool:
    return _CKPT.exists()


def _load():
    global _MODEL, _TF, _DEV
    if _MODEL is not None:
        return _MODEL
    import torch, torch.nn as nn
    from torchvision import transforms, models
    _DEV = torch.device("cpu")  # serving: CPU (kararlılık); tek görüntü hızlı
    m = models.efficientnet_b0()
    m.classifier[1] = nn.Linear(m.classifier[1].in_features, 4)
    m.load_state_dict(torch.load(str(_CKPT), map_location=_DEV))
    m.eval().to(_DEV)
    _MODEL = m
    _TF = transforms.Compose([
        transforms.Grayscale(3), transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    return _MODEL


def _to_gray_u8(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        import cv2
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    a = img.astype(np.float32)
    lo, hi = np.percentile(a, 1), np.percentile(a, 99)
    if hi <= lo:
        lo, hi = float(a.min()), float(a.max())
    a = np.clip((a - lo) / (hi - lo + 1e-6), 0, 1) * 255
    return a.astype(np.uint8)


def predict_cnn(img: np.ndarray, **_) -> dict:
    import torch
    from PIL import Image
    m = _load()
    gray = _to_gray_u8(img)
    x = _TF(Image.fromarray(gray).convert("L")).unsqueeze(0).to(_DEV)
    with torch.no_grad():
        p = torch.softmax(m(x), 1).cpu().numpy()[0]
    idx = int(p.argmax())
    return {
        "prediction": CLASS_NAMES[idx],
        "confidence": float(p[idx]),
        "probabilities": {CLASS_NAMES[i]: float(p[i]) for i in range(4)},
        "model": "cnn_efficientnet_b0_mri",
    }
