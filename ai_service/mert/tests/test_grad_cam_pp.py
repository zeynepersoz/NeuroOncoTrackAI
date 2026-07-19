import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from xai.grad_cam_pp import grad_cam_pp


class Simple3DCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv3d(4, 16, kernel_size=3, padding=1)
        self.conv2 = nn.Conv3d(16, 32, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool3d(1)
        self.fc = nn.Linear(32, 1)

    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = self.pool(x).flatten(1)
        x = self.fc(x)
        return x


def test_grad_cam_pp_returns_numpy():
    model = Simple3DCNN()
    input_vol = torch.randn(1, 4, 16, 16, 16)

    cam = grad_cam_pp(model, input_vol, model.conv2)

    assert isinstance(cam, np.ndarray)


def test_grad_cam_pp_output_shape_matches_spatial():
    model = Simple3DCNN()
    input_vol = torch.randn(1, 4, 16, 16, 16)

    cam = grad_cam_pp(model, input_vol, model.conv2)

    assert cam.shape == (16, 16, 16)


def test_grad_cam_pp_values_between_zero_and_one():
    model = Simple3DCNN()
    input_vol = torch.randn(1, 4, 16, 16, 16)

    cam = grad_cam_pp(model, input_vol, model.conv2)

    assert cam.min() >= 0.0
    assert cam.max() <= 1.0


def test_grad_cam_pp_hooks_cleaned_up():
    model = Simple3DCNN()
    input_vol = torch.randn(1, 4, 16, 16, 16)

    hooks_before = len(model.conv2._forward_hooks)
    grad_cam_pp(model, input_vol, model.conv2)
    hooks_after = len(model.conv2._forward_hooks)

    assert hooks_after == hooks_before