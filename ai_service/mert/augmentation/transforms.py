from __future__ import annotations

from monai.transforms import (
    Compose,
    RandFlipd,
    RandRotate90d,
    RandGaussianNoised,
    RandAdjustContrastd,
    RandAffined,
)


def get_train_transforms() -> Compose:
    return Compose(
        [
            RandFlipd(keys="image", prob=0.5, spatial_axis=0),
            RandRotate90d(keys="image", prob=0.3),
            RandAffined(
                keys="image", prob=0.3,
                rotate_range=0.1, scale_range=0.1,
            ),
            RandGaussianNoised(keys="image", prob=0.2),
            RandAdjustContrastd(keys="image", prob=0.3),
        ]
    )