from __future__ import annotations

from pathlib import Path

import SimpleITK as sitk

from .utils import PreprocessingError, logger


def _initial_transform(fixed: sitk.Image, moving: sitk.Image) -> sitk.Transform:
    return sitk.CenteredTransformInitializer(
        fixed,
        moving,
        sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.MOMENTS,
    )


def register_to_reference(
    moving_path: Path,
    fixed_path: Path,
    output_path: Path,
    interpolator: int = sitk.sitkLinear,
) -> Path:
    moving_path = Path(moving_path)
    fixed_path = Path(fixed_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for p in (moving_path, fixed_path):
        if not p.exists():
            raise PreprocessingError(f"Girdi dosyası bulunamadı: {p}")

    logger.info("Registration: %s -> %s", moving_path.name, fixed_path.name)

    fixed = sitk.ReadImage(str(fixed_path), sitk.sitkFloat32)
    moving = sitk.ReadImage(str(moving_path), sitk.sitkFloat32)

    initial_transform = _initial_transform(fixed, moving)

    registration = sitk.ImageRegistrationMethod()
    registration.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
    registration.SetMetricSamplingStrategy(registration.RANDOM)
    registration.SetMetricSamplingPercentage(0.2)
    registration.SetInterpolator(sitk.sitkLinear)

    registration.SetOptimizerAsGradientDescent(
        learningRate=1.0,
        numberOfIterations=200,
        convergenceMinimumValue=1e-6,
        convergenceWindowSize=10,
    )
    registration.SetOptimizerScalesFromPhysicalShift()

    registration.SetShrinkFactorsPerLevel(shrinkFactors=[4, 2, 1])
    registration.SetSmoothingSigmasPerLevel(smoothingSigmas=[2, 1, 0])
    registration.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()

    registration.SetInitialTransform(initial_transform, inPlace=False)

    try:
        final_transform = registration.Execute(fixed, moving)
    except RuntimeError as exc:
        raise PreprocessingError(
            f"Registration başarısız oldu ({moving_path} -> {fixed_path}): {exc}"
        ) from exc

    metric_value = registration.GetMetricValue()
    logger.info(
        "  Kayıt tamamlandı | son metrik: %.4f | durma nedeni: %s",
        metric_value,
        registration.GetOptimizerStopConditionDescription(),
    )

    resampled = sitk.Resample(
        moving,
        fixed,
        final_transform,
        interpolator,
        0.0,
        moving.GetPixelID(),
    )
    sitk.WriteImage(resampled, str(output_path))
    logger.info("  -> %s", output_path)
    return output_path


def register_patient_to_t1(
    modality_paths: dict[str, Path],
    output_dir: Path,
    reference_modality: str = "t1",
) -> dict[str, Path]:
    if reference_modality not in modality_paths:
        raise PreprocessingError(
            f"Referans modalite ({reference_modality}) girdide yok: "
            f"{list(modality_paths)}"
        )

    output_dir = Path(output_dir)
    fixed_path = modality_paths[reference_modality]
    results: dict[str, Path] = {}

    ref_out = output_dir / f"{reference_modality}.nii.gz"
    ref_out.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(sitk.ReadImage(str(fixed_path)), str(ref_out))
    results[reference_modality] = ref_out

    for modality, path in modality_paths.items():
        if modality == reference_modality:
            continue
        out_path = output_dir / f"{modality}.nii.gz"
        results[modality] = register_to_reference(path, fixed_path, out_path)

    return results