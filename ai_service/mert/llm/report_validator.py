from __future__ import annotations

import re

from .system_prompt import (
    FHIR_SECTION_MAP,
    FORBIDDEN_PHRASES,
    REPORT_SECTIONS,
    REQUIRED_DISCLAIMER,
    RESTRICTED_MODE_KEYWORDS,
    WRONG_TERMINOLOGY,
)


def check_disclaimer(report: str) -> bool:
    return REQUIRED_DISCLAIMER in report


def check_sections(report: str) -> list[str]:
    missing = []
    for section in REPORT_SECTIONS:
        if section not in report:
            missing.append(section)
    return missing


def check_forbidden_phrases(report: str) -> list[str]:
    found = []
    report_without_disclaimer = report.replace(REQUIRED_DISCLAIMER, "")
    report_lower = report_without_disclaimer.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in report_lower:
            found.append(phrase)
    return found


def check_wrong_terminology(report: str) -> list[str]:
    found = []
    report_lower = report.lower()
    for term in WRONG_TERMINOLOGY:
        if term in report_lower:
            found.append(term)
    return found


NUMERIC_CONSISTENCY_EXCLUDED_KEYS = ("confidence",)


def check_numeric_consistency(report: str, model_output: dict) -> list[str]:
    mismatches = []
    numeric_fields = {}

    radiomics = model_output.get("radiomics")
    if isinstance(radiomics, dict):
        for key, value in radiomics.items():
            if isinstance(value, (int, float)):
                numeric_fields[f"radiomics.{key}"] = value

    for key, value in model_output.items():
        if key == "radiomics" or key in NUMERIC_CONSISTENCY_EXCLUDED_KEYS:
            continue
        if isinstance(value, (int, float)):
            numeric_fields[key] = value

    for key, value in numeric_fields.items():
        candidates = {str(value)}
        if isinstance(value, float):
            candidates.add(f"{value:.1f}")
            candidates.add(f"{value:.0f}")
            if 0 <= value <= 1:
                candidates.add(str(round(value * 100)))

        if not any(c in report for c in candidates):
            mismatches.append(f"{key}: {value}")

    return mismatches


def check_non_turkish_characters(report: str) -> list[str]:
    allowed = (
        r"A-Za-zÇçĞğİIıöÖşŞüÜ0-9"
        r"\s"
        r".,;:!?()\-–—/%°³²±"
        r"\"'“”‘’…"
        r"\n"
    )
    pattern = re.compile(f"[^{allowed}]")
    matches = pattern.findall(report)
    return list(set(matches))


def check_restricted_mode_violation(report: str, model_output: dict | None) -> list[str]:
    if not model_output or model_output.get("label") is not None:
        return []

    report_lower = report.lower()
    violations = [kw for kw in RESTRICTED_MODE_KEYWORDS if kw in report_lower]
    return violations


def extract_sections(report: str) -> dict[str, str]:
    sections = {}
    report_clean = report.replace(REQUIRED_DISCLAIMER, "").strip()

    for i, section in enumerate(REPORT_SECTIONS):
        start = report_clean.find(section)
        if start == -1:
            continue

        content_start = start + len(section)

        if i + 1 < len(REPORT_SECTIONS):
            next_start = report_clean.find(REPORT_SECTIONS[i + 1])
            if next_start != -1:
                content = report_clean[content_start:next_start]
            else:
                content = report_clean[content_start:]
        else:
            content = report_clean[content_start:]

        sections[section] = content.strip()

    return sections


def map_to_fhir(sections: dict[str, str]) -> dict:
    fhir_report = {
        "resourceType": "DiagnosticReport",
        "status": "preliminary",
        "category": "radiology",
    }

    for our_section, fhir_field in FHIR_SECTION_MAP.items():
        if our_section in sections:
            fhir_report[fhir_field] = sections[our_section]

    fhir_report["disclaimer"] = REQUIRED_DISCLAIMER

    return fhir_report


def validate_report(report: str, model_output: dict | None = None) -> dict:
    has_disclaimer = check_disclaimer(report)
    if not has_disclaimer:
        report = report.rstrip() + "\n\n" + REQUIRED_DISCLAIMER

    missing_sections = check_sections(report)
    forbidden = check_forbidden_phrases(report)
    wrong_terms = check_wrong_terminology(report)
    numeric_issues = check_numeric_consistency(report, model_output) if model_output else []
    non_turkish_chars = check_non_turkish_characters(report)
    restricted_violations = check_restricted_mode_violation(report, model_output)

    is_valid = (
        len(missing_sections) == 0
        and len(forbidden) == 0
        and len(wrong_terms) == 0
        and len(numeric_issues) == 0
        and len(non_turkish_chars) == 0
        and len(restricted_violations) == 0
    )

    sections = extract_sections(report)
    fhir = map_to_fhir(sections) if sections else {}

    return {
        "is_valid": is_valid,
        "report": report,
        "disclaimer_added": not has_disclaimer,
        "missing_sections": missing_sections,
        "forbidden_phrases": forbidden,
        "wrong_terminology": wrong_terms,
        "numeric_mismatches": numeric_issues,
        "non_turkish_characters": non_turkish_chars,
        "restricted_mode_violations": restricted_violations,
        "sections": sections,
        "fhir": fhir,
    }