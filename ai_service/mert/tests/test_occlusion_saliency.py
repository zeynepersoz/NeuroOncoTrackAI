import numpy as np
import pytest

from xai.occlusion_saliency import get_saliency_info, occlusion_saliency


def _fake_predict_bright_top_left(img: np.ndarray) -> dict:
    top_left = img[:32, :32].mean()
    glioma_prob = min(0.95, 0.1 + top_left / 255.0 * 0.8)
    other = (1 - glioma_prob) / 2
    return {
        "prediction": "glioma" if glioma_prob > 0.5 else "notumor",
        "confidence": glioma_prob,
        "probabilities": {"glioma": glioma_prob, "meningioma": other, "notumor": other},
    }


def _fake_predict_constant(img: np.ndarray) -> dict:
    return {
        "prediction": "notumor",
        "confidence": 0.9,
        "probabilities": {"glioma": 0.05, "meningioma": 0.05, "notumor": 0.9},
    }


def test_occlusion_saliency_output_shape():
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    heatmap = occlusion_saliency(image, _fake_predict_constant, patch_size=16, stride=16)
    assert heatmap.shape == (64, 64)


def test_occlusion_saliency_values_in_range():
    image = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    heatmap = occlusion_saliency(image, _fake_predict_bright_top_left, patch_size=16, stride=16)
    assert heatmap.min() >= 0.0
    assert heatmap.max() <= 1.0


def test_occlusion_saliency_finds_important_region():
    image = np.zeros((128, 128, 3), dtype=np.uint8)
    image[:32, :32] = 255

    heatmap = occlusion_saliency(image, _fake_predict_bright_top_left, patch_size=16, stride=8)

    top_left_importance = heatmap[:32, :32].mean()
    bottom_right_importance = heatmap[96:, 96:].mean()
    assert top_left_importance > bottom_right_importance


def test_occlusion_saliency_constant_prediction_gives_flat_map():
    image = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    heatmap = occlusion_saliency(image, _fake_predict_constant, patch_size=16, stride=16)
    assert heatmap.max() == pytest.approx(0.0, abs=1e-6)


def test_occlusion_saliency_rejects_non_3d_image():
    image = np.zeros((64, 64), dtype=np.uint8)
    with pytest.raises(ValueError):
        occlusion_saliency(image, _fake_predict_constant)


def test_occlusion_saliency_respects_target_class():
    image = np.zeros((64, 64, 3), dtype=np.uint8)

    def predict_fn(img):
        return {
            "prediction": "notumor",
            "probabilities": {"glioma": 0.3, "meningioma": 0.3, "notumor": 0.4},
        }

    heatmap_default = occlusion_saliency(image, predict_fn, patch_size=16, stride=16)
    heatmap_glioma = occlusion_saliency(
        image, predict_fn, target_class="glioma", patch_size=16, stride=16
    )
    assert heatmap_default.shape == heatmap_glioma.shape


def test_get_saliency_info_grid_size():
    info = get_saliency_info((128, 128, 3), patch_size=16, stride=8)
    assert info["grid_size"] == [15, 15]
    assert info["total_forward_passes"] == 226


def test_get_saliency_info_non_overlapping():
    info = get_saliency_info((64, 64, 3), patch_size=16, stride=16)
    assert info["grid_size"] == [4, 4]
    assert info["total_forward_passes"] == 17