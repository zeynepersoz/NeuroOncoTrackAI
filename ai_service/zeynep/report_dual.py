"""
zeynep/report_dual.py — Çift-LLM rapor doğrulama (ikinci görüş / bağımsız denetçi)
================================================================================
Zeynep bölümü. Taslağı yazan LLM-A'ya (RAG pipeline) DOKUNMADAN, bağımsız ikinci
bir LLM (LLM-B: denetçi) ekler. Denetçi FARKLI sağlayıcı olabilir — farklı sağlayıcı
halüsinasyonu yakalamada daha güçlüdür (generator ↔ critic).

Denetçi sağlayıcısı (öncelik):
    1) REVIEWER_PROVIDER env  ("anthropic" | "groq")
    2) otomatik: ANTHROPIC_API_KEY varsa → anthropic (Claude), yoksa → groq

Env:
    ANTHROPIC_API_KEY        Claude denetçi için
    ANTHROPIC_REVIEWER_MODEL Claude modeli (vars. claude-sonnet-5)
    GROQ_API_KEY             Groq denetçi (yedek) için
    GROQ_REVIEWER_MODEL      Groq modeli (vars. openai/gpt-oss-20b)
    GROQ_MODEL               LLM-A/taslak modeli (bilgi amaçlı)
    DUAL_LLM                 "0" ise devre dışı (serve.py kontrol eder)

Dış API:
    add_second_opinion(model_output, draft_payload, groq_api_key=None,
                       reviewer_model=None) -> dict   (draft_payload + 'dual_llm')
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

DEFAULT_GROQ_REVIEWER = "openai/gpt-oss-20b"
DEFAULT_ANTHROPIC_REVIEWER = "claude-sonnet-5"

_REVIEWER_SYSTEM = (
    "Sen bir nöro-onkoloji uzmanı gibi davranan BAĞIMSIZ bir klinik rapor "
    "denetçisisin. Görevin, başka bir yapay zekânın yazdığı taslak radyoloji/klinik "
    "raporu, sana verilen YAPISAL MODEL ÇIKTISI (kesin gerçekler) ile karşılaştırıp "
    "doğrulamaktır. Taslağı yeniden yazma; SADECE denetle.\n"
    "Şunları kontrol et:\n"
    "1) Tutarlılık: Taslaktaki tanı, güven, tümör hacmi ve olasılıklar model "
    "çıktısıyla birebir uyuşuyor mu?\n"
    "2) Halüsinasyon: Model çıktısında OLMAYAN sayısal değer, bulgu veya iddia var mı?\n"
    "3) Güvenlik: Kesin/agresif dil, eksik sorumluluk reddi, hatalı terminoloji var mı?\n"
    "Yanıtı SADECE şu şemada geçerli JSON olarak ver, başka metin yazma:\n"
    '{"verdict":"onaylandı|düzeltme_gerekli","agreement_score":0.0,'
    '"factual_issues":[],"hallucinations":[],"safety_flags":[],'
    '"second_opinion":"kısa bağımsız değerlendirme (2-3 cümle, Türkçe)"}'
)


def _facts_block(model_output: dict) -> str:
    """Model çıktısından denetçiye verilecek kesin gerçekleri derler."""
    keys = [
        "prediction", "prediction_tr", "label", "confidence",
        "tumor_volume_cm3", "et_wt_ratio", "reject_reason",
    ]
    facts: dict[str, Any] = {k: model_output[k] for k in keys if k in model_output}
    probs = model_output.get("probabilities") or model_output.get("probs")
    if isinstance(probs, dict):
        facts["probabilities"] = {k: round(float(v), 4) for k, v in probs.items()}
    radiomics = model_output.get("radiomics")
    if isinstance(radiomics, dict):
        facts["radiomics"] = radiomics
    return json.dumps(facts, ensure_ascii=False, indent=2)


def _parse_json(text: str) -> Optional[dict]:
    """LLM çıktısındaki JSON'ı toleranslı ayrıştır (```json blokları dahil)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _reviewer_config(reviewer_model: Optional[str]) -> tuple[str, str]:
    """Sağlayıcı ve model seç. ANTHROPIC_API_KEY varsa Claude, yoksa Groq."""
    provider = (os.environ.get("REVIEWER_PROVIDER") or "").strip().lower()
    if provider not in ("anthropic", "groq"):
        provider = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "groq"
    if provider == "anthropic":
        model = (reviewer_model or os.environ.get("ANTHROPIC_REVIEWER_MODEL")
                 or DEFAULT_ANTHROPIC_REVIEWER)
    else:
        model = (reviewer_model or os.environ.get("GROQ_REVIEWER_MODEL")
                 or DEFAULT_GROQ_REVIEWER)
    return provider, model


