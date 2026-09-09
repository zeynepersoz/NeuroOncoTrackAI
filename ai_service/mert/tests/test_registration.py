import numpy as np
import pytest
import SimpleITK as sitk

from preprocessing.registration import register_to_reference
from preprocessing.utils import PreprocessingError


def test_register_to_reference_output_matches_fixed_geometry(synthetic_brain_pair, tmp_path):
    fixed_path, moving_path = synthetic_brain_pair
    out_path = tmp_path / "registered.nii.gz"

    register_to_reference(moving_path, fixed_path, out_path)

    fixed = sitk.ReadImage(str(fixed_path))
    result = sitk.ReadImage(str(out_path))

    assert result.GetSize() == fixed.GetSize()
    assert result.GetSpacing() == pytest.approx(fixed.GetSpacing())


def test_register_to_reference_produces_nonzero_output(synthetic_brain_pair, tmp_path):
    fixed_path, moving_path = synthetic_brain_pair
    out_path = tmp_path / "registered.nii.gz"

    register_to_reference(moving_path, fixed_path, out_path)

    result_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(out_path)))
    assert result_arr.max() > 0


def test_register_to_reference_preserves_intensity_range(synthetic_brain_pair, tmp_path):
    fixed_path, moving_path = synthetic_brain_pair
    out_path = tmp_path / "registered.nii.gz"

    moving_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(moving_path)))
    register_to_reference(moving_path, fixed_path, out_path)
    result_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(out_path)))

    assert result_arr.min() >= moving_arr.min() - 1.0
    assert result_arr.max() <= moving_arr.max() + 1.0


def test_register_to_reference_missing_file_raises(tmp_path):
    with pytest.raises(PreprocessingError):
        register_to_reference(
            tmp_path / "missing_moving.nii.gz",
            tmp_path / "missing_fixed.nii.gz",
            tmp_path / "out.nii.gz",
        )