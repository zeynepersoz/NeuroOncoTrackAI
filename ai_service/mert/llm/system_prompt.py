from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "Sen bir nöroradyoloji YZ destek asistanısın.\n"
    "Girdi: segmentasyon + genomik tahmin sonuçları (JSON) ve getirilen klinik referans belgeleri.\n"
    "\n"
    "Kurallar:\n"
    "- Yalnızca girdi JSON'unu ve getirilen belgeleri kaynak al, dışarıdan bilgi ekleme\n"
    "- Kesin tanı koyma; olasılık/olası ifadesi kullan\n"
    "- Her raporda zorunlu YZ uyarısı yer almalı\n"
    "- Türkçe yaz, standart tıbbi terminoloji kullan\n"
    "- WHO CNS 5 sınıflandırmasını kullan: 'evre' değil 'Grade' (Grade 1, 2, 3, 4)\n"
    "- Segmentasyon alt bölgelerini ilk kullanımda açık yaz:\n"
    "  ET = Enhancing Tumor (kontrast tutan tümör)\n"
    "  WT = Whole Tumor (tüm tümör)\n"
    "  TC = Tumor Core (tümör çekirdeği)\n"
    "- Tümör hacmini cm³ biriminde raporla\n"
    "- ET/WT oranını yüzde olarak belirt\n"
    "\n"
    "Çıktı formatı:\n"
    "1. BULGULAR\n"
    "2. DEĞERLENDİRME\n"
    "3. ÖNERİ\n"
)

REQUIRED_DISCLAIMER = (
    "Bu rapor yapay zeka destekli bir sistem tarafından üretilmiştir. "
    "Kesin tanı niteliği taşımaz ve uzman hekim değerlendirmesi gerektirir."
)

REPORT_SECTIONS = ("BULGULAR", "DEĞERLENDİRME", "ÖNERİ")

FHIR_SECTION_MAP = {
    "BULGULAR": "result",
    "DEĞERLENDİRME": "conclusion",
    "ÖNERİ": "recommendation",
}

FORBIDDEN_PHRASES = (
    "kesinlikle",
    "kesin tanı",
    "teşhis edilmiştir",
    "tanısı konulmuştur",
    "şüphesiz",
    "kuşkusuz",
    "tartışmasız",
)

WRONG_TERMINOLOGY = (
    "evre 1",
    "evre 2",
    "evre 3",
    "evre 4",
    "evre i",
    "evre ii",
    "evre iii",
    "evre iv",
    "stage 1",
    "stage 2",
    "stage 3",
    "stage 4",
)


def format_user_message(model_output: dict, context_docs: list[str]) -> str:
    context_block = "\n---\n".join(context_docs) if context_docs else "Referans belge bulunamadı."

    return (
        f"MODEL ÇIKTISI:\n{json.dumps(model_output, ensure_ascii=False, indent=2)}\n\n"
        f"KLİNİK REFERANS BELGELERİ:\n{context_block}\n\n"
        "Yukarıdaki verilere dayanarak BULGULAR, DEĞERLENDİRME ve ÖNERİ bölümlerinden "
        "oluşan bir radyoloji raporu oluştur. Zorunlu YZ uyarısını raporun sonuna ekle. "
        "WHO CNS sınıflandırmasına göre Grade kullan, evre/stage ifadesi kullanma. "
        "Segmentasyon alt bölgelerini (ET, WT, TC) ilk geçişte açık adlarıyla birlikte yaz."
    )