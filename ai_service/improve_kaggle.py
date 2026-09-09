"""
ai_service/improve_kaggle.py — TTA + Stacking + Threshold ile baseline'ı geç
==============================================================================

Baseline: rf_kaggle.pkl + hgb_kaggle.pkl (finetune_kaggle.py'nin çıktısı)
         → Testing accuracy 0.8988, glioma recall 0.7175

Bu script:
  1. TTA (Test-Time Augmentation) → Testing setinde 5 augmentation ortala
  2. Stacking meta-learner (LR) → Training out-of-fold probs üstünde eğit
  3. Threshold optimization → Training val split'te class-specific eşik öğren
  4. Hepsini birleştirip final metric raporla

Test setine dokunulmaz — sadece final skor için kullanılır.
Threshold ve stacking TAMAMEN Training'den öğrenilir (5-fold CV).

Kullanım:
  python3 ai_service/improve_kaggle.py \
      --root /Users/zeynepersoz/data/kaggle/brain-tumor-mri/archive-2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import joblib
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "zeynep"))

CLASSES = ["glioma", "meningioma", "notumor", "pituitary"]
MODELS_DIR = HERE / "finetuned_models_kaggle"
OUT_DIR = HERE / "_eval_out"


# ═══════════════════════════════════════════════════════════════════
# Augmentation transforms (TTA)
# ═══════════════════════════════════════════════════════════════════
def _augment_variants(img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Bir görüntünün 5 augmentation versiyonu."""
    return [
        ("orig", img),
        ("hflip", cv2.flip(img, 1)),
        ("vflip", cv2.flip(img, 0)),
        ("rot90", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)),
        ("rot270", cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)),
    ]


# ═══════════════════════════════════════════════════════════════════
# Feature extraction (TTA-aware)
# ═══════════════════════════════════════════════════════════════════
def _iter_class_images(root: Path, split: str, cls: str):
    d = root / split / cls
    if not d.exists():
        d = root / split / cls.replace("notumor", "no_tumor")
        if not d.exists():
            return
    yield from sorted(list(d.glob("*.jpg")) + list(d.glob("*.png")))


