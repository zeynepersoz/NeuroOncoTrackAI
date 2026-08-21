from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PIL import Image


def _make_grid_positions(height: int, width: int, patch_size: int, stride: int):
    ys = list(range(0, max(height - patch_size, 0) + 1, stride))
    xs = list(range(0, max(width - patch_size, 0) + 1, stride))
    if not ys:
        ys = [0]
    if not xs:
        xs = [0]
    return ys, xs


def _occlude(image: np.ndarray, y: int, x: int, patch_size: int, fill_value: np.ndarray) -> np.ndarray:
    occluded = image.copy()
    occluded[y:y + patch_size, x:x + patch_size] = fill_value
    return occluded


def occlusion_saliency(
    image: np.ndarray,
    predict_fn: Callable[[np.ndarray], dict],
    target_class: Optional[str] = None,
    patch_size: int = 16,
    stride: int = 8,
) -> np.ndarray:
    if image.ndim != 3:
        raise ValueError(f"Görüntü 3 boyutlu (H, W, C) olmalı, gelen şekil: {image.shape}")

    height, width = image.shape[:2]
    fill_value = image.mean(axis=(0, 1)).astype(image.dtype)

    baseline_result = predict_fn(image)
    if target_class is None:
        target_class = baseline_result["prediction"]
    baseline_prob = baseline_result["probabilities"][target_class]

    ys, xs = _make_grid_positions(height, width, patch_size, stride)
    grid = np.zeros((len(ys), len(xs)), dtype=np.float32)

    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            occluded_image = _occlude(image, y, x, patch_size, fill_value)
            occluded_result = predict_fn(occluded_image)
            occluded_prob = occluded_result["probabilities"][target_class]
            grid[i, j] = baseline_prob - occluded_prob

    grid = np.clip(grid, a_min=0, a_max=None)
    if grid.max() > 0:
        grid = grid / grid.max()

    grid_img = Image.fromarray(grid, mode="F")
    resized = grid_img.resize((width, height), resample=Image.BILINEAR)
    heatmap = np.array(resized, dtype=np.float32)

    return heatmap


def get_saliency_info(image_shape, patch_size: int = 16, stride: int = 8) -> dict:
    height, width = image_shape[:2]
    ys, xs = _make_grid_positions(height, width, patch_size, stride)
    return {
        "grid_size": [len(ys), len(xs)],
        "total_forward_passes": len(ys) * len(xs) + 1,
        "patch_size": patch_size,
        "stride": stride,
    }