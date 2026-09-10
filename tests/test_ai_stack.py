#!/usr/bin/env python3
"""
tests/test_ai_stack.py — NeuroOncoTrack-AI uçtan uca stack testi
================================================================================
Her özelliği ve "hiçbir alan boş kalmasın" sözleşmesini doğrular. Servisler ayakta
olmalı (docker + backend :8001 + AI :8100 + patoloji :8110; 3D için pod tüneli :8200).

Çalıştırma:
    python tests/test_ai_stack.py
    # veya belirli URL'lerle:
    BACKEND=http://127.0.0.1:8001 AI=http://127.0.0.1:8100 PATH_SVC=http://127.0.0.1:8110 \
    SEG=http://127.0.0.1:8200 python tests/test_ai_stack.py

Çıkış kodu 0 = tümü geçti / atlandı; 1 = en az bir başarısızlık.
"""
from __future__ import annotations

import io
import os
import sys
import time

import httpx
import numpy as np

BACKEND = os.environ.get("BACKEND", "http://127.0.0.1:8001")
AI = os.environ.get("AI", "http://127.0.0.1:8100")
PATH_SVC = os.environ.get("PATH_SVC", "http://127.0.0.1:8110")
SEG = os.environ.get("SEG", "http://127.0.0.1:8200")
DEMO_DIR = os.environ.get(
    "NEURO_DEMO_DIR", "/Users/zeynepersoz/NeuroOncoTrack/test_vakalari/goruntuler")

_PASS, _FAIL, _SKIP = [], [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (_PASS if cond else _FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))


def skip(name: str, why: str) -> None:
    _SKIP.append(name)
    print(f"  ⊘ {name} — atlandı ({why})")


def _up(url: str) -> bool:
    try:
        return httpx.get(f"{url}/health", timeout=5).status_code == 200
    except Exception:
        return False


def _jpg(name: str) -> bytes | None:
    p = os.path.join(DEMO_DIR, name)
    return open(p, "rb").read() if os.path.exists(p) else None


# ── 1. Sağlık ────────────────────────────────────────────────────────
def test_health():
    print("[1] Sağlık kontrolleri")
    for label, url in [("backend :8001", BACKEND), ("ai :8100", AI), ("patoloji :8110", PATH_SVC)]:
        try:
            r = httpx.get(f"{url}/health", timeout=5)
            check(f"health {label}", r.status_code == 200, f"HTTP {r.status_code}")
        except Exception as e:
            check(f"health {label}", False, str(e))


# ── 2. Sınıflandırma (/classify) ─────────────────────────────────────
def test_classify():
    print("[2] Sınıflandırma /classify")
    data = _jpg("03_Gliom_03.jpg")
    if not data:
        return skip("classify", "test görüntüsü yok")
    r = httpx.post(f"{AI}/classify", files={"file": ("g.jpg", data, "image/jpeg")}, timeout=60)
    j = r.json()
    check("classify HTTP 200", r.status_code == 200)
    check("classify tahmin 4 sınıftan biri",
          j.get("prediction") in {"glioma", "meningioma", "notumor", "pituitary"},
          str(j.get("prediction")))
    check("classify olasılık toplamı ~1",
          abs(sum(j.get("probabilities", {}).values()) - 1.0) < 0.05)


# ── 3. Görselli sınıflandırma (/classify_viz) — ön işleme + saliency ──
def test_classify_viz():
    print("[3] /classify_viz — ön işleme adımları + ısı haritası")
    data = _jpg("04_Meningiom_01.jpg")
    if not data:
        return skip("classify_viz", "test görüntüsü yok")
    r = httpx.post(f"{AI}/classify_viz", files={"file": ("m.jpg", data, "image/jpeg")}, timeout=90)
    j = r.json()
    imgs = j.get("images", {})
    for k in ["original", "stripped", "corrected", "normalized", "gradcam", "overlay"]:
        check(f"classify_viz images.{k} dolu", bool(imgs.get(k)))


# ── 4. Çift-LLM rapor (/report) ──────────────────────────────────────
def test_report_dual():
    print("[4] /report — çift-LLM (taslak + denetçi)")
    mo = {"prediction": "meningioma", "prediction_tr": "Menenjiyom",
          "confidence": 0.9, "tumor_volume_cm3": 17.0,
          "probabilities": {"glioma": 0.05, "meningioma": 0.9, "notumor": 0.02, "pituitary": 0.03}}
    r = httpx.post(f"{AI}/report", json={"model_output": mo}, timeout=120)
    p = r.json().get("payload", {})
    dl = p.get("dual_llm", {})
    check("report metni dolu", len(p.get("report", "")) > 50)
    check("report FHIR dolu", bool(p.get("fhir")))
    check("dual_llm taslak sağlayıcı var", bool(dl.get("drafter_provider")))
    check("dual_llm denetçi sağlayıcı var", bool(dl.get("reviewer_provider")))
    check("dual_llm verdict var", dl.get("verdict") in {"onaylandı", "düzeltme_gerekli"} or dl.get("status") == "ok",
          str(dl.get("verdict")))


