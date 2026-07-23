"""
ai_service/plot_confusion.py — Confusion matrix heatmap PNG
=============================================================

Bir eval_summary.json veya metrics_kaggle.json içindeki confusion matrix'i
profesyonel heatmap PNG olarak render eder (TEKNOFEST sunumu için).

Kullanım:
  # v3 base (BraTS-only) sonucu
  python3 ai_service/plot_confusion.py \
      --json _eval_out/eval_summary.json --key confusion_matrix_kaggle4 \
      --title "v3 (BraTS-only) — Kaggle Testing" --out _eval_out/cm_base.png

  # Finetune sonucu
  python3 ai_service/plot_confusion.py \
      --json finetuned_models_kaggle/metrics_kaggle.json --key testing.confusion_matrix \
      --title "v3+Kaggle-finetune — Testing" --out _eval_out/cm_finetune.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _get(d: dict, dotted_key: str):
    cur = d
    for part in dotted_key.split("."):
        cur = cur[part]
    return cur


def main() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--key", default="confusion_matrix",
                    help="dotted path: örn 'testing.confusion_matrix' veya 'confusion_matrix_kaggle4'")
    ap.add_argument("--labels-key", default=None,
                    help="Otomatik bulunmazsa: örn 'testing.labels'")
    ap.add_argument("--title", default="Confusion Matrix")
    ap.add_argument("--out", required=True)
    ap.add_argument("--normalize", action="store_true",
                    help="Satır bazında normalize et (recall görselleştirmesi)")
    args = ap.parse_args()

    data = json.loads(Path(args.json).read_text())
    cm_obj = _get(data, args.key)

    # cm_obj ya {"labels": [...], "matrix": [[...]]} ya da direkt list-of-list olabilir
    if isinstance(cm_obj, dict) and "matrix" in cm_obj:
        M = np.array(cm_obj["matrix"])
        labels = cm_obj.get("labels")
    else:
        M = np.array(cm_obj)
        labels = None

    if labels is None:
        if args.labels_key:
            labels = _get(data, args.labels_key)
        elif "labels" in data:
            labels = data["labels"]
        elif "testing" in data and "labels" in data["testing"]:
            labels = data["testing"]["labels"]
        else:
            labels = [f"c{i}" for i in range(len(M))]

    disp = M.astype(float)
    fmt = "d"
    if args.normalize:
        row_sum = disp.sum(axis=1, keepdims=True)
        row_sum[row_sum == 0] = 1
        disp = disp / row_sum
        fmt = ".2f"

    fig, ax = plt.subplots(figsize=(1.5 * len(labels) + 3, 1.5 * len(labels) + 2))
    im = ax.imshow(disp, cmap="Blues", vmin=0)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Vaka sayısı" if not args.normalize else "Oran")

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    ax.set_xlabel("Tahmin edilen sınıf")
    ax.set_ylabel("Gerçek sınıf")
    ax.set_title(args.title, fontsize=13, fontweight="bold", pad=14)

    # Hücrelere sayı yaz
    thresh = disp.max() / 2.0
    for i in range(len(labels)):
        for j in range(len(labels)):
            v_raw = M[i, j]
            v = disp[i, j]
            txt = f"{v:{fmt}}" if args.normalize else f"{int(v_raw)}"
            ax.text(j, i, txt, ha="center", va="center",
                    color="white" if v > thresh else "#333",
                    fontsize=11, fontweight="bold")

    # Alt bilgi: diyagonal toplamı
    diag = int(np.trace(M))
    total = int(M.sum())
    acc = diag / total if total else 0
    ax.text(0.02, -0.15, f"Overall accuracy: {acc:.3f}  ({diag}/{total})",
            transform=ax.transAxes, fontsize=10, color="#555")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    print(f"PNG: {out_path}  ({out_path.stat().st_size/1024:.1f} KB)  acc={acc:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
