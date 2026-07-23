"""
ai_service/plot_batch.py — Batch summary.csv'den görsel istatistik üret
=========================================================================

_batch_out/summary.csv üzerinden 4 panelli PNG:
  1. Tümör hacmi (cm³) dağılımı
  2. ET/WT oranı dağılımı
  3. Model güven (confidence) dağılımı
  4. Latency (ms) dağılımı  — log-x

Kullanım:
    python3 ai_service/plot_batch.py
    python3 ai_service/plot_batch.py --csv _batch_out/summary.csv --out figures/
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(csv_path: Path) -> dict[str, list[float]]:
    cols: dict[str, list[float]] = {
        "tumor_volume_cm3": [], "et_wt_ratio": [],
        "confidence": [], "total_ms": [],
    }
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "ok":
                continue
            for k in cols:
                v = row.get(k)
                if v not in (None, ""):
                    try:
                        cols[k].append(float(v))
                    except ValueError:
                        pass
    return cols


def _stats(xs: list[float]) -> str:
    if not xs:
        return "n=0"
    xs2 = sorted(xs)
    med = xs2[len(xs2) // 2]
    mn, mx = xs2[0], xs2[-1]
    return f"n={len(xs)}  median={med:.2f}  min={mn:.2f}  max={mx:.2f}"


def main() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(HERE / "_batch_out" / "summary.csv"))
    ap.add_argument("--out", default=str(HERE / "_batch_out"))
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cols = _load(csv_path)
    print(f"CSV: {csv_path}")
    for k, xs in cols.items():
        print(f"  {k:<20} → {_stats(xs)}")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(
        f"NeuroOncoTrack-AI — BraTS-GLI Kohortu (n={len(cols['confidence'])})",
        fontsize=14, fontweight="bold",
    )

    # 1) Tümör hacmi
    ax = axes[0, 0]
    ax.hist(cols["tumor_volume_cm3"], bins=30, color="#4C72B0", edgecolor="white")
    ax.set_xlabel("Tümör Hacmi (cm³) — BraTS seg ground-truth")
    ax.set_ylabel("Vaka sayısı")
    ax.set_title("Whole-Tumor Hacim Dağılımı")
    ax.axvline(60, ls="--", color="gray", alpha=0.6, label="Literatür medyan aralığı 60–80")
    ax.axvline(80, ls="--", color="gray", alpha=0.6)
    ax.legend(fontsize=9)

    # 2) ET/WT
    ax = axes[0, 1]
    ax.hist(cols["et_wt_ratio"], bins=30, color="#DD8452", edgecolor="white")
    ax.set_xlabel("ET / WT Oranı")
    ax.set_ylabel("Vaka sayısı")
    ax.set_title("Enhancing/Whole-Tumor Oranı — Agresiflik Göstergesi")
    ax.axvline(0.35, ls="--", color="red", alpha=0.6, label="Agresif eşiği ~0.35")
    ax.legend(fontsize=9)

    # 3) Confidence
    ax = axes[1, 0]
    ax.hist(cols["confidence"], bins=30, color="#55A868", edgecolor="white")
    ax.set_xlabel("Model Güveni (glioma)")
    ax.set_ylabel("Vaka sayısı")
    ax.set_title("Sınıflandırma Güven Dağılımı  (recall=100%)")
    ax.axvline(0.5, ls="--", color="red", alpha=0.6, label="karar eşiği 0.5")
    ax.legend(fontsize=9)

    # 4) Latency (log)
    ax = axes[1, 1]
    ax.hist(cols["total_ms"], bins=40, color="#C44E52", edgecolor="white")
    ax.set_xscale("log")
    ax.set_xlabel("Toplam Latency (ms)  — log ölçek")
    ax.set_ylabel("Vaka sayısı")
    ax.set_title("Pipeline Latency Dağılımı")
    ax.axvline(200, ls="--", color="gray", alpha=0.6, label="200 ms hedefi")
    ax.legend(fontsize=9)

    plt.tight_layout(rect=(0, 0, 1, 0.96))
    out_png = out_dir / "batch_distributions.png"
    plt.savefig(out_png, dpi=140, bbox_inches="tight")
    print(f"\nPNG: {out_png}  ({out_png.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
