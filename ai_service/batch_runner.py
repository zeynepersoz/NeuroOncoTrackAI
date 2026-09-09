"""
ai_service/batch_runner.py — 355 BraTS-GLI vakası üzerinde toplu pipeline çalışması
=====================================================================================

Amaç:
  1. Pipeline'ın kohort-ölçeğinde stabilitesini kanıtla (kaç vaka başarılı, kaç hatalı)
  2. Seg ground-truth'tan hacim / ET-WT dağılımını çıkar (TEKNOFEST istatistiği)
  3. TF geldiğinde aynı script sınıflandırma metriklerini de raporlar
  4. Vaka-başı JSON + toplu summary.json + kolay-okunur özet CSV üretir

Kullanım:
    python3 ai_service/batch_runner.py                        # tüm 355 vaka
    python3 ai_service/batch_runner.py --limit 20             # ilk 20
    python3 ai_service/batch_runner.py --mode classify_only   # sadece classify (XAI yok)
    python3 ai_service/batch_runner.py --workers 4            # paralel
    python3 ai_service/batch_runner.py --skip-xai             # XAI PNG atma (disk tasarrufu)

Çıktı:
    _batch_out/<patient>/result.json  ← her vaka
    _batch_out/summary.json           ← toplu istatistik
    _batch_out/summary.csv            ← Excel'e açılır tablo
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from smoke_test import (  # noqa: E402
    DEFAULT_TRAIN_DIR,
    _tumor_extra_from_seg,
    find_brats_case,
    list_available_cases,
)


def _process_one(args: tuple) -> dict:
    """Alt işlemde bir vakayı işler (ProcessPoolExecutor için pickle-safe)."""
    patient_id, mode, out_root_str, skip_xai = args
    out_root = Path(out_root_str)
    from bridge import run_pipeline  # bridge is at ai_service/

    try:
        case = find_brats_case(patient_id)
        extras = _tumor_extra_from_seg(case["seg_path"])
        # skip-xai için classify_only iyi bir kısayol (bridge XAI atlar)
        effective_mode = "classify_only" if skip_xai else mode
        result = run_pipeline(
            patient_id=patient_id,
            modality_paths=case["modality_paths"],
            output_dir=out_root / patient_id,
            mode=effective_mode,
            device="auto",
            predictor="v3",
            extra_features=extras or None,
            persist_json=True,
        )
        return {"patient_id": patient_id, "ok": True, "result": result}
    except Exception as exc:
        return {
            "patient_id": patient_id,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _flatten_row(patient_id: str, r: dict | None, error: str | None) -> dict:
    """summary.csv için tek satır."""
    if error is not None:
        return {
            "patient_id": patient_id,
            "status": "load_error",
            "error": error,
            "total_ms": None,
            "prediction": None,
            "confidence": None,
            "tumor_volume_cm3": None,
            "et_wt_ratio": None,
            "tumor_area_ratio_2d": None,
        }
    s = r.get("summary", {})
    stages = r.get("stages", {})
    classify_status = stages.get("classify", {}).get("status", "n/a")
    return {
        "patient_id": patient_id,
        "status": "ok" if classify_status == "ok" else classify_status,
        "error": "; ".join(r.get("errors", [])) or None,
        "total_ms": r.get("total_elapsed_ms"),
        "prediction": s.get("prediction"),
        "confidence": s.get("confidence"),
        "tumor_volume_cm3": s.get("tumor_volume_cm3"),
        "et_wt_ratio": s.get("et_wt_ratio"),
        "tumor_area_ratio_2d": s.get("tumor_area_ratio_2d"),
    }


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs2 = sorted(xs)
    k = (len(xs2) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(xs2) - 1)
    return xs2[lo] if lo == hi else xs2[lo] + (xs2[hi] - xs2[lo]) * (k - lo)


def _aggregate(rows: list[dict], t_start: float, t_end: float) -> dict:
    n_total = len(rows)
    n_load_err = sum(1 for r in rows if r["status"] == "load_error")
    n_classify_ok = sum(1 for r in rows if r["status"] == "ok")
    n_classify_err = sum(1 for r in rows if r["status"] == "error")

    def _col(name: str) -> list[float]:
        return [r[name] for r in rows if r.get(name) is not None]

    vols = _col("tumor_volume_cm3")
    ratios = _col("et_wt_ratio")
    area = _col("tumor_area_ratio_2d")
    latencies = _col("total_ms")

    def _stats(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"n": 0}
        return {
            "n": len(xs),
            "min": round(min(xs), 3),
            "p25": round(_percentile(xs, 25) or 0, 3),
            "median": round(statistics.median(xs), 3),
            "p75": round(_percentile(xs, 75) or 0, 3),
            "max": round(max(xs), 3),
            "mean": round(statistics.fmean(xs), 3),
            "stdev": round(statistics.pstdev(xs), 3) if len(xs) > 1 else 0.0,
        }

    predictions: dict[str, int] = {}
    for r in rows:
        p = r.get("prediction")
        if p:
            predictions[p] = predictions.get(p, 0) + 1

    return {
        "wall_time_sec": round(t_end - t_start, 2),
        "count": {
            "total": n_total,
            "load_error": n_load_err,
            "classify_ok": n_classify_ok,
            "classify_error": n_classify_err,
            "classify_skipped": n_total - n_classify_ok - n_classify_err - n_load_err,
        },
        "prediction_distribution": predictions,
        "latency_ms": _stats(latencies),
        "tumor_volume_cm3": _stats(vols),
        "et_wt_ratio": _stats(ratios),
        "tumor_area_ratio_2d": _stats(area),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="İlk N vaka (varsayılan: tümü)")
    ap.add_argument("--mode", default="classify_only",
                    choices=["full", "fast", "classify_only"],
                    help="Batch için classify_only önerilir (hızlı, disk tasarrufu)")
    ap.add_argument("--out", default=str(HERE / "_batch_out"))
    ap.add_argument("--workers", type=int, default=1,
                    help="Paralel worker sayısı (1 = seri)")
    ap.add_argument("--skip-xai", action="store_true",
                    help="XAI PNG'lerini atlar (mode'u classify_only'ye zorlar)")
    ap.add_argument("--train-dir", default=str(DEFAULT_TRAIN_DIR))
    args = ap.parse_args()

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    train_dir = Path(args.train_dir)
    cases = list_available_cases(train_dir)
    if args.limit:
        cases = cases[: args.limit]

    n = len(cases)
    print(f"→ Vaka: {n}  |  mode={args.mode}  |  workers={args.workers}  |  skip_xai={args.skip_xai}")
    print(f"→ Çıktı: {out_root}")
    print("─" * 70)

    rows: list[dict] = []
    per_case_full: dict[str, dict] = {}
    t_start = time.perf_counter()

    tasks = [(pid, args.mode, str(out_root), args.skip_xai) for pid in cases]

    if args.workers <= 1:
        for i, task in enumerate(tasks, 1):
            entry = _process_one(task)
            _report_case(i, n, entry)
            rows.append(_flatten_row(entry["patient_id"], entry.get("result"), entry.get("error")))
            if entry.get("result"):
                per_case_full[entry["patient_id"]] = entry["result"]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            fut2pid = {pool.submit(_process_one, t): t[0] for t in tasks}
            i = 0
            for fut in as_completed(fut2pid):
                i += 1
                entry = fut.result()
                _report_case(i, n, entry)
                rows.append(_flatten_row(entry["patient_id"], entry.get("result"), entry.get("error")))
                if entry.get("result"):
                    per_case_full[entry["patient_id"]] = entry["result"]

    t_end = time.perf_counter()

    # CSV
    csv_path = out_root / "summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # summary JSON
    agg = _aggregate(rows, t_start, t_end)
    (out_root / "summary.json").write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print()
    print("─" * 70)
    print("SONUÇ")
    print("─" * 70)
    print(json.dumps(agg, indent=2, ensure_ascii=False))
    print()
    print(f"CSV : {csv_path}")
    print(f"JSON: {out_root / 'summary.json'}")
    return 0


def _report_case(i: int, n: int, entry: dict) -> None:
    pid = entry["patient_id"]
    if not entry["ok"]:
        print(f"[{i:>3}/{n}] {pid}  LOAD-ERR  {entry.get('error','')}")
        return
    r = entry["result"]
    cls = r.get("stages", {}).get("classify", {})
    status = cls.get("status", "n/a")
    ms = r.get("total_elapsed_ms", 0)
    pred = r.get("summary", {}).get("prediction")
    vol = r.get("summary", {}).get("tumor_volume_cm3")
    tail = ""
    if pred:
        tail = f"  pred={pred} conf={r['summary'].get('confidence'):.2f}"
    elif status == "error":
        tail = f"  cls-err={cls.get('error','?')[:60]}"
    vol_s = f"vol={vol:>6.2f}cc" if vol is not None else "vol=  n/a "
    print(f"[{i:>3}/{n}] {pid}  {status:<8} {ms:>5.0f}ms  {vol_s}{tail}")


if __name__ == "__main__":
    raise SystemExit(main())
