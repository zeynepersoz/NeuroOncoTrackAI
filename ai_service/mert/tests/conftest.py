from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk


def _make_synthetic_brain(size=(32, 32, 32), spacing=(2.0, 2.0, 2.0), seed=0) -> sitk.Image:
    rng = np.random.default_rng(seed)
    arr = np.zeros(size, dtype=np.float32)

    zz, yy, xx = np.meshgrid(
        np.arange(size[0]), np.arange(size[1]), np.arange(size[2]), indexing="ij"
    )
    center = np.array(size) / 2
    radius = min(size) * 0.35
    dist = np.sqrt(
        (zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2
    )
    brain_mask = dist < radius

    base_intensity = 500.0
    noise = rng.normal(0, 20, size=size)
    arr[brain_mask] = base_intensity + noise[brain_mask]

    bias = 1.0 + 0.15 * (xx / size[2])
    arr = arr * bias

    arr = arr.astype(np.float32)
    image = sitk.GetImageFromArray(arr)
    image.SetSpacing(spacing)
    return image


@pytest.fixture
def synthetic_brain_path(tmp_path: Path) -> Path:
    image = _make_synthetic_brain()
    path = tmp_path / "synthetic_t1.nii.gz"
    sitk.WriteImage(image, str(path))
    return path


def _make_synthetic_brain_shifted(
    size=(64, 64, 64), spacing=(2.0, 2.0, 2.0), seed=0, shift=(0, 0, 0)
) -> sitk.Image:
    rng = np.random.default_rng(seed)
    arr = np.zeros(size, dtype=np.float32)

    zz, yy, xx = np.meshgrid(
        np.arange(size[0]), np.arange(size[1]), np.arange(size[2]), indexing="ij"
    )
    center = np.array(size) / 2 + np.array(shift)
    outer_radius = min(size) * 0.35
    inner_radius = min(size) * 0.18
    dist = np.sqrt(
        (zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2
    )
    outer_mask = dist < outer_radius
    inner_mask = dist < inner_radius

    arr[outer_mask] = 350.0
    arr[inner_mask] = 700.0

    noise = rng.normal(0, 25, size=size)
    arr[outer_mask] += noise[outer_mask]

    arr = arr.astype(np.float32)
    image = sitk.GetImageFromArray(arr)
    image.SetSpacing(spacing)
    return image


@pytest.fixture
def synthetic_brain_pair(tmp_path: Path) -> tuple[Path, Path]:
    fixed = _make_synthetic_brain_shifted(seed=1, shift=(0, 0, 0))
    moving = _make_synthetic_brain_shifted(seed=1, shift=(0, 2, 3))

    fixed_path = tmp_path / "fixed_t1.nii.gz"
    moving_path = tmp_path / "moving_t2.nii.gz"
    sitk.WriteImage(fixed, str(fixed_path))
    sitk.WriteImage(moving, str(moving_path))
    return fixed_path, moving_path