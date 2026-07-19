import numpy as np

from xai.overlay import create_overlay, save_overlay_png, generate_three_plane_overlays


def test_create_overlay_output_shape():
    mr = np.random.rand(64, 64).astype(np.float32)
    cam = np.random.rand(64, 64).astype(np.float32)

    result = create_overlay(mr, cam)

    assert result.shape == (64, 64, 3)


def test_create_overlay_output_dtype():
    mr = np.random.rand(64, 64).astype(np.float32)
    cam = np.random.rand(64, 64).astype(np.float32)

    result = create_overlay(mr, cam)

    assert result.dtype == np.uint8


def test_create_overlay_values_in_range():
    mr = np.random.rand(64, 64).astype(np.float32) * 500
    cam = np.random.rand(64, 64).astype(np.float32)

    result = create_overlay(mr, cam)

    assert result.min() >= 0
    assert result.max() <= 255


def test_save_overlay_png_creates_file(tmp_path):
    mr = np.random.rand(64, 64).astype(np.float32)
    cam = np.random.rand(64, 64).astype(np.float32)
    out_path = tmp_path / "overlay.png"

    result = save_overlay_png(mr, cam, out_path)

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_generate_three_plane_overlays_creates_three_files(tmp_path):
    mr_vol = np.random.rand(32, 32, 32).astype(np.float32)
    cam_vol = np.random.rand(32, 32, 32).astype(np.float32)

    results = generate_three_plane_overlays(mr_vol, cam_vol, tmp_path / "planes")

    assert "axial" in results
    assert "coronal" in results
    assert "sagittal" in results

    for name, path in results.items():
        assert path.exists()
        assert path.suffix == ".png"