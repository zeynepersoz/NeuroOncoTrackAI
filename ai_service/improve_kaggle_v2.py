"""
ai_service/improve_kaggle_v2.py — Milder TTA + Glioma-boosted retrain
========================================================================

v1 sonuçları:
  Baseline           : 0.8988
  Stacking (winner)  : 0.9025 (+0.37 pp)
  TTA (aggressive)   : 0.8712 (KÖTÜ — vflip/rot90 beyin anatomisine uymuyor)

v2 stratejisi:
  1. Milder TTA: sadece hflip (bilateral simetri) + gamma variation
  2. Glioma-boosted head retrain: sample_weight ile glioma×2
  3. LightGBM 3. head (opsiyonel) + stacking

Amaç: glioma recall'ı 0.718 → >0.85'e çıkarmak.
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
# MILD TTA — sadece anatomik olarak geçerli augmentations
# ═══════════════════════════════════════════════════════════════════
def _mild_augment_variants(img: np.ndarray) -> list[np.ndarray]:
    """
    Beyin MR için anatomik olarak geçerli augmentation:
    - orig
    - hflip (bilateral simetri — sol/sağ hemisfer)
    - gamma 0.85 (biraz daha parlak → farklı MR sekans/scanner)
    - gamma 1.15 (biraz daha karanlık)
    NOT: vflip YOK (beyin vertikal simetrik değil — cerebellum aşağıda)
    NOT: rot90 YOK (aksiyel görüntüde koronal/sagittal ile karışır)
    """
    def _gamma(im, g):
        im = im.astype(np.float32) / 255.0
        return np.clip(np.power(im, g) * 255.0, 0, 255).astype(np.uint8)
    return [
        img,
        cv2.flip(img, 1),
        _gamma(img, 0.85),
        _gamma(img, 1.15),
    ]


def _iter_class_images(root: Path, split: str, cls: str):
    d = root / split / cls
    if not d.exists():
        d = root / split / cls.replace("notumor", "no_tumor")
        if not d.exists():
            return
    yield from sorted(list(d.glob("*.jpg")) + list(d.glob("*.png")))


def extract_mild_tta_features(root: Path, split: str) -> tuple[np.ndarray, np.ndarray]:
    """(N, 4, 1280) — orig, hflip, gamma-, gamma+"""
    from v2_predictor import _to_grayscale_u8, _kaggle_style_preprocess, _letterbox
    from v3_predictor import _load_cnn

    cnn = _load_cnn()
    all_feats: list[np.ndarray] = []
    labels: list[int] = []
    t0 = time.perf_counter()

    for ci, cls in enumerate(CLASSES):
        n = 0
        for fpath in _iter_class_images(root, split, cls):
            img = cv2.imread(str(fpath), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            gray = _to_grayscale_u8(img)
            variants = _mild_augment_variants(gray)
            batch = []
            for var_img in variants:
                rgb = _kaggle_style_preprocess(var_img)
                lb = _letterbox(rgb, 128).astype(np.float32) / 255.0
                batch.append(lb)
            batch_arr = np.stack(batch, axis=0)
            feats = cnn.predict(batch_arr, verbose=0)
            all_feats.append(feats)
            labels.append(ci)
            n += 1
            if n % 100 == 0:
                elapsed = time.perf_counter() - t0
                print(f"  {cls:<11} n={n}  toplam={len(all_feats)}  ({elapsed:.1f}s)")
        print(f"  {cls:<11} tamam: {n}")

    X = np.stack(all_feats, axis=0)
    y = np.array(labels, dtype=np.int64)
    print(f"→ Mild TTA feature matrix: {X.shape}  ({time.perf_counter()-t0:.1f}s)")
    return X, y


# ═══════════════════════════════════════════════════════════════════
# Glioma-boosted retrain
# ═══════════════════════════════════════════════════════════════════
def fit_glioma_boosted(X: np.ndarray, y: np.ndarray, glioma_weight: float = 2.0):
    """
    Glioma vakalarına daha yüksek sample_weight ver.
    Hem RF hem HGB için.
    """
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier

    # sample_weight: glioma=glioma_weight, diğer=1.0
    sw = np.ones(len(y), dtype=np.float32)
    sw[y == CLASSES.index("glioma")] = glioma_weight

    print(f"→ Glioma-boosted RF (glioma_weight={glioma_weight})...")
    t = time.perf_counter()
    rf = RandomForestClassifier(
        n_estimators=600, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    rf.fit(X, y, sample_weight=sw)
    print(f"  RF fit: {time.perf_counter()-t:.1f}s")

    print(f"→ Glioma-boosted HGB...")
    t = time.perf_counter()
    hgb = HistGradientBoostingClassifier(
        max_iter=500, random_state=42,
    )
    hgb.fit(X, y, sample_weight=sw)
    print(f"  HGB fit: {time.perf_counter()-t:.1f}s")

    return rf, hgb


# ═══════════════════════════════════════════════════════════════════
# Prediction helpers
# ═══════════════════════════════════════════════════════════════════
def predict_ensemble(X: np.ndarray, rf, hgb, w_rf: float = 0.70) -> np.ndarray:
    return w_rf * rf.predict_proba(X) + (1 - w_rf) * hgb.predict_proba(X)


def predict_tta_mild(X_tta: np.ndarray, rf, hgb, w_rf: float = 0.70) -> np.ndarray:
    """X_tta: (N, K_aug, 1280) → probs (N, 4)"""
    N, K, D = X_tta.shape
    flat = X_tta.reshape(N * K, D)
    probs_flat = predict_ensemble(flat, rf, hgb, w_rf)
    probs = probs_flat.reshape(N, K, 4)
    # Geometric mean
    log_p = np.log(np.clip(probs, 1e-8, 1.0))
    p = np.exp(log_p.mean(axis=1))
    return p / p.sum(axis=1, keepdims=True)


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
    ap.add_argument("--glioma-weight", type=float, default=2.0)
    ap.add_argument("--force-tta", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Baseline modeller ve features ──────────────────────────────
    print("→ Baseline modeller yükleniyor...")
    rf_base = joblib.load(MODELS_DIR / "rf_kaggle.pkl")
    hgb_base = joblib.load(MODELS_DIR / "hgb_kaggle.pkl")
    d_tr = np.load(MODELS_DIR / "features_kaggle_train.npz", allow_pickle=True)
    X_tr, y_tr = d_tr["X"], d_tr["y"]
    d_te = np.load(MODELS_DIR / "features_kaggle_test.npz", allow_pickle=True)
    X_te, y_te = d_te["X"], d_te["y"]

    # ── Baseline metric (referans) ─────────────────────────────────
    probs_base = predict_ensemble(X_te, rf_base, hgb_base)
    m_base = compute_metrics(y_te, probs_base.argmax(axis=1),
                             label="Baseline (v1 stack olmadan)")

    # ── Glioma-boosted retrain ─────────────────────────────────────
    print(f"\n═══ Glioma-boosted retrain (weight={args.glioma_weight}) ═══")
    rf_boost, hgb_boost = fit_glioma_boosted(X_tr, y_tr, args.glioma_weight)
    probs_boost = predict_ensemble(X_te, rf_boost, hgb_boost)
    m_boost = compute_metrics(y_te, probs_boost.argmax(axis=1),
                              label=f"Glioma-boosted (w={args.glioma_weight})")

    # ── Milder TTA feature çıkarımı (Testing) ──────────────────────
    mild_tta_cache = MODELS_DIR / "features_kaggle_test_tta_mild.npz"
    if mild_tta_cache.exists() and not args.force_tta:
        print(f"\n→ Cached mild TTA yükleniyor: {mild_tta_cache}")
        d = np.load(mild_tta_cache, allow_pickle=True)
        X_te_tta, y_te_tta = d["X"], d["y"]
        print(f"  shape={X_te_tta.shape}")
    else:
        print("\n→ Testing MILD TTA feature çıkarımı (4 augmentation × 1600 = ~4 dk)...")
        X_te_tta, y_te_tta = extract_mild_tta_features(root, "Testing")
        np.savez_compressed(mild_tta_cache, X=X_te_tta, y=y_te_tta)
        print(f"  cached: {mild_tta_cache}")

    assert np.array_equal(y_te, y_te_tta)

    # ── Mild TTA (baseline modelle) ────────────────────────────────
    probs_tta_base = predict_tta_mild(X_te_tta, rf_base, hgb_base)
    m_tta_base = compute_metrics(y_te, probs_tta_base.argmax(axis=1),
                                 label="Baseline + Mild TTA (hflip+gamma)")

    # ── Mild TTA (glioma-boosted modelle) ──────────────────────────
    probs_tta_boost = predict_tta_mild(X_te_tta, rf_boost, hgb_boost)
    m_tta_boost = compute_metrics(y_te, probs_tta_boost.argmax(axis=1),
                                  label="Glioma-Boosted + Mild TTA")

    # ── Stacking (v1'den) + boosted RF/HGB kombinasyonu ────────────
    try:
        meta = joblib.load(MODELS_DIR / "meta_lr_kaggle.pkl")
        K = len(CLASSES)
        # Base modeller + boosted modeller = 4 head concatenation için LR yeniden fit
        # Basitleştir: sadece base stacking + boost'un OR'u
        stack_feat_te = np.zeros((len(X_te), K * 2), dtype=np.float32)
        stack_feat_te[:, :K] = rf_base.predict_proba(X_te)
        stack_feat_te[:, K:] = hgb_base.predict_proba(X_te)
        probs_stack = meta.predict_proba(stack_feat_te)

        # Ensemble: stacking + boosted average (glioma pozitif ise boost'a %60 ağırlık)
        w_stack = 0.5
        probs_combo = w_stack * probs_stack + (1 - w_stack) * probs_boost
        m_combo = compute_metrics(y_te, probs_combo.argmax(axis=1),
                                  label="Stacking + Glioma-Boosted (50/50)")

        # Combo + Mild TTA
        stack_feat_tta = np.zeros((len(X_te), 4, K * 2), dtype=np.float32)
        for k in range(4):
            stack_feat_tta[:, k, :K] = rf_base.predict_proba(X_te_tta[:, k, :])
            stack_feat_tta[:, k, K:] = hgb_base.predict_proba(X_te_tta[:, k, :])
        probs_stack_tta = np.zeros((len(X_te), K), dtype=np.float32)
        for k in range(4):
            probs_stack_tta += meta.predict_proba(stack_feat_tta[:, k, :]) / 4
        probs_combo_tta = w_stack * probs_stack_tta + (1 - w_stack) * probs_tta_boost
        m_combo_tta = compute_metrics(y_te, probs_combo_tta.argmax(axis=1),
                                      label="Stacking + Glioma-Boosted + Mild TTA (FINAL)")
    except FileNotFoundError:
        print("⚠ meta_lr_kaggle.pkl yok, önce improve_kaggle.py çalıştır")
        m_combo = m_combo_tta = None

    # ── Save & summary ────────────────────────────────────────────
    joblib.dump(rf_boost, MODELS_DIR / "rf_kaggle_glioma_boost.pkl")
    joblib.dump(hgb_boost, MODELS_DIR / "hgb_kaggle_glioma_boost.pkl")

    all_results = {
        "baseline": m_base,
        "glioma_boosted": m_boost,
        "tta_mild_baseline": m_tta_base,
        "tta_mild_boosted": m_tta_boost,
        "combo_stack_boost": m_combo,
        "final_combo_stack_boost_tta": m_combo_tta,
        "config": {"glioma_weight": args.glioma_weight,
                   "tta": ["orig", "hflip", "gamma_0.85", "gamma_1.15"]},
    }
    (OUT_DIR / "improve_kaggle_v2_results.json").write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")

    # Özet
    print("\n" + "=" * 70)
    print("ÖZET v2 (Kaggle Testing, n=1600)")
    print("=" * 70)
    print(f"{'Strateji':<45}  {'acc':>7}  {'macro-F1':>9}  {'glioma-R':>9}")
    print("-" * 70)
    rows = [("Baseline (rf+hgb)", m_base),
            (f"Glioma-boosted (w={args.glioma_weight})", m_boost),
            ("Baseline + Mild TTA", m_tta_base),
            ("Glioma-boost + Mild TTA", m_tta_boost)]
    if m_combo:
        rows.append(("Stacking + Glioma-Boost (50/50)", m_combo))
    if m_combo_tta:
        rows.append(("FINAL: Stack + Boost + Mild TTA", m_combo_tta))

    for name, m in rows:
        delta = (m["accuracy"] - m_base["accuracy"]) * 100
        arrow = f"+{delta:.2f} pp" if delta > 0 else f"{delta:.2f} pp"
        gR = m["per_class"]["glioma"]["recall"]
        print(f"{name:<45}  {m['accuracy']:>7.4f}  {m['macro_f1']:>9.4f}  "
              f"{gR:>9.4f}  {arrow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
