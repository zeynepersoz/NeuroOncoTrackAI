from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F


def grad_cam_pp(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    target_layer: torch.nn.Module,
) -> np.ndarray:
    activations = []
    gradients = []

    def fwd_hook(module, inp, out):
        activations.append(out.detach())

    def bwd_hook(module, grad_in, grad_out):
        gradients.append(grad_out[0].detach())

    fwd_handle = target_layer.register_forward_hook(fwd_hook)
    bwd_handle = target_layer.register_full_backward_hook(bwd_hook)

    output = model(input_tensor)

    if output.dim() == 1:
        score = output[0]
    else:
        score = output[0, 0]

    model.zero_grad()
    score.backward()

    fwd_handle.remove()
    bwd_handle.remove()

    act = activations[0]
    grad = gradients[0]

    grad_pow2 = grad.pow(2)
    grad_pow3 = grad.pow(3)

    spatial_dims = tuple(range(2, act.dim()))

    sum_act_grad3 = (act * grad_pow3).sum(dim=spatial_dims, keepdim=True)
    alpha = grad_pow2 / (2 * grad_pow2 + sum_act_grad3 + 1e-7)

    weights = (alpha * F.relu(grad)).sum(dim=spatial_dims)

    cam = F.relu(
        (weights.unsqueeze(-1).unsqueeze(-1).unsqueeze(-1) * act).sum(dim=1, keepdim=True)
    )

    cam = cam.squeeze()
    cam = cam - cam.min()
    if cam.max() > 0:
        cam = cam / cam.max()

    return cam.cpu().numpy()