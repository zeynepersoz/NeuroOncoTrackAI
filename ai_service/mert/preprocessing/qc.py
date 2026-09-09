from __future__ import annotations

from pathlib import Path

import SimpleITK as sitk

from .utils import REQUIRED_MODALITIES, Patient, logger


def check_modality_completeness(patient: Patient) -> list[str]:
    issues = []
    missing = patient.missing_modalities()
    if missing:
        issues.append(f"Eksik modalite(ler): {', '.join(missing)}")
    return issues


def check_spacing_consistency(patient: Patient, tolerance: float = 0.5) -> list[str]:
    issues = []
    spacings = {}
    for modality, path in patient.modalities.items():
        try:
            img = sitk.ReadImage(str(path))
            spacings[modality] = img.GetSpacing()
        except RuntimeError as exc:
            issues.append(f"{modality}: dosya okunamadı ({exc})")

    if len(spacings) < 2:
        return issues

    reference = next(iter(spacings.values()))
    for modality, spacing in spacings.items():
        diff = max(abs(a - b) for a, b in zip(spacing, reference))
        if diff > tolerance:
            issues.append(
                f"{modality}: spacing {spacing} referanstan {diff:.2f}mm sapıyor"
            )
    return issues


def check_empty_slices(patient: Patient, empty_fraction_threshold: float = 0.3) -> list[str]:
    issues = []
    for modality, path in patient.modalities.items():
        try:
            img = sitk.ReadImage(str(path))
        except RuntimeError:
            continue

        arr = sitk.GetArrayFromImage(img)
        empty_slices = sum(1 for sl in arr if sl.max() == 0)
        fraction = empty_slices / max(len(arr), 1)
        if fraction > empty_fraction_threshold:
            issues.append(
                f"{modality}: dilimlerin %{fraction*100:.0f}'i boş "
                f"(eşik: %{empty_fraction_threshold*100:.0f})"
            )
    return issues


def run_pre_pipeline_qc(patient: Patient) -> Patient:
    checks = [
        check_modality_completeness,
        check_spacing_consistency,
        check_empty_slices,
    ]
    for check in checks:
        issues = check(patient)
        patient.qc_flags.extend(issues)

    if patient.qc_flags:
        logger.warning(
            "[%s] QC uyarıları (%d): %s",
            patient.patient_id, len(patient.qc_flags), patient.qc_flags,
        )
    else:
        logger.info("[%s] QC: sorun bulunamadı", patient.patient_id)

    return patient


def quarantine_if_critical(patient: Patient, quarantine_root: Path) -> bool:
    critical = not patient.has_all_modalities()
    if not critical:
        return False

    quarantine_dir = Path(quarantine_root) / patient.patient_id
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    (quarantine_dir / "qc_report.txt").write_text(
        "\n".join(patient.qc_flags) or "Eksik modalite (detay yok)"
    )
    logger.error(
        "[%s] Karantinaya alındı (eksik modalite): %s",
        patient.patient_id, quarantine_dir,
    )
    return True