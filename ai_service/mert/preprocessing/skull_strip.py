from __future__ import annotations

from pathlib import Path

from .utils import PreprocessingError, logger

try:
    from HD_BET.run import run_hd_bet

    _HD_BET_AVAILABLE = True
except ImportError:
    _HD_BET_AVAILABLE = False


def skull_strip(
    input_path: Path,
    output_path: Path,
    device: str = "cuda",
    save_mask: bool = True,
) -> Path:
    if not _HD_BET_AVAILABLE:
        raise PreprocessingError(
            "HD-BET kurulu değil. Kurulum: 'pip install HD-BET'. "
            "Detay: https://github.com/MIC-DKFZ/HD-BET"
        )

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise PreprocessingError(f"Girdi dosyası bulunamadı: {input_path}")

    logger.info("HD-BET çalıştırılıyor (%s, device=%s)", input_path.name, device)
    try:
        run_hd_bet(
            mri_fnames=[str(input_path)],
            output_fnames=[str(output_path)],
            mode="accurate",
            device=device,
            postprocess=True,
            do_tta=True,
            keep_mask=save_mask,
        )
    except Exception as exc:
        raise PreprocessingError(f"HD-BET başarısız oldu ({input_path}): {exc}") from exc

    if not output_path.exists():
        raise PreprocessingError(
            f"HD-BET çalıştı ama çıktı üretmedi (beklenen: {output_path})"
        )

    logger.info("  -> %s", output_path)
    return output_path


def apply_brain_mask(volume_path: Path, mask_path: Path, output_path: Path) -> Path:
    import SimpleITK as sitk

    volume = sitk.ReadImage(str(volume_path))
    mask = sitk.ReadImage(str(mask_path))

    if volume.GetSize() != mask.GetSize():
        raise PreprocessingError(
            f"Volüm ve maske boyutu uyuşmuyor ({volume_path.name}): "
            f"{volume.GetSize()} vs {mask.GetSize()}. "
            "Bu adım co-registration'dan SONRA çalıştırılmalı."
        )

    masked = sitk.Mask(volume, sitk.Cast(mask, sitk.sitkUInt8))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(masked, str(output_path))
    return output_path