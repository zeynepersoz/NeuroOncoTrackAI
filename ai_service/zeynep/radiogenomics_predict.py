"""
radiogenomics_predict.py — Gerçek IDH tahmini (sanal biyopsi çekirdeği).
UCSF-PDGM (495 glioma, gerçek IDH etiketi) ile eğitilmiş RF+GB ensemble,
hasta-bazlı 5-fold CV AUC=0,919. T1c + FLAIR + tümör maskesinden radyomik
özellik çıkarıp IDH-mutant olasılığı ve en belirleyici özellikleri (SHAP-benzeri)
döner. MGMT: imaging'den güvenilir tahmin edilemez (AUC~0,52; RSNA-MICCAI 2021
ile tutarlı) — sahte değer ÜRETİLMEZ, lab önerilir. Model repoda YOK (ayrı paylaşılır).
"""
from __future__ import annotations
import os
from pathlib import Path
import numpy as np

_HERE = Path(__file__).resolve().parent
_MODEL = _HERE / "finetuned_models" / "model_idh.pkl"
_M = None


def idh_available() -> bool:
    return _MODEL.exists()


def _load():
    global _M
    if _M is None:
        import joblib
        _M = joblib.load(str(_MODEL))
    return _M


def predict_idh(t1c: np.ndarray, flair: np.ndarray, mask: np.ndarray, spacing=(1.0, 1.0, 1.0)) -> dict:
    """T1c + FLAIR + tümör maskesi → IDH-mutant olasılığı + öne çıkan özellikler."""
    from radiogenomics import extract_features, FEATURES
    m = _load()
    f = extract_features(t1c, flair, mask.astype(bool), spacing)
    x = np.array([[f[k] for k in FEATURES]])
    xn = m["scaler"].transform(x)
    p = 0.6 * m["rf"].predict_proba(xn)[0, 1] + 0.4 * m["gb"].predict_proba(xn)[0, 1]
    imp = m["rf"].feature_importances_
    order = np.argsort(imp)[::-1][:5]
    top = [{"feature": FEATURES[i], "value": round(float(f[FEATURES[i]]), 2),
            "importance": round(float(imp[i]), 3)} for i in order]
    prob = float(p)
    return {
        "idh_status": "IDH-mutant" if prob >= 0.5 else "IDH-wildtype",
        "idh_mutant_prob": round(prob * 100, 1),
        "model_auc": m.get("auc"),
        "top_features": top,
        "mgmt_status": "İmaging'den güvenilir tahmin edilemez — laboratuvar (metilasyon PCR) gerekir",
        "note": (f"Radyogenomik IDH tahmini (UCSF-PDGM, n={m.get('n')}, 5-fold CV AUC={m.get('auc')}). "
                 "Karar destek amaçlıdır; kesin tanı moleküler patoloji ile."),
    }
