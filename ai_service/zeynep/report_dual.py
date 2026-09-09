"""
zeynep/report_dual.py — Çift-LLM rapor doğrulama (ikinci görüş)
================================================================================
Zeynep bölümü. Mert'in RAG pipeline'ına (LLM-A: taslak yazar) DOKUNMADAN,
bağımsız ikinci bir LLM (LLM-B: doğrulayıcı / ikinci görüş) ekler.

Akış:
    1) LLM-A (varsayılan openai/gpt-oss-120b)  → RAG raporu taslağı  (bridge/serve üretir)
    2) LLM-B (varsayılan openai/gpt-oss-20b)   → bağımsız klinik doğrulama:
         - taslak, model çıktısındaki GERÇEKLERLE (tanı, güven, hacim, olasılıklar)
           tutarlı mı?
         - halüsinasyon / dayanaksız iddia var mı?
         - kısa bağımsız ikinci görüş + güvenlik bayrakları

İki farklı model kullanmak, tek modele göre halüsinasyonu yakalamada daha güçlüdür
(generator ↔ critic deseni). Her iki model de Groq üzerinden çalışır; sağlayıcı/model
env ile değiştirilebilir (sonradan OpenAI/Gemini/Anthropic'e taşımak kolay).

Env:
    GROQ_API_KEY            zorunlu (yoksa ikinci görüş atlanır, taslak aynen döner)
    GROQ_MODEL              LLM-A (bilgi amaçlı; taslağı serve/bridge üretir)
    GROQ_REVIEWER_MODEL     LLM-B (varsayılan openai/gpt-oss-20b)
    DUAL_LLM                "0" ise devre dışı (serve.py kontrol eder)

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

DEFAULT_REVIEWER_MODEL = "openai/gpt-oss-20b"

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


def add_second_opinion(
    model_output: dict,
    draft_payload: dict,
    groq_api_key: Optional[str] = None,
    reviewer_model: Optional[str] = None,
) -> dict:
    """LLM-A taslağına LLM-B'nin bağımsız doğrulamasını ekler.

    draft_payload: bridge.generate_report_only(...) çıktısı (içinde .payload.report).
    Dönüş: aynı payload + 'dual_llm' bloğu. Hata/anahtar yoksa taslak aynen döner
    (servis asla çökmemeli — ikinci görüş 'en iyi çaba').
    """
    groq_api_key = groq_api_key or os.environ.get("GROQ_API_KEY")
    reviewer_model = (
        reviewer_model
        or os.environ.get("GROQ_REVIEWER_MODEL")
        or DEFAULT_REVIEWER_MODEL
    )

    # draft_payload StageResult.asdict() → {"status","payload":{...},...}
    payload = draft_payload.get("payload") if isinstance(draft_payload, dict) else None
    draft_report = ""
    if isinstance(payload, dict):
        draft_report = payload.get("report") or ""

    meta = {
        "reviewer_model": reviewer_model,
        "drafter_model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    }

    if not groq_api_key:
        _attach(draft_payload, {**meta, "status": "skipped",
                                "reason": "GROQ_API_KEY yok"})
        return draft_payload
    if not draft_report.strip():
        _attach(draft_payload, {**meta, "status": "skipped",
                                "reason": "LLM-A taslağı boş — doğrulanacak metin yok"})
        return draft_payload

    t0 = time.perf_counter()
    try:
        from groq import Groq  # type: ignore
        client = Groq(api_key=groq_api_key)
        user_msg = (
            "YAPISAL MODEL ÇIKTISI (kesin gerçekler):\n"
            f"{_facts_block(model_output)}\n\n"
            "DENETLENECEK TASLAK RAPOR:\n"
            f"{draft_report}"
        )
        messages = [
            {"role": "system", "content": _REVIEWER_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        # gpt-oss modelleri "reasoning" kanalına token harcayıp content'i boş
        # bırakabiliyor → reasoning_effort=low + json_object ile zorluyoruz.
        # Bunları desteklemeyen sağlayıcıda (OpenAI/Gemini) sade çağrıya düşer.
        try:
            resp = client.chat.completions.create(
                model=reviewer_model, messages=messages,
                temperature=0.1, max_completion_tokens=2048,
                reasoning_effort="low",
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = client.chat.completions.create(
                model=reviewer_model, messages=messages,
                temperature=0.1, max_completion_tokens=2048,
            )
        raw = resp.choices[0].message.content or ""
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
            # JSON çıkmadıysa ham metni ikinci görüş olarak sakla
            review.update({"verdict": None, "second_opinion": raw.strip(),
                           "parse_warning": "JSON ayrıştırılamadı, ham metin döndü"})
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
    # Basit elle test: sahte model çıktısı + sahte taslak
    demo_output = {
        "prediction": "meningioma", "prediction_tr": "menenjiyom",
        "confidence": 0.94, "tumor_volume_cm3": 32.5,
        "probabilities": {"glioma": 0.02, "meningioma": 0.94,
                          "notumor": 0.01, "pituitary": 0.03},
    }
    demo_draft = {"status": "ok", "payload": {"report":
        "Hastada menenjiyom ile uyumlu, yaklaşık 32.5 cm³ hacimli kitle izlenmektedir. "
        "Güven düzeyi %94'tür. Kesin tanı için histopatolojik korelasyon önerilir."}}
    out = add_second_opinion(demo_output, demo_draft)
    print(json.dumps(out["dual_llm"], ensure_ascii=False, indent=2))
