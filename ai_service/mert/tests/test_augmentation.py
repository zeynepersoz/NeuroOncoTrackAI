import numpy as np
import torch

from augmentation.transforms import get_train_transforms


def test_get_train_transforms_returns_compose():
    tf = get_train_transforms()
    assert tf is not None


def test_transform_preserves_shape():
    tf = get_train_transforms()
    vol = np.random.rand(4, 32, 32, 32).astype(np.float32)
    sample = {"image": vol}

    out = tf(sample)

    assert out["image"].shape[0] == 4
    assert out["image"].shape[1] == 32
    assert out["image"].shape[2] == 32
    assert out["image"].shape[3] == 32


def test_transform_preserves_dtype():
    tf = get_train_transforms()
    vol = np.random.rand(4, 32, 32, 32).astype(np.float32)
    sample = {"image": vol}

    out = tf(sample)

    assert out["image"].dtype == torch.float32


def test_transform_produces_different_outputs():
    tf = get_train_transforms()
    vol = np.random.rand(4, 32, 32, 32).astype(np.float32)

    out1 = tf({"image": vol.copy()})
    out2 = tf({"image": vol.copy()})

    arr1 = out1["image"].numpy()
    arr2 = out2["image"].numpy()
    assert not np.array_equal(arr1, arr2)