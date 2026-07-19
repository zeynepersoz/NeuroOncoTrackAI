from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from preprocessing.normalize import resample_isotropic, zscore_normalize
from preprocessing.utils import PreprocessingError


def test_resample_isotropic_changes_spacing(synthetic_brain_path, tmp_path):
    out_path = tmp_path / "resampled.nii.gz"
    resample_isotropic(synthetic_brain_path, out_path, target_spacing=(1.0, 1.0, 1.0))

    result = sitk.ReadImage(str(out_path))
    assert result.GetSpacing() == pytest.approx((1.0, 1.0, 1.0))


def test_resample_preserves_physical_extent(synthetic_brain_path, tmp_path):
    original = sitk.ReadImage(str(synthetic_brain_path))
    original_extent = [
        sz * sp for sz, sp in zip(original.GetSize(), original.GetSpacing())
    ]

    out_path = tmp_path / "resampled.nii.gz"
    resample_isotropic(synthetic_brain_path, out_path, target_spacing=(1.0, 1.0, 1.0))
    result = sitk.ReadImage(str(out_path))
    new_extent = [sz * sp for sz, sp in zip(result.GetSize(), result.GetSpacing())]

    for orig, new in zip(original_extent, new_extent):
        assert new == pytest.approx(orig, rel=0.05)


def test_zscore_normalize_brain_mean_std(synthetic_brain_path, tmp_path):
    out_path = tmp_path / "normalized.nii.gz"
    zscore_normalize(synthetic_brain_path, out_path)

    result = sitk.GetArrayFromImage(sitk.ReadImage(str(out_path)))
    brain_voxels = result[result != 0]

    assert brain_voxels.mean() == pytest.approx(0.0, abs=0.05)
    assert brain_voxels.std() == pytest.approx(1.0, abs=0.05)


def test_zscore_normalize_background_stays_zero(synthetic_brain_path, tmp_path):
    out_path = tmp_path / "normalized.nii.gz"
    zscore_normalize(synthetic_brain_path, out_path)

    original = sitk.GetArrayFromImage(sitk.ReadImage(str(synthetic_brain_path)))
    result = sitk.GetArrayFromImage(sitk.ReadImage(str(out_path)))

    assert np.array_equal(result[original == 0], np.zeros_like(result[original == 0]))


def test_zscore_normalize_raises_on_empty_volume(tmp_path):
    empty = sitk.GetImageFromArray(np.zeros((8, 8, 8), dtype=np.float32))
    empty_path = tmp_path / "empty.nii.gz"
    sitk.WriteImage(empty, str(empty_path))

    with pytest.raises(PreprocessingError):
        zscore_normalize(empty_path, tmp_path / "out.nii.gz")


def test_zscore_normalize_missing_file_raises(tmp_path):
    with pytest.raises(PreprocessingError):
        zscore_normalize(tmp_path / "does_not_exist.nii.gz", tmp_path / "out.nii.gz")