def _review_raw(provider: str, model: str, user_msg: str,
                groq_api_key: Optional[str]) -> str:
    """Denetçi LLM'i çağır, ham metin döndür. Sağlayıcıya göre SDK seçer."""
    if provider == "anthropic":
        from anthropic import Anthropic  # type: ignore
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        # Not: Sonnet 5 temperature/top_p KABUL ETMEZ (400) — göndermiyoruz.
        # Thinking adaptif (varsayılan); yalnız text bloklarını topla.
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_REVIEWER_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return ""
        parts = [getattr(b, "text", "") for b in (resp.content or [])
                 if getattr(b, "type", None) == "text"]
        return "".join(parts)

    # groq (yedek / varsayılan)
    from groq import Groq  # type: ignore
    client = Groq(api_key=groq_api_key)
    messages = [{"role": "system", "content": _REVIEWER_SYSTEM},
                {"role": "user", "content": user_msg}]
    # gpt-oss "reasoning"e token harcayıp content'i boş bırakabiliyor → zorla.
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.1,
            max_completion_tokens=2048, reasoning_effort="low",
            response_format={"type": "json_object"})
    except Exception:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.1,
            max_completion_tokens=2048)
    return resp.choices[0].message.content or ""


def add_second_opinion(
    model_output: dict,
    draft_payload: dict,
    groq_api_key: Optional[str] = None,
    reviewer_model: Optional[str] = None,
) -> dict:
    """LLM-A taslağına bağımsız denetçinin (LLM-B) doğrulamasını ekler.

    draft_payload: bridge.generate_report_only(...) çıktısı (içinde .payload.report).
    Dönüş: aynı payload + 'dual_llm' bloğu. Hata/anahtar yoksa taslak aynen döner
    (servis asla çökmemeli — ikinci görüş 'en iyi çaba').
    """
    groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
    provider, reviewer_model = _reviewer_config(reviewer_model)

    payload = draft_payload.get("payload") if isinstance(draft_payload, dict) else None
    draft_report = ""
    if isinstance(payload, dict):
        draft_report = payload.get("report") or ""

    _draft_openai = (os.environ.get("DRAFTER_PROVIDER", "").strip().lower() == "openai"
                     or bool(os.environ.get("OPENAI_API_KEY")))
    drafter_model = (os.environ.get("OPENAI_MODEL", "gpt-4o") if _draft_openai
                     else os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))
    meta = {
        "reviewer_provider": provider,
        "reviewer_model": reviewer_model,
        "drafter_provider": "openai" if _draft_openai else "groq",
        "drafter_model": drafter_model,
    }

    have_key = (bool(os.environ.get("ANTHROPIC_API_KEY")) if provider == "anthropic"
                else bool(groq_api_key))
    if not have_key:
        _attach(draft_payload, {**meta, "status": "skipped",
                                "reason": f"{provider} API anahtarı yok"})
        return draft_payload
    if not draft_report.strip():
        _attach(draft_payload, {**meta, "status": "skipped",
                                "reason": "LLM-A taslağı boş — doğrulanacak metin yok"})
        return draft_payload

    user_msg = (
        "YAPISAL MODEL ÇIKTISI (kesin gerçekler):\n"
        f"{_facts_block(model_output)}\n\n"
        "DENETLENECEK TASLAK RAPOR:\n"
        f"{draft_report}"
    )
    t0 = time.perf_counter()
    try:
        raw = _review_raw(provider, reviewer_model, user_msg, groq_api_key)
        parsed = _parse_json(raw)
        review: dict[str, Any] = {**meta, "status": "ok",
                                  "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}
        if parsed:
            review.update({
                "verdict": parsed.get("verdict"),
                "agreement_score": parsed.get("agreement_score"),
                "factual_issues": parsed.get("factual_issues", []),
                "hallucinations": parsed.get("hallucinations", []),
                "safety_flags": parsed.get("safety_flags", []),
                "second_opinion": parsed.get("second_opinion", ""),
            })
        else:
            review.update({"verdict": None, "second_opinion": (raw or "").strip(),
                           "parse_warning": "JSON ayrıştırılamadı ya da boş yanıt"})
        _attach(draft_payload, review)
    except Exception as exc:  # pragma: no cover
        _attach(draft_payload, {**meta, "status": "error",
                                "error": f"{type(exc).__name__}: {exc}",
                                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)})
    return draft_payload


def _attach(draft_payload: dict, dual_block: dict) -> None:
    """'dual_llm' bloğunu payload'a ve üst seviyeye ekler (backend kolay okusun)."""
    if isinstance(draft_payload, dict):
        payload = draft_payload.get("payload")
        if isinstance(payload, dict):
            payload["dual_llm"] = dual_block
        draft_payload["dual_llm"] = dual_block


if __name__ == "__main__":
    demo_output = {
        "prediction": "meningioma", "prediction_tr": "Menenjiyom",
        "confidence": 0.94, "tumor_volume_cm3": 17.0,
        "probabilities": {"glioma": 0.03, "meningioma": 0.94,
                          "notumor": 0.01, "pituitary": 0.02},
    }
    demo_draft = {"status": "ok", "payload": {"report":
        "Hastada menenjiyom ile uyumlu, ~17 cm³ hacimli ekstra-aksiyel kitle izlenmektedir. "
        "Kesin tanı için histopatolojik korelasyon önerilir."}}
    out = add_second_opinion(demo_output, demo_draft)
    print(json.dumps(out.get("dual_llm"), ensure_ascii=False, indent=2))
