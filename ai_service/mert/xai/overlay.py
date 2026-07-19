from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def create_overlay(
    mr_slice: np.ndarray,
    cam_slice: np.ndarray,
    alpha: float = 0.4,
    colormap: str = "jet",
) -> np.ndarray:
    mr_normalized = mr_slice.copy().astype(np.float32)
    if mr_normalized.max() > mr_normalized.min():
        mr_normalized = (mr_normalized - mr_normalized.min()) / (
            mr_normalized.max() - mr_normalized.min()
        )

    mr_rgb = np.stack([mr_normalized] * 3, axis=-1)

    cmap = matplotlib.colormaps[colormap]
    cam_colored = cmap(cam_slice.astype(np.float32))[:, :, :3]

    blended = (1 - alpha) * mr_rgb + alpha * cam_colored
    blended = np.clip(blended, 0, 1)

    return (blended * 255).astype(np.uint8)


def save_overlay_png(
    mr_slice: np.ndarray,
    cam_slice: np.ndarray,
    output_path: Path,
    alpha: float = 0.4,
    colormap: str = "jet",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    blended = create_overlay(mr_slice, cam_slice, alpha, colormap)
    img = Image.fromarray(blended)
    img.save(str(output_path))

    return output_path


def generate_three_plane_overlays(
    mr_volume: np.ndarray,
    cam_volume: np.ndarray,
    output_dir: Path,
    alpha: float = 0.4,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    results = {}

    mid_z = mr_volume.shape[0] // 2
    results["axial"] = save_overlay_png(
        mr_volume[mid_z], cam_volume[mid_z],
        output_dir / "axial.png", alpha,
    )

    mid_y = mr_volume.shape[1] // 2
    results["coronal"] = save_overlay_png(
        mr_volume[:, mid_y, :], cam_volume[:, mid_y, :],
        output_dir / "coronal.png", alpha,
    )

    mid_x = mr_volume.shape[2] // 2
    results["sagittal"] = save_overlay_png(
        mr_volume[:, :, mid_x], cam_volume[:, :, mid_x],
        output_dir / "sagittal.png", alpha,
    )

    return results