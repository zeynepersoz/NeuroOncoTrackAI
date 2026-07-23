"""
ai_service/finetune_kaggle.py — Kaggle 4-sınıf head fine-tune
================================================================

v3 predictor'ın distribution shift sorununu çözmek için:
  - MobileNetV2 backbone (ImageNet) DOKUNULMAZ (Zeynep'in v3_predictor.py aynen kalır)
  - RF ve HGB head'lar Kaggle Training seti üzerinde yeniden fit edilir
  - 4 sınıf desteklenir: glioma, meningioma, notumor, pituitary (BraTS'te olmayan)

Çıktı:
  ai_service/finetuned_models_kaggle/
    ├── features_kaggle_train.npz   (1280-D feature cache, tekrar çalıştırmak için)
    ├── rf_kaggle.pkl
    ├── hgb_kaggle.pkl
    └── metrics_kaggle.json

Kullanım:
  python3 ai_service/finetune_kaggle.py \
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


def _iter_class_images(root: Path, split: str, cls: str, limit: int | None = None):
    d = root / split / cls
    if not d.exists():
        d = root / split / cls.replace("notumor", "no_tumor")
        if not d.exists():
            return
    files = sorted(list(d.glob("*.jpg")) + list(d.glob("*.png")))
    if limit:
        files = files[:limit]
    yield from files


def extract_features(root: Path, split: str, limit_per_class: int | None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Kaggle görüntülerinden MobileNet 1280-D feature çıkar."""
    from v2_predictor import _to_grayscale_u8, _kaggle_style_preprocess, _letterbox
    from v3_predictor import _load_cnn

    cnn = _load_cnn()
    feats: list[np.ndarray] = []
    labels: list[int] = []
    filenames: list[str] = []
    t0 = time.perf_counter()

    for ci, cls in enumerate(CLASSES):
        n_cls = 0
        for fpath in _iter_class_images(root, split, cls, limit_per_class):
            img = cv2.imread(str(fpath), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            gray = _to_grayscale_u8(img)
            rgb = _kaggle_style_preprocess(gray)
            lb = _letterbox(rgb, 128).astype(np.float32) / 255.0
            feat = cnn.predict(np.expand_dims(lb, 0), verbose=0)[0]
            feats.append(feat)
            labels.append(ci)
            filenames.append(f"{cls}/{fpath.name}")
            n_cls += 1
            if n_cls % 100 == 0:
                elapsed = time.perf_counter() - t0
                print(f"  {cls:<11} n={n_cls}  toplam={len(feats)}  ({elapsed:.1f}s)")
        print(f"  {cls:<11} tamam: {n_cls} görüntü")

    X = np.array(feats, dtype=np.float32)
    y = np.array(labels, dtype=np.int64)
    print(f"→ Feature matrix: {X.shape}  ({time.perf_counter()-t0:.1f}s)")
    return X, y, filenames


def fit_head(X: np.ndarray, y: np.ndarray, seed: int = 42) -> tuple[object, object]:
    """RF + HGB fit (v3 ile aynı hiperparametreler)."""
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier

    print("→ RandomForest fit ediliyor (600 est, class_weight=balanced)...")
    t = time.perf_counter()
    rf = RandomForestClassifier(
        n_estimators=600, class_weight="balanced",
        random_state=seed, n_jobs=-1,
    )
    rf.fit(X, y)
    print(f"  RF fit: {time.perf_counter()-t:.1f}s")

    print("→ HistGradientBoosting fit ediliyor (max_iter=500)...")
    t = time.perf_counter()
    hgb = HistGradientBoostingClassifier(
        max_iter=500, random_state=seed,
    )
    hgb.fit(X, y)
    print(f"  HGB fit: {time.perf_counter()-t:.1f}s")

    return rf, hgb


def evaluate(X: np.ndarray, y: np.ndarray, rf, hgb, w_rf: float = 0.70) -> dict:
    """Verilen fold üzerinde ensemble metrikleri."""
    w_hgb = 1.0 - w_rf
    p_rf = rf.predict_proba(X)
    p_hgb = hgb.predict_proba(X)
    p = w_rf * p_rf + w_hgb * p_hgb
    pred = p.argmax(axis=1)

    # Confusion matrix
    K = len(CLASSES)
    cm = np.zeros((K, K), dtype=int)
    for t, p_i in zip(y, pred):
        cm[t, p_i] += 1

    # Per-class metrikler
    per_class = {}
    for i, c in enumerate(CLASSES):
        tp = cm[i, i]
        fp = cm[:, i].sum() - tp
        fn = cm[i, :].sum() - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_class[c] = {
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1": round(float(f1), 4),
            "support": int(cm[i, :].sum()),
        }
    acc = float((pred == y).mean())
    return {"accuracy": round(acc, 4), "per_class": per_class,
            "confusion_matrix": cm.tolist(), "labels": CLASSES}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--limit-per-class", type=int, default=None,
                    help="Hızlı test için sınıf başına maks görüntü (None=hepsi)")
    ap.add_argument("--out", default=str(HERE / "finetuned_models_kaggle"))
    ap.add_argument("--force", action="store_true",
                    help="Cached feature'ı yeniden çıkar")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 1) Training feature çıkar (cached) ─────────────────────────────
    train_cache = out_dir / "features_kaggle_train.npz"
    if train_cache.exists() and not args.force:
        print(f"→ Cached feature yükleniyor: {train_cache}")
        d = np.load(train_cache, allow_pickle=True)
        X_tr, y_tr = d["X"], d["y"]
        print(f"  shape={X_tr.shape}")
    else:
        print("→ Training feature çıkarımı (bu 3-5 dakika sürer)...")
        X_tr, y_tr, files_tr = extract_features(root, "Training", args.limit_per_class)
        np.savez_compressed(train_cache, X=X_tr, y=y_tr, files=np.array(files_tr))
        print(f"  cached: {train_cache}")

    # ── 2) RF + HGB fit ────────────────────────────────────────────────
    rf, hgb = fit_head(X_tr, y_tr)
    joblib.dump(rf, out_dir / "rf_kaggle.pkl")
    joblib.dump(hgb, out_dir / "hgb_kaggle.pkl")
    print(f"→ Kaydedildi: rf_kaggle.pkl ({(out_dir / 'rf_kaggle.pkl').stat().st_size/1024/1024:.1f} MB)")
    print(f"→ Kaydedildi: hgb_kaggle.pkl ({(out_dir / 'hgb_kaggle.pkl').stat().st_size/1024/1024:.1f} MB)")

    # ── 3) Training self-fit (sanity) ──────────────────────────────────
    tr_metrics = evaluate(X_tr, y_tr, rf, hgb)
    print(f"\nTraining self-fit accuracy: {tr_metrics['accuracy']:.4f}")

    # ── 4) Testing evaluation ──────────────────────────────────────────
    print("\n→ Testing feature çıkarımı...")
    test_cache = out_dir / "features_kaggle_test.npz"
    if test_cache.exists() and not args.force:
        d = np.load(test_cache, allow_pickle=True)
        X_te, y_te = d["X"], d["y"]
        print(f"  cached: shape={X_te.shape}")
    else:
        X_te, y_te, files_te = extract_features(root, "Testing", args.limit_per_class)
        np.savez_compressed(test_cache, X=X_te, y=y_te, files=np.array(files_te))

    te_metrics = evaluate(X_te, y_te, rf, hgb)
    print(f"\nTesting accuracy: {te_metrics['accuracy']:.4f}")

    print("\nTesting per-class:")
    for c, m in te_metrics["per_class"].items():
        print(f"  {c:<11}  P={m['precision']:.3f}  R={m['recall']:.3f}"
              f"  F1={m['f1']:.3f}  n={m['support']}")

    print("\nTesting confusion matrix:")
    print(" " * 12 + "  ".join(f"{c:>11}" for c in CLASSES))
    for i, c in enumerate(CLASSES):
        print(f"{c:<11}" + "  ".join(f"{te_metrics['confusion_matrix'][i][j]:>11}"
                                       for j in range(len(CLASSES))))

    # ── 5) Metrics kaydet ──────────────────────────────────────────────
    (out_dir / "metrics_kaggle.json").write_text(
        json.dumps({"training": tr_metrics, "testing": te_metrics,
                    "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
                    "classes": CLASSES,
                    "ensemble_weights": {"rf": 0.70, "hgb": 0.30}},
                   indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nMetrics: {out_dir / 'metrics_kaggle.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