# ── 5. Patoloji (/predict) — smoke ───────────────────────────────────
def test_pathology():
    print("[5] Patoloji /predict (smoke)")
    if not _up(PATH_SVC):
        return skip("pathology", "servis kapalı")
    import cv2
    arr = (np.random.rand(224, 224, 3) * 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", arr)
    r = httpx.post(f"{PATH_SVC}/predict", files={"file": ("t.png", buf.tobytes(), "image/png")}, timeout=60)
    j = r.json()
    check("pathology HTTP 200", r.status_code == 200)
    check("pathology 9-sınıftan biri",
          j.get("prediction") in {"ADI", "BACK", "DEB", "LYM", "MUC", "MUS", "NORM", "STR", "TUM"},
          str(j.get("prediction")))


# ── 6. Vaka kütüphanesi (/api/library) ───────────────────────────────
def test_library():
    print("[6] /api/library")
    r = httpx.get(f"{BACKEND}/api/library", timeout=10)
    lst = r.json()
    check("library dizi döner", isinstance(lst, list) and len(lst) > 0, f"len={len(lst) if isinstance(lst,list) else 'n/a'}")
    check("library 3D referans vaka içerir", any(x.get("is_3d") for x in lst))


# ── 7. 2D analiz + BOŞ ALAN DENETİMİ (empty-audit) ───────────────────
REQUIRED_TOP = ["diagnosis_tr", "predicted_tumor_type", "confidence", "probs",
                "report", "fhir", "molecular", "features", "dual_llm", "images"]
REQUIRED_IMAGES = ["original", "stripped", "corrected", "normalized", "gradcam", "overlay"]


def test_analyze_2d_no_empty():
    print("[7] /api/analyze 2D — hiçbir alan boş değil (empty-audit)")
    r = httpx.post(f"{BACKEND}/api/analyze", data={"library_id": "01_Gliom_01.jpg"}, timeout=120)
    d = r.json()
    check("analyze HTTP 200", r.status_code == 200)
    for k in REQUIRED_TOP:
        v = d.get(k)
        nonempty = v not in (None, "", {}, [], 0)
        check(f"alan dolu: {k}", nonempty, f"boş ({v!r})")
    for k in REQUIRED_IMAGES:
        check(f"görsel dolu: images.{k}", bool(d.get("images", {}).get(k)))
    mol = d.get("molecular", {})
    check("molecular.idh_status dolu (dürüst durum)", bool(mol.get("idh_status")))
    dl = d.get("dual_llm", {})
    check("dual_llm taslak+denetçi", bool(dl.get("drafter_provider")) and bool(dl.get("reviewer_provider")),
          f"{dl.get('drafter_provider')}/{dl.get('reviewer_provider')}")


# ── 8. Cache — aynı vaka 2. kez LLM'e gitmez ─────────────────────────
def test_cache():
    print("[8] Cache — tekrar seçimde token harcanmaz")
    t0 = time.time(); httpx.post(f"{BACKEND}/api/analyze", data={"library_id": "02_Gliom_02.jpg"}, timeout=120); t1 = time.time()
    r2 = httpx.post(f"{BACKEND}/api/analyze", data={"library_id": "02_Gliom_02.jpg"}, timeout=30); t2 = time.time()
    d2 = r2.json()
    check("2. çağrı cache'ten (cached=True)", d2.get("cached") is True)
    check("2. çağrı belirgin hızlı", (t2 - t1) < (t1 - t0) / 3 + 0.5, f"{t1-t0:.1f}s → {t2-t1:.2f}s")


# ── 9. 3D analiz (pod tüneli varsa) ──────────────────────────────────
def test_analyze_3d():
    print("[9] /api/analyze 3D (pod GPU)")
    if not _up(SEG):
        return skip("analyze_3d", "pod tüneli :8200 kapalı")
    r = httpx.post(f"{BACKEND}/api/analyze", data={"library_id": "3D_MEN_0402"}, timeout=180)
    d = r.json()
    check("3D hacim (cm³) dolu ve >0", isinstance(d.get("volume"), (int, float)) and d["volume"] > 0, str(d.get("volume")))
    check("3D overlay görseli dolu", bool(d.get("images", {}).get("overlay")))
    check("3D eşdeğer çap dolu", d.get("equiv_diameter_cm") is not None)


# ── 10. Backend auth ucu var (kimlik testi — gerçek şifre YOK) ───────
def test_auth_endpoint():
    print("[10] /api/v1/auth/login ucu mevcut (yanlış kimlik → 401, 404 değil)")
    r = httpx.post(f"{BACKEND}/api/v1/auth/login",
                   json={"email": "wrong@test.invalid", "password": "wrongwrong"}, timeout=10)
    # 400/401/422 = uç var ve girdiyi reddetti; 404 = uç yok (asıl hata).
    check("auth/login ucu mevcut (404 değil)", r.status_code != 404, f"HTTP {r.status_code}")


def main():
    print("=" * 64)
    print("NeuroOncoTrack-AI — stack testi")
    print("=" * 64)
    for fn in [test_health, test_classify, test_classify_viz, test_report_dual,
               test_pathology, test_library, test_analyze_2d_no_empty, test_cache,
               test_analyze_3d, test_auth_endpoint]:
        try:
            fn()
        except Exception as e:
            check(fn.__name__, False, f"istisna: {e}")
    print("=" * 64)
    print(f"GEÇTİ: {len(_PASS)}  BAŞARISIZ: {len(_FAIL)}  ATLANDI: {len(_SKIP)}")
    if _FAIL:
        print("Başarısızlar:", ", ".join(_FAIL))
    print("=" * 64)
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
