from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict

from .utils import PreprocessingError, logger


def _check_dcm2niix_available() -> None:
    if shutil.which("dcm2niix") is None:
        raise PreprocessingError(
            "dcm2niix bulunamadı. Kurulum: 'apt install dcm2niix' veya "
            "'conda install -c conda-forge dcm2niix'."
        )


def convert_dicom_series(dicom_dir: Path, output_dir: Path, series_name: str) -> Path:
    _check_dcm2niix_available()
    dicom_dir = Path(dicom_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not dicom_dir.exists() or not any(dicom_dir.iterdir()):
        raise PreprocessingError(f"DICOM klasörü boş veya yok: {dicom_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "dcm2niix",
            "-z", "y",
            "-f", series_name,
            "-o", tmp,
            "-b", "n",
            str(dicom_dir),
        ]
        logger.info("dcm2niix çalıştırılıyor: %s", dicom_dir.name)
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise PreprocessingError(
                f"dcm2niix başarısız oldu ({dicom_dir}):\n{result.stderr}"
            )

        produced = list(Path(tmp).glob(f"{series_name}*.nii.gz"))
        if not produced:
            raise PreprocessingError(
                f"dcm2niix çalıştı ama .nii.gz üretmedi: {dicom_dir}. "
                f"stdout: {result.stdout[-500:]}"
            )

        final_path = output_dir / f"{series_name}.nii.gz"
        shutil.move(str(produced[0]), str(final_path))
        logger.info("  -> %s", final_path)
        return final_path


def convert_patient(
    dicom_series_dirs: Dict[str, Path], output_dir: Path
) -> Dict[str, Path]:
    results: Dict[str, Path] = {}
    for modality, dicom_dir in dicom_series_dirs.items():
        try:
            results[modality] = convert_dicom_series(dicom_dir, output_dir, modality)
        except PreprocessingError as exc:
            logger.warning("Modalite atlandı (%s): %s", modality, exc)
    return results