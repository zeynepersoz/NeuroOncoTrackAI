from llm.report_validator import (
    check_disclaimer,
    check_forbidden_phrases,
    check_numeric_consistency,
    check_sections,
    check_wrong_terminology,
    extract_sections,
    map_to_fhir,
    validate_report,
)
from llm.system_prompt import REQUIRED_DISCLAIMER


GOOD_REPORT = (
    "BULGULAR\n"
    "Tümör hacmi 45.2 cm³ olarak hesaplanmıştır.\n\n"
    "DEĞERLENDİRME\n"
    "IDH mutasyonu olasılığı yüksektir.\n\n"
    "ÖNERİ\n"
    "İleri tetkik önerilir.\n\n"
    f"{REQUIRED_DISCLAIMER}"
)


def test_check_disclaimer_present():
    assert check_disclaimer(GOOD_REPORT) is True


def test_check_disclaimer_missing():
    assert check_disclaimer("Sadece bir metin.") is False


def test_check_sections_all_present():
    assert check_sections(GOOD_REPORT) == []


def test_check_sections_missing():
    missing = check_sections("BULGULAR\nBir şeyler.\nÖNERİ\nBir şeyler.")
    assert missing == ["DEĞERLENDİRME"]


def test_check_forbidden_phrases_clean():
    assert check_forbidden_phrases(GOOD_REPORT) == []


def test_check_forbidden_phrases_found():
    bad = "Tümör kesinlikle maligndir. Tanısı konulmuştur."
    found = check_forbidden_phrases(bad)
    assert "kesinlikle" in found
    assert "tanısı konulmuştur" in found


def test_check_forbidden_phrases_ignores_disclaimer():
    report_with_only_disclaimer = f"BULGULAR\nBir şeyler.\n\n{REQUIRED_DISCLAIMER}"
    found = check_forbidden_phrases(report_with_only_disclaimer)
    assert found == []


def test_check_wrong_terminology_clean():
    report = "WHO Grade 4 glioblastom olası tanısı düşünülmektedir."
    found = check_wrong_terminology(report)
    assert found == []


def test_check_wrong_terminology_evre():
    report = "Evre 4 glioblastom tespit edilmiştir."
    found = check_wrong_terminology(report)
    assert "evre 4" in found


def test_check_wrong_terminology_stage():
    report = "Stage 3 astrocytoma considered."
    found = check_wrong_terminology(report)
    assert "stage 3" in found


def test_check_wrong_terminology_roman():
    report = "Evre IV olarak değerlendirilmiştir."
    found = check_wrong_terminology(report)
    assert "evre iv" in found


def test_check_numeric_consistency_pass():
    report = "Tümör hacmi 45.2 cm³ olarak ölçülmüştür."
    issues = check_numeric_consistency(report, {"tumor_volume": 45.2})
    assert issues == []


def test_check_numeric_consistency_mismatch():
    report = "Tümör hacmi 50 cm³ olarak ölçülmüştür."
    issues = check_numeric_consistency(report, {"tumor_volume": 45.2})
    assert len(issues) == 1
    assert "tumor_volume" in issues[0]


def test_extract_sections_all():
    sections = extract_sections(GOOD_REPORT)
    assert "BULGULAR" in sections
    assert "DEĞERLENDİRME" in sections
    assert "ÖNERİ" in sections
    assert "45.2" in sections["BULGULAR"]
    assert "IDH" in sections["DEĞERLENDİRME"]
    assert "tetkik" in sections["ÖNERİ"]


def test_extract_sections_excludes_disclaimer():
    sections = extract_sections(GOOD_REPORT)
    for content in sections.values():
        assert "yapay zeka destekli" not in content


def test_extract_sections_partial():
    partial = "BULGULAR\nBir şeyler.\nÖNERİ\nBaşka şeyler."
    sections = extract_sections(partial)
    assert "BULGULAR" in sections
    assert "ÖNERİ" in sections
    assert "DEĞERLENDİRME" not in sections


def test_map_to_fhir_fields():
    sections = extract_sections(GOOD_REPORT)
    fhir = map_to_fhir(sections)

    assert fhir["resourceType"] == "DiagnosticReport"
    assert fhir["status"] == "preliminary"
    assert fhir["category"] == "radiology"
    assert "45.2" in fhir["result"]
    assert "IDH" in fhir["conclusion"]
    assert "tetkik" in fhir["recommendation"]
    assert fhir["disclaimer"] == REQUIRED_DISCLAIMER


def test_validate_report_valid():
    result = validate_report(GOOD_REPORT, {"tumor_volume": 45.2})
    assert result["is_valid"] is True
    assert result["disclaimer_added"] is False
    assert result["missing_sections"] == []
    assert result["forbidden_phrases"] == []
    assert result["wrong_terminology"] == []
    assert "fhir" in result
    assert result["fhir"]["resourceType"] == "DiagnosticReport"


def test_validate_report_adds_disclaimer():
    no_disclaimer = "BULGULAR\nTest.\nDEĞERLENDİRME\nTest.\nÖNERİ\nTest."
    result = validate_report(no_disclaimer)
    assert result["disclaimer_added"] is True
    assert REQUIRED_DISCLAIMER in result["report"]


def test_validate_report_invalid_forbidden():
    bad = f"BULGULAR\nKesinlikle tümör.\nDEĞERLENDİRME\nTest.\nÖNERİ\nTest.\n{REQUIRED_DISCLAIMER}"
    result = validate_report(bad)
    assert result["is_valid"] is False
    assert "kesinlikle" in result["forbidden_phrases"]


def test_validate_report_invalid_terminology():
    bad = f"BULGULAR\nEvre 4 glioblastom.\nDEĞERLENDİRME\nTest.\nÖNERİ\nTest.\n{REQUIRED_DISCLAIMER}"
    result = validate_report(bad)
    assert result["is_valid"] is False
    assert "evre 4" in result["wrong_terminology"]