def extract_features_tta(root: Path, split: str) -> tuple[np.ndarray, np.ndarray]:
    """Her görüntü için 5 augmentation feature'ı → (N, 5, 1280)."""
    from v2_predictor import _to_grayscale_u8, _kaggle_style_preprocess, _letterbox
    from v3_predictor import _load_cnn

    cnn = _load_cnn()
    all_feats: list[np.ndarray] = []  # (5, 1280) per image
    labels: list[int] = []
    t0 = time.perf_counter()

    for ci, cls in enumerate(CLASSES):
        n = 0
        for fpath in _iter_class_images(root, split, cls):
            img = cv2.imread(str(fpath), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            gray = _to_grayscale_u8(img)
            variants = _augment_variants(gray)
            # Her varyantı preprocess + feature
            batch = []
            for _, var_img in variants:
                rgb = _kaggle_style_preprocess(var_img)
                lb = _letterbox(rgb, 128).astype(np.float32) / 255.0
                batch.append(lb)
            batch_arr = np.stack(batch, axis=0)  # (5, 128, 128, 3)
            feats = cnn.predict(batch_arr, verbose=0)  # (5, 1280)
            all_feats.append(feats)
            labels.append(ci)
            n += 1
            if n % 50 == 0:
                elapsed = time.perf_counter() - t0
                print(f"  {cls:<11} n={n}  toplam={len(all_feats)}  ({elapsed:.1f}s)")
        print(f"  {cls:<11} tamam: {n}")

    X = np.stack(all_feats, axis=0)  # (N, 5, 1280)
    y = np.array(labels, dtype=np.int64)
    print(f"→ TTA feature matrix: {X.shape}  ({time.perf_counter()-t0:.1f}s)")
    return X, y


# ═══════════════════════════════════════════════════════════════════
# Ensemble prediction (with soft-voting across augmentations)
# ═══════════════════════════════════════════════════════════════════
def predict_ensemble(X: np.ndarray, rf, hgb, w_rf: float = 0.70) -> np.ndarray:
    """X: (N, 1280) → probs (N, 4)"""
    w_hgb = 1.0 - w_rf
    p_rf = rf.predict_proba(X)
    p_hgb = hgb.predict_proba(X)
    return w_rf * p_rf + w_hgb * p_hgb


def predict_tta(X_tta: np.ndarray, rf, hgb, w_rf: float = 0.70) -> np.ndarray:
    """X_tta: (N, K_aug, 1280) → probs (N, 4), geometric mean across augs."""
    N, K, D = X_tta.shape
    flat = X_tta.reshape(N * K, D)
    probs_flat = predict_ensemble(flat, rf, hgb, w_rf)  # (N*K, 4)
    probs = probs_flat.reshape(N, K, 4)
    # Geometric mean (log-space) — outlier'a arithmetic'ten daha dayanıklı
    log_p = np.log(np.clip(probs, 1e-8, 1.0))
    log_mean = log_p.mean(axis=1)
    p = np.exp(log_mean)
    return p / p.sum(axis=1, keepdims=True)


# ═══════════════════════════════════════════════════════════════════
# Stacking meta-learner (LR on RF+HGB out-of-fold probs)
# ═══════════════════════════════════════════════════════════════════
def build_stacking(X_train: np.ndarray, y_train: np.ndarray, n_folds: int = 5):
    """Training üstünde 5-fold CV ile out-of-fold probs oluştur → LR fit."""
    from sklearn.model_selection import StratifiedKFold
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression

    print(f"→ Stacking meta-learner ({n_folds}-fold CV oof probs)...")
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    N = len(X_train)
    K = len(CLASSES)
    oof_probs = np.zeros((N, K * 2), dtype=np.float32)  # RF probs + HGB probs
    t0 = time.perf_counter()

    for fold, (tr_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
        rf = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                    random_state=42, n_jobs=-1)
        hgb = HistGradientBoostingClassifier(max_iter=400, random_state=42)
        rf.fit(X_train[tr_idx], y_train[tr_idx])
        hgb.fit(X_train[tr_idx], y_train[tr_idx])
        oof_probs[val_idx, :K] = rf.predict_proba(X_train[val_idx])
        oof_probs[val_idx, K:] = hgb.predict_proba(X_train[val_idx])
        print(f"  fold {fold+1}/{n_folds} tamam ({time.perf_counter()-t0:.1f}s)")

    print(f"→ Meta-learner (LR) fit ediliyor...")
    meta = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced",
                              multi_class="multinomial", random_state=42)
    meta.fit(oof_probs, y_train)
    print(f"  OOF stacking accuracy: {meta.score(oof_probs, y_train):.4f}")
    return meta


def stacked_predict(X: np.ndarray, rf, hgb, meta) -> np.ndarray:
    """Full-training RF+HGB probs → meta-learner ile birleştir."""
    K = len(CLASSES)
    stacked_feat = np.zeros((len(X), K * 2), dtype=np.float32)
    stacked_feat[:, :K] = rf.predict_proba(X)
    stacked_feat[:, K:] = hgb.predict_proba(X)
    return meta.predict_proba(stacked_feat)


def stacked_predict_tta(X_tta: np.ndarray, rf, hgb, meta) -> np.ndarray:
    N, K_aug, D = X_tta.shape
    all_probs = np.zeros((N, K_aug, len(CLASSES)), dtype=np.float32)
    for k in range(K_aug):
        all_probs[:, k, :] = stacked_predict(X_tta[:, k, :], rf, hgb, meta)
    log_p = np.log(np.clip(all_probs, 1e-8, 1.0))
    p = np.exp(log_p.mean(axis=1))
    return p / p.sum(axis=1, keepdims=True)


