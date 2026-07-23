"""
ai_service/eval_4class.py — Kaggle Brain Tumor MRI 4-sınıf değerlendirmesi
============================================================================

Kaggle Nickparvar/brain-tumor-mri-dataset üzerinde v3 predictor için
confusion matrix + per-class precision/recall/F1 hesaplar.

Beklenen dizin yapısı:
    <root>/Testing/glioma/*.jpg
    <root>/Testing/meningioma/*.jpg
    <root>/Testing/pituitary/*.jpg
    <root>/Testing/notumor/*.jpg

Not:
  v3_predictor sadece 3 sınıf döndürür (glioma / meningioma / notumor).
  Kaggle datasetteki 'pituitary' sınıfı v3'te YOK; bu sınıf için
  "beklenen sınıf olmadığından" ayrı bir "pituitary → hangi sınıfa
  yönleniyor?" raporu üretilir.

Kullanım:
    python3 ai_service/eval_4class.py --root ~/data/kaggle/brain-tumor-mri
    python3 ai_service/eval_4class.py --root <path> --limit-per-class 100
    python3 ai_service/eval_4class.py --root <path> --split Training
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "zeynep"))

CLASSES_V3 = ["glioma", "meningioma", "notumor"]
CLASSES_KAGGLE = ["glioma", "meningioma", "notumor", "pituitary"]


def _load_image_gray(path: Path) -> np.ndarray | None:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return img.astype(np.uint8)


def _iter_dataset(root: Path, split: str, limit: int | None):
    split_dir = root / split
    if not split_dir.exists():
        # Bazı Kaggle versiyonlarında split klasörü yok, direkt sınıflar var
        split_dir = root
    for cls in CLASSES_KAGGLE:
        cls_dir = split_dir / cls
        if not cls_dir.exists():
            # Kaggle bazen "no_tumor" yazıyor
            alt = split_dir / cls.replace("notumor", "no_tumor")
            if alt.exists():
                cls_dir = alt
            else:
                print(f"  UYARI: {cls_dir} yok, atlanıyor")
                continue
        files = sorted(list(cls_dir.glob("*.jpg")) + list(cls_dir.glob("*.png")))
        if limit:
            files = files[:limit]
        for f in files:
            yield cls, f


def _confusion(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    idx = {c: i for i, c in enumerate(labels)}
    M = np.zeros((len(labels), len(labels)), dtype=int)
    for t, p in zip(y_true, y_pred):
        if t not in idx or p not in idx:
            continue
        M[idx[t], idx[p]] += 1
    return {"labels": labels, "matrix": M.tolist()}


def _per_class(cm: dict) -> dict:
    labels = cm["labels"]
    M = np.array(cm["matrix"])
    out = {}
    for i, c in enumerate(labels):
        tp = M[i, i]
        fp = M[:, i].sum() - tp
        fn = M[i, :].sum() - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        support = M[i, :].sum()
        out[c] = {
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1": round(float(f1), 4),
            "support": int(support),
        }
    return out


def _accuracy_v3only(y_true: list[str], y_pred: list[str]) -> float:
    """pituitary hariç accuracy (v3 sadece 3 sınıf tanıyor)."""
    ok = 0
    total = 0
    for t, p in zip(y_true, y_pred):
        if t == "pituitary":
            continue
        total += 1
        if t == p:
            ok += 1
    return round(ok / total, 4) if total else 0.0


def _print_cm(cm: dict) -> None:
    labels = cm["labels"]
    M = cm["matrix"]
    w = max(max(len(l) for l in labels), 8)
    print()
    print("Confusion Matrix  (satır=gerçek, sütun=tahmin)")
    print(" " * (w + 2) + "  ".join(f"{l:>{w}}" for l in labels))
    for i, l in enumerate(labels):
        print(f"{l:<{w}}  " + "  ".join(f"{M[i][j]:>{w}}" for j in range(len(labels))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Kaggle dataset kök klasörü")
    ap.add_argument("--split", default="Testing", choices=["Testing", "Training"])
    ap.add_argument("--limit-per-class", type=int, default=None)
    ap.add_argument("--out", default=str(HERE / "_eval_out"))
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    if not root.exists():
        print(f"HATA: {root} yok", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Lazy import (TF yüklemesi burada)
    print("→ v3_predictor yükleniyor (TF cold-start)...")
    t0 = time.perf_counter()
    from v3_predictor import predict_v3
    # warm-up
    predict_v3(np.random.randint(30, 220, (240, 240), dtype=np.uint8))
    print(f"  hazır ({(time.perf_counter()-t0):.1f}s)")

    y_true: list[str] = []
    y_pred: list[str] = []
    y_conf: list[float] = []
    rows: list[dict] = []
    latencies: list[float] = []

    t_start = time.perf_counter()
    n_seen = 0
    n_load_err = 0

    for cls, fpath in _iter_dataset(root, args.split, args.limit_per_class):
        img = _load_image_gray(fpath)
        if img is None:
            n_load_err += 1
            continue
        t = time.perf_counter()
        try:
            out = predict_v3(img)
        except Exception as exc:
            rows.append({"file": str(fpath), "true": cls, "pred": None, "error": str(exc)})
            continue
        dt = (time.perf_counter() - t) * 1000
        latencies.append(dt)
        pred = out["prediction"]
        conf = out.get("confidence", 0.0)
        y_true.append(cls)
        y_pred.append(pred)
        y_conf.append(conf)
        rows.append({
            "file": fpath.name, "true": cls, "pred": pred,
            "confidence": round(conf, 4), "latency_ms": round(dt, 2),
        })
        n_seen += 1
        if n_seen % 50 == 0:
            print(f"  [{n_seen}] {cls:<11} → {pred:<11}  conf={conf:.2f}  {dt:.0f}ms")

    t_end = time.perf_counter()

    # ── raporlama ──
    print()
    print("─" * 70)
    print(f"n={n_seen}  load_err={n_load_err}  toplam={t_end-t_start:.1f}s"
          f"  ort_latency={sum(latencies)/max(len(latencies),1):.1f}ms")

    # Kaggle 4-sınıf CM (pituitary v3'te yok → v3 'meningioma' veya 'glioma' derse
    # "confusion" olarak sayılır; bu davranışı görmek istiyoruz)
    cm_all = _confusion(y_true, y_pred, CLASSES_KAGGLE)
    _print_cm(cm_all)

    # v3 3-sınıf CM (pituitary hariç)
    y_true_v3 = [t for t in y_true if t != "pituitary"]
    y_pred_v3 = [p for t, p in zip(y_true, y_pred) if t != "pituitary"]
    cm_v3 = _confusion(y_true_v3, y_pred_v3, CLASSES_V3)
    print()
    print("v3 3-sınıf (pituitary hariç)")
    _print_cm(cm_v3)

    per_v3 = _per_class(cm_v3)
    acc_v3 = _accuracy_v3only(y_true, y_pred)

    print()
    print("Per-class metrikler (v3 3-sınıf)")
    for c, m in per_v3.items():
        print(f"  {c:<11}  P={m['precision']:.3f}  R={m['recall']:.3f}"
              f"  F1={m['f1']:.3f}  n={m['support']}")
    print(f"  Overall accuracy (pituitary hariç): {acc_v3:.4f}")

    # pituitary yönlenme analizi
    if "pituitary" in y_true:
        pit_preds = [p for t, p in zip(y_true, y_pred) if t == "pituitary"]
        pit_dist = {c: pit_preds.count(c) for c in set(pit_preds)}
        print()
        print(f"pituitary vakalarının v3-tahmin dağılımı (n={len(pit_preds)}):")
        for c, n in sorted(pit_dist.items(), key=lambda x: -x[1]):
            print(f"  → {c:<11}  {n}  ({100*n/len(pit_preds):.1f}%)")

    # dosyaya yaz
    summary = {
        "n_total": n_seen, "n_load_err": n_load_err,
        "wall_time_sec": round(t_end - t_start, 2),
        "confusion_matrix_kaggle4": cm_all,
        "confusion_matrix_v3_3class": cm_v3,
        "per_class_v3": per_v3,
        "accuracy_v3_pituitary_excluded": acc_v3,
        "latency_ms": {
            "n": len(latencies),
            "min": round(min(latencies), 2) if latencies else None,
            "median": round(sorted(latencies)[len(latencies)//2], 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
    }
    (out_dir / "eval_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with open(out_dir / "eval_per_case.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print()
    print(f"JSON: {out_dir / 'eval_summary.json'}")
    print(f"CSV : {out_dir / 'eval_per_case.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
