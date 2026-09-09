from __future__ import annotations

from pathlib import Path

import SimpleITK as sitk

from .utils import PreprocessingError, logger


def n4_bias_correction(
    input_path: Path,
    output_path: Path,
    shrink_factor: int = 4,
    num_fitting_levels: int = 4,
    num_iterations: int = 50,
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise PreprocessingError(f"Girdi dosyası bulunamadı: {input_path}")

    logger.info("N4 bias correction uygulanıyor: %s", input_path.name)

    image = sitk.ReadImage(str(input_path), sitk.sitkFloat32)

    mask_image = sitk.OtsuThreshold(image, 0, 1, 200)

    shrunk_image = sitk.Shrink(image, [shrink_factor] * image.GetDimension())
    shrunk_mask = sitk.Shrink(mask_image, [shrink_factor] * image.GetDimension())

    corrector = sitk.N4BiasFieldCorrectionImageFilter()
    corrector.SetMaximumNumberOfIterations([num_iterations] * num_fitting_levels)

    try:
        corrector.Execute(shrunk_image, shrunk_mask)
    except RuntimeError as exc:
        raise PreprocessingError(
            f"N4 bias correction başarısız oldu ({input_path}): {exc}"
        ) from exc

    log_bias_field = corrector.GetLogBiasFieldAsImage(image)
    corrected_image = image / sitk.Exp(log_bias_field)
    corrected_image = sitk.Cast(corrected_image, sitk.sitkFloat32)

    sitk.WriteImage(corrected_image, str(output_path))
    logger.info("  -> %s (iterasyon: %s)", output_path, corrector.GetElapsedIterations())
    return output_path