from __future__ import annotations

import json

TUMOR_TYPE_LABELS = ("glioma", "meningioma", "pituitary", "notumor")

TUMOR_TYPE_TURKISH = {
    "glioma": "gliom",
    "meningioma": "menenjiom",
    "pituitary": "pitüiter adenom",
    "notumor": "tümör bulgusu yok",
}

RESTRICTED_MODE_KEYWORDS = (
    "gliom",
    "menenjiom",
    "meningiom",
    "pitüiter",
    "hipofiz adenom",
)

SYSTEM_PROMPT = (
    "Sen bir nöroradyoloji YZ destek asistanısın.\n"
    "Girdi: bir sınıflandırma modelinin çıktısı (JSON) ve getirilen klinik referans belgeleri.\n"
    "Girdi alanları: decision (classified/uncertain), label (tümör tipi veya null), "
    "confidence, radiomics.volume_cm3, radiomics.et_wt_ratio, reject_reason.\n"
    "\n"
    "Kurallar:\n"
    "- Yalnızca girdi JSON'unu ve getirilen belgeleri kaynak al, dışarıdan bilgi ekleme\n"
    "- Kesin tanı koyma; olasılık/olası ifadesi kullan\n"
    "- Her raporda zorunlu YZ uyarısı yer almalı\n"
    "- Türkçe yaz, standart tıbbi terminoloji kullan\n"
    "- Yalnızca Türkçe alfabesi ve standart noktalama kullan; Çince, Japonca, Korece veya Vietnamca karakter kesinlikle kullanma\n"
    "- 'Detaylı' ve 'spesifik' kelimeleri yerine 'ayrıntılı' kelimesini tercih et\n"
    "- Segmentasyon alt bölgelerini ilk kullanımda açık yaz:\n"
    "  ET = Enhancing Tumor (kontrast tutan tümör)\n"
    "  WT = Whole Tumor (tüm tümör)\n"
    "- Tümör hacmini cm³ biriminde raporla\n"
    "- ET/WT oranını yüzde olarak belirt\n"
    "\n"
    "KISITLI MOD — label alanı null geldiğinde:\n"
    "- Sınıflandırma güven sınırının altında kaldığı için tümör tipi (gliom, menenjiom, "
    "pitüiter adenom gibi) ADINI HİÇ ZİKRETME, tahmin etme, ima etme\n"
    "- Yalnızca radiomics verilerine (hacim, ET/WT oranı) ve Grad-CAM bulgularına dayanarak "
    "tanımlayıcı bir ön değerlendirme yap\n"
    "- BULGULAR ve DEĞERLENDİRME bölümlerinde tümör tipinden bağımsız, sadece morfolojik "
    "gözlemlere (boyut, kontrast tutulumu, konum gibi) yer ver\n"
    "- ÖNERİ bölümünde ek inceleme/uzman değerlendirmesi gerektiğini vurgula\n"
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
    is_restricted = model_output.get("label") is None

    restriction_note = (
        "\n\nÖNEMLİ: label değeri null geldi — KISITLI MOD kurallarını uygula, "
        "tümör tipi adını hiç zikretme."
        if is_restricted
        else ""
    )

    return (
        f"MODEL ÇIKTISI:\n{json.dumps(model_output, ensure_ascii=False, indent=2)}\n\n"
        f"KLİNİK REFERANS BELGELERİ:\n{context_block}\n\n"
        "Yukarıdaki verilere dayanarak BULGULAR, DEĞERLENDİRME ve ÖNERİ bölümlerinden "
        "oluşan bir radyoloji raporu oluştur. Zorunlu YZ uyarısını raporun sonuna ekle."
        f"{restriction_note}"
    )