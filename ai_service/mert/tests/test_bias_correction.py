import numpy as np
import pytest
import SimpleITK as sitk

from preprocessing.bias_correction import n4_bias_correction
from preprocessing.utils import PreprocessingError


def test_n4_bias_correction_runs_and_writes_output(synthetic_brain_path, tmp_path):
    out_path = tmp_path / "n4_corrected.nii.gz"
    result = n4_bias_correction(synthetic_brain_path, out_path, num_iterations=5)

    assert result == out_path
    assert out_path.exists()

    corrected = sitk.ReadImage(str(out_path))
    original = sitk.ReadImage(str(synthetic_brain_path))
    assert corrected.GetSize() == original.GetSize()


def test_n4_bias_correction_reduces_intensity_gradient(synthetic_brain_path, tmp_path):
    out_path = tmp_path / "n4_corrected.nii.gz"
    n4_bias_correction(synthetic_brain_path, out_path, num_iterations=20)

    original_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(synthetic_brain_path)))
    corrected_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(out_path)))

    def left_right_gradient(arr):
        mask = arr > 0
        z, y, x = np.where(mask)
        mid = arr.shape[2] // 2
        left_mean = arr[z[x < mid], y[x < mid], x[x < mid]].mean()
        right_mean = arr[z[x >= mid], y[x >= mid], x[x >= mid]].mean()
        return abs(right_mean - left_mean) / max(abs(left_mean), 1e-6)

    original_gradient = left_right_gradient(original_arr)
    corrected_gradient = left_right_gradient(corrected_arr)

    assert corrected_gradient < original_gradient


def test_n4_bias_correction_missing_file_raises(tmp_path):
    with pytest.raises(PreprocessingError):
        n4_bias_correction(tmp_path / "missing.nii.gz", tmp_path / "out.nii.gz")