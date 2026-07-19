from pathlib import Path

import SimpleITK as sitk

from preprocessing import qc
from preprocessing.utils import Patient


def _write_dummy(path: Path, size=(10, 10, 10), spacing=(1.0, 1.0, 1.0), all_zero=False):
    import numpy as np
    arr = np.zeros(size, dtype=np.float32) if all_zero else np.ones(size, dtype=np.float32) * 100
    img = sitk.GetImageFromArray(arr)
    img.SetSpacing(spacing)
    path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(img, str(path))


def test_check_modality_completeness_flags_missing(tmp_path):
    p = Patient(
        patient_id="p1",
        modalities={"t1": tmp_path / "t1.nii.gz", "t2": tmp_path / "t2.nii.gz"},
        output_dir=tmp_path / "out",
    )
    issues = qc.check_modality_completeness(p)
    assert len(issues) == 1
    assert "t1c" in issues[0] and "flair" in issues[0]


def test_check_modality_completeness_passes_when_full(tmp_path):
    modalities = {m: tmp_path / f"{m}.nii.gz" for m in ("t1", "t1c", "t2", "flair")}
    p = Patient(patient_id="p2", modalities=modalities, output_dir=tmp_path / "out")
    assert qc.check_modality_completeness(p) == []


def test_check_spacing_consistency_flags_mismatch(tmp_path):
    t1_path = tmp_path / "t1.nii.gz"
    t2_path = tmp_path / "t2.nii.gz"
    _write_dummy(t1_path, spacing=(1.0, 1.0, 1.0))
    _write_dummy(t2_path, spacing=(3.0, 3.0, 3.0))

    p = Patient(
        patient_id="p3",
        modalities={"t1": t1_path, "t2": t2_path},
        output_dir=tmp_path / "out",
    )
    issues = qc.check_spacing_consistency(p, tolerance=0.5)
    assert len(issues) == 1
    assert "t2" in issues[0]


def test_check_empty_slices_flags_mostly_empty_volume(tmp_path):
    path = tmp_path / "t1.nii.gz"
    _write_dummy(path, all_zero=True)

    p = Patient(patient_id="p4", modalities={"t1": path}, output_dir=tmp_path / "out")
    issues = qc.check_empty_slices(p, empty_fraction_threshold=0.3)
    assert len(issues) == 1
    assert "t1" in issues[0]


def test_quarantine_if_critical_moves_incomplete_patient(tmp_path):
    p = Patient(
        patient_id="p5",
        modalities={"t1": tmp_path / "t1.nii.gz"},
        output_dir=tmp_path / "out",
    )
    p.qc_flags.append("Eksik modalite(ler): t1c, t2, flair")

    quarantined = qc.quarantine_if_critical(p, quarantine_root=tmp_path / "quarantine")

    assert quarantined is True
    assert (tmp_path / "quarantine" / "p5" / "qc_report.txt").exists()


def test_quarantine_if_critical_skips_complete_patient(tmp_path):
    modalities = {m: tmp_path / f"{m}.nii.gz" for m in ("t1", "t1c", "t2", "flair")}
    p = Patient(patient_id="p6", modalities=modalities, output_dir=tmp_path / "out")

    quarantined = qc.quarantine_if_critical(p, quarantine_root=tmp_path / "quarantine")

    assert quarantined is False
    assert not (tmp_path / "quarantine" / "p6").exists()