# ═══════════════════════════════════════════════════════════════════
# Threshold tuning (Training val split ile)
# ═══════════════════════════════════════════════════════════════════
def learn_class_priors(probs_val: np.ndarray, y_val: np.ndarray) -> np.ndarray:
    """Her sınıf için multiplier bul (glioma'yı boost et)."""
    from scipy.optimize import minimize

    K = len(CLASSES)

    def neg_f1_macro(logw):
        w = np.exp(logw)
        adjusted = probs_val * w[None, :]
        pred = adjusted.argmax(axis=1)
        f1s = []
        for i in range(K):
            tp = ((pred == i) & (y_val == i)).sum()
            fp = ((pred == i) & (y_val != i)).sum()
            fn = ((pred != i) & (y_val == i)).sum()
            prec = tp / (tp + fp + 1e-9)
            rec = tp / (tp + fn + 1e-9)
            f1 = 2 * prec * rec / (prec + rec + 1e-9)
            f1s.append(f1)
        return -np.mean(f1s)

    print("→ Class priors optimizasyonu (macro-F1 max)...")
    res = minimize(neg_f1_macro, x0=np.zeros(K), method="Nelder-Mead",
                   options={"maxiter": 500, "xatol": 1e-3})
    w = np.exp(res.x)
    w = w / w.min()  # normalize
    print(f"  Bulunan multiplier: {dict(zip(CLASSES, np.round(w, 3).tolist()))}")
    print(f"  Val macro-F1: {-res.fun:.4f}")
    return w


