from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import SimpleITK as sitk

from .utils import PreprocessingError, TARGET_SPACING, logger


def resample_isotropic(
    input_path: Path,
    output_path: Path,
    target_spacing: Tuple[float, float, float] = TARGET_SPACING,
    interpolator: int = sitk.sitkLinear,
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise PreprocessingError(f"Girdi dosyası bulunamadı: {input_path}")

    image = sitk.ReadImage(str(input_path))
    original_spacing = image.GetSpacing()
    original_size = image.GetSize()

    new_size = [
        int(round(osz * ospc / tspc))
        for osz, ospc, tspc in zip(original_size, original_spacing, target_spacing)
    ]

    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputSpacing(target_spacing)
    resampler.SetSize(new_size)
    resampler.SetOutputDirection(image.GetDirection())
    resampler.SetOutputOrigin(image.GetOrigin())
    resampler.SetTransform(sitk.Transform())
    resampler.SetDefaultPixelValue(0.0)
    resampler.SetInterpolator(interpolator)

    resampled = resampler.Execute(image)
    sitk.WriteImage(resampled, str(output_path))
    logger.info(
        "Resample: %s | %s -> %s spacing",
        input_path.name,
        tuple(round(s, 2) for s in original_spacing),
        target_spacing,
    )
    return output_path


def zscore_normalize(
    input_path: Path,
    output_path: Path,
    background_threshold: float = 0.0,
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise PreprocessingError(f"Girdi dosyası bulunamadı: {input_path}")

    image = sitk.ReadImage(str(input_path), sitk.sitkFloat32)
    arr = sitk.GetArrayFromImage(image)

    mask = arr > background_threshold
    if not mask.any():
        raise PreprocessingError(
            f"Z-score normalizasyonu için beyin dokusu bulunamadı: {input_path}. "
            "Kafatası soyma adımı bu görüntüde başarısız olmuş olabilir."
        )

    mean = arr[mask].mean()
    std = arr[mask].std()

    if std < 1e-8:
        raise PreprocessingError(
            f"Standart sapma sıfıra çok yakın ({input_path}); görüntü bozuk olabilir."
        )

    normalized = np.zeros_like(arr, dtype=np.float32)
    normalized[mask] = (arr[mask] - mean) / std

    out_image = sitk.GetImageFromArray(normalized)
    out_image.CopyInformation(image)
    sitk.WriteImage(out_image, str(output_path))

    logger.info(
        "Z-score: %s | mean=%.2f std=%.2f -> %s",
        input_path.name, mean, std, output_path,
    )
    return output_path


def resample_and_normalize(
    input_path: Path,
    output_path: Path,
    target_spacing: Tuple[float, float, float] = TARGET_SPACING,
) -> Path:
    resampled_tmp = output_path.with_suffix("").with_suffix(".resampled.nii.gz")
    resample_isotropic(input_path, resampled_tmp, target_spacing)
    result = zscore_normalize(resampled_tmp, output_path)
    resampled_tmp.unlink(missing_ok=True)
    return result