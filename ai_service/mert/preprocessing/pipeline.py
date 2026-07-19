from __future__ import annotations

from pathlib import Path

from . import qc
from .bias_correction import n4_bias_correction
from .normalize import resample_and_normalize
from .registration import register_patient_to_t1
from .skull_strip import apply_brain_mask, skull_strip
from .utils import (
    REFERENCE_MODALITY,
    REQUIRED_MODALITIES,
    Patient,
    PreprocessingError,
    logger,
)


def preprocess_patient(
    patient: Patient,
    quarantine_root: Path,
    device: str = "cuda",
) -> Patient:
    logger.info("=== Hasta işleniyor: %s ===", patient.patient_id)

    patient = qc.run_pre_pipeline_qc(patient)
    if qc.quarantine_if_critical(patient, quarantine_root):
        return patient

    ref = REFERENCE_MODALITY
    stripped_ref = patient.stage_output_path("skull_strip", ref)
    mask_path = stripped_ref.with_name(stripped_ref.stem + "_mask.nii.gz")
    skull_strip(patient.modalities[ref], stripped_ref, device=device, save_mask=True)
    patient.processed[ref] = stripped_ref

    n4_ref = patient.stage_output_path("n4", ref)
    n4_bias_correction(stripped_ref, n4_ref)
    patient.processed[ref] = n4_ref

    other_modalities = {
        m: p for m, p in patient.modalities.items() if m != ref
    }
    reg_dir = patient.output_dir / "registered"
    registered = register_patient_to_t1(
        {ref: n4_ref, **other_modalities}, reg_dir, reference_modality=ref
    )

    masked_paths: dict[str, Path] = {}
    for modality, path in registered.items():
        masked_out = patient.stage_output_path("masked", modality)
        if modality == ref:
            import shutil
            shutil.copy(n4_ref, masked_out)
        else:
            apply_brain_mask(path, mask_path, masked_out)
        masked_paths[modality] = masked_out

    patient.processed.update(masked_paths)

    for modality in REQUIRED_MODALITIES:
        final_out = patient.stage_output_path("final", modality)
        resample_and_normalize(patient.processed[modality], final_out)
        patient.processed[modality] = final_out

    logger.info("=== Tamamlandı: %s -> %s ===", patient.patient_id, patient.output_dir / "final")
    return patient


def preprocess_cohort(
    patients: list[Patient],
    quarantine_root: Path,
    device: str = "cuda",
    stop_on_error: bool = False,
) -> tuple[list[Patient], list[tuple[Patient, Exception]]]:
    succeeded: list[Patient] = []
    failed: list[tuple[Patient, Exception]] = []

    for i, patient in enumerate(patients, 1):
        logger.info("[%d/%d] %s", i, len(patients), patient.patient_id)
        try:
            preprocess_patient(patient, quarantine_root, device=device)
            succeeded.append(patient)
        except PreprocessingError as exc:
            logger.error("[%s] Pipeline hatası: %s", patient.patient_id, exc)
            failed.append((patient, exc))
            if stop_on_error:
                raise

    logger.info(
        "Kohort tamamlandı: %d başarılı, %d başarısız (toplam %d)",
        len(succeeded), len(failed), len(patients),
    )
    return succeeded, failed