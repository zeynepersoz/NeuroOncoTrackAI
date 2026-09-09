from __future__ import annotations

import re

from .system_prompt import (
    FHIR_SECTION_MAP,
    FORBIDDEN_PHRASES,
    REPORT_SECTIONS,
    REQUIRED_DISCLAIMER,
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


def check_numeric_consistency(report: str, model_output: dict) -> list[str]:
    mismatches = []
    for key, value in model_output.items():
        if isinstance(value, (int, float)):
            str_value = str(value)
            if str_value not in report:
                mismatches.append(f"{key}: {value}")
    return mismatches


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

    is_valid = (
        len(missing_sections) == 0
        and len(forbidden) == 0
        and len(wrong_terms) == 0
        and len(numeric_issues) == 0
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
        "sections": sections,
        "fhir": fhir,
    }