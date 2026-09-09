"""
ai_service/warmup.py — Cold-start latency azaltmak için model warm-up
======================================================================

İlk `/infer` çağrısında MobileNetV2 ağırlıklarının indirilmesi + TF grafiği
inşa + RF/HGB pickle load ~2.5-3.5 saniye sürüyor. Bu script sunucu
başlatılırken (veya CLI'dan) çağrılırsa sonraki çağrılar ~100 ms'ye düşer.

Kullanım:
    # Standalone
    python3 ai_service/warmup.py

    # Serve.py içinde (startup event) otomatik çağrılır.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ZEYNEP = HERE / "zeynep"
sys.path.insert(0, str(ZEYNEP))


def warm_v3() -> dict:
    """v3_predictor için TF backbone + RF/HGB pkl'lerini belleğe yükler."""
    t0 = time.perf_counter()
    from v3_predictor import predict_v3  # lazy import
    # 240x240 uint8 sentetik "beyin benzeri" gri görüntü (Otsu maskesi yakalayabilsin)
    rng = np.random.default_rng(42)
    dummy = rng.integers(30, 220, size=(240, 240), dtype=np.uint8)
    t_import = time.perf_counter()
    # İlk predict → CNN + RF + HGB hepsi bellek + graf inşa eder
    out = predict_v3(dummy)
    t_first = time.perf_counter()
    # İkinci predict → sadece cache üzerinden inference
    out2 = predict_v3(dummy)
    t_second = time.perf_counter()
    return {
        "import_ms": round((t_import - t0) * 1000, 1),
        "first_predict_ms": round((t_first - t_import) * 1000, 1),
        "second_predict_ms": round((t_second - t_first) * 1000, 1),
        "total_ms": round((t_second - t0) * 1000, 1),
        "dummy_prediction": out.get("prediction"),
        "dummy_prediction_second": out2.get("prediction"),
    }


def main() -> int:
    print("→ v3 warm-up başlıyor...")
    result = warm_v3()
    print()
    print(f"  import         : {result['import_ms']:>8.1f} ms")
    print(f"  first predict  : {result['first_predict_ms']:>8.1f} ms  (cold)")
    print(f"  second predict : {result['second_predict_ms']:>8.1f} ms  (warm)")
    print(f"  toplam         : {result['total_ms']:>8.1f} ms")
    print()
    speedup = (result["first_predict_ms"] / max(result["second_predict_ms"], 1))
    print(f"→ Cold→Warm hızlanma: {speedup:.1f}×")
    print(f"→ Dummy tahmin (cold): {result['dummy_prediction']}")
    print(f"→ Dummy tahmin (warm): {result['dummy_prediction_second']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