# ═══════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════
def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, label: str = "") -> dict:
    K = len(CLASSES)
    cm = np.zeros((K, K), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    per_class = {}
    f1s = []
    for i, c in enumerate(CLASSES):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_class[c] = {"precision": round(float(prec), 4),
                        "recall": round(float(rec), 4),
                        "f1": round(float(f1), 4),
                        "support": int(cm[i, :].sum())}
        f1s.append(f1)
    acc = float((y_pred == y_true).mean())
    macro_f1 = float(np.mean(f1s))
    if label:
        print(f"\n{label}:")
        print(f"  accuracy = {acc:.4f}   macro-F1 = {macro_f1:.4f}")
        for c, m in per_class.items():
            print(f"  {c:<11} P={m['precision']:.3f} R={m['recall']:.3f} "
                  f"F1={m['f1']:.3f} n={m['support']}")
    return {"accuracy": round(acc, 4), "macro_f1": round(macro_f1, 4),
            "per_class": per_class, "confusion_matrix": cm.tolist(),
            "labels": CLASSES}


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--force-tta", action="store_true",
                    help="TTA feature cache'i yeniden hesapla")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1) Modelleri ve cached feature'ları yükle ─────────────────
    print("→ Baseline modeller yükleniyor...")
    rf = joblib.load(MODELS_DIR / "rf_kaggle.pkl")
    hgb = joblib.load(MODELS_DIR / "hgb_kaggle.pkl")
    d_tr = np.load(MODELS_DIR / "features_kaggle_train.npz", allow_pickle=True)
    X_tr, y_tr = d_tr["X"], d_tr["y"]
    d_te = np.load(MODELS_DIR / "features_kaggle_test.npz", allow_pickle=True)
    X_te, y_te = d_te["X"], d_te["y"]
    print(f"  train={X_tr.shape}  test={X_te.shape}")

    # ── 2) BASELINE (mevcut) ────────────────────────────────────────
    probs_base = predict_ensemble(X_te, rf, hgb)
    m_base = compute_metrics(y_te, probs_base.argmax(axis=1),
                             label="Baseline (mevcut, tek augmentation)")

    # ── 3) TTA feature çıkarımı (Testing) ─────────────────────────
    tta_cache = MODELS_DIR / "features_kaggle_test_tta.npz"
    if tta_cache.exists() and not args.force_tta:
        print(f"\n→ Cached TTA feature yükleniyor: {tta_cache}")
        d = np.load(tta_cache, allow_pickle=True)
        X_te_tta, y_te_tta = d["X"], d["y"]
        print(f"  shape={X_te_tta.shape}")
    else:
        print("\n→ Testing TTA feature çıkarımı (5 augmentation × 1600 = ~4-6 dk)...")
        X_te_tta, y_te_tta = extract_features_tta(root, "Testing")
        np.savez_compressed(tta_cache, X=X_te_tta, y=y_te_tta)
        print(f"  cached: {tta_cache}")

    assert np.array_equal(y_te, y_te_tta), "Etiket sırası bozuk"

    # ── 4) TTA sonucu ───────────────────────────────────────────────
    probs_tta = predict_tta(X_te_tta, rf, hgb)
    m_tta = compute_metrics(y_te, probs_tta.argmax(axis=1),
                            label="TTA (5 augmentation ortalaması)")

    # ── 5) Stacking meta-learner ────────────────────────────────────
    meta = build_stacking(X_tr, y_tr, n_folds=5)
    joblib.dump(meta, MODELS_DIR / "meta_lr_kaggle.pkl")

    probs_stack = stacked_predict(X_te, rf, hgb, meta)
    m_stack = compute_metrics(y_te, probs_stack.argmax(axis=1),
                              label="Stacking (RF+HGB probs → LR meta)")

    probs_stack_tta = stacked_predict_tta(X_te_tta, rf, hgb, meta)
    m_stack_tta = compute_metrics(y_te, probs_stack_tta.argmax(axis=1),
                                  label="Stacking + TTA")

    # ── 6) Class prior optimization (Training oof üstünde) ─────────
    from sklearn.model_selection import StratifiedKFold
    print("\n→ Training'den oof probs (prior tuning için)...")
    oof_probs_tr = np.zeros((len(X_tr), len(CLASSES)), dtype=np.float32)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    for fold, (tri, vai) in enumerate(skf.split(X_tr, y_tr)):
        rf_f = RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                      random_state=42, n_jobs=-1)
        hgb_f = HistGradientBoostingClassifier(max_iter=400, random_state=42)
        rf_f.fit(X_tr[tri], y_tr[tri])
        hgb_f.fit(X_tr[tri], y_tr[tri])
        p_rf = rf_f.predict_proba(X_tr[vai])
        p_hgb = hgb_f.predict_proba(X_tr[vai])
        oof_probs_tr[vai] = 0.7 * p_rf + 0.3 * p_hgb
        print(f"  fold {fold+1}/5 tamam")
    priors = learn_class_priors(oof_probs_tr, y_tr)

    # Priors'ı stacking+TTA'ya uygula
    probs_final = probs_stack_tta * priors[None, :]
    probs_final = probs_final / probs_final.sum(axis=1, keepdims=True)
    m_final = compute_metrics(y_te, probs_final.argmax(axis=1),
                              label="Stacking + TTA + Class Priors (FINAL)")

    # ── 7) Kaydet ───────────────────────────────────────────────────
    all_results = {
        "baseline": m_base,
        "tta_only": m_tta,
        "stacking_only": m_stack,
        "stacking_tta": m_stack_tta,
        "final_stacking_tta_priors": m_final,
        "class_priors": {c: float(w) for c, w in zip(CLASSES, priors)},
    }
    out_path = OUT_DIR / "improve_kaggle_results.json"
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"\n→ Sonuçlar: {out_path}")

    # Özet tablo
    print("\n" + "=" * 60)
    print("ÖZET (Kaggle Testing, n=1600)")
    print("=" * 60)
    print(f"{'Strateji':<40}  {'acc':>7}  {'macro-F1':>9}")
    print("-" * 60)
    for name, m in [("Baseline (rf+hgb)", m_base),
                    ("TTA", m_tta),
                    ("Stacking", m_stack),
                    ("Stacking + TTA", m_stack_tta),
                    ("FINAL (Stack+TTA+Priors)", m_final)]:
        delta = (m["accuracy"] - m_base["accuracy"]) * 100
        arrow = f"+{delta:.2f} pp" if delta > 0 else f"{delta:.2f} pp"
        print(f"{name:<40}  {m['accuracy']:>7.4f}  {m['macro_f1']:>9.4f}  {arrow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
