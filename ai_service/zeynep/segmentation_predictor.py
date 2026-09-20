"""
zeynep/segmentation_predictor.py — Meningiom GTV segmentasyonu (2D U-Net, PyTorch)
================================================================================
Zeynep bölümü. Üründeki SAHTE "ResUNet segmentasyon / Hacim / overlay"i GERÇEK yapar.

Model: BraTS-MEN-RT üzerinde eğitilmiş 2D U-Net (T1c → GTV), `finetuned_models/unet_men.pt`.
Checkpoint {"state_dict", "size"} taşır; giriş boyutu buradan okunur (128/192/256 uyumlu).

Dış API:
  segment_slice(img_2d)      -> {mask (H,W uint8), tumor_fraction, latency_ms}
  segment_nifti(t1c_path)    -> {volume_cm3 (GERÇEK voksel), num_tumor_slices,
                                 best_slice, mask_shape, latency_ms}
  get_segmentation_info()    -> model meta

Torch/nibabel yoksa graceful: modül import edilir, çağrıda RuntimeError döner.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_MODEL_PATH = _HERE / "finetuned_models" / "unet_men.pt"

_MODEL = None
_SIZE = 128
_DEVICE = None


# ─── U-Net mimarisi (eğitimle birebir; self-contained) ─────────────────────────
def _build_unet():
    import torch.nn as nn

    def conv_block(i, o):
        return nn.Sequential(
            nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
            nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        def __init__(self, ch=(16, 32, 64, 128)):
            super().__init__()
            self.e1, self.e2, self.e3 = conv_block(1, ch[0]), conv_block(ch[0], ch[1]), conv_block(ch[1], ch[2])
            self.bott = conv_block(ch[2], ch[3])
            self.pool = nn.MaxPool2d(2)
            self.u3 = nn.ConvTranspose2d(ch[3], ch[2], 2, 2); self.d3 = conv_block(ch[3], ch[2])
            self.u2 = nn.ConvTranspose2d(ch[2], ch[1], 2, 2); self.d2 = conv_block(ch[2], ch[1])
            self.u1 = nn.ConvTranspose2d(ch[1], ch[0], 2, 2); self.d1 = conv_block(ch[1], ch[0])
            self.out = nn.Conv2d(ch[0], 1, 1)

        def forward(self, x):
            import torch
            e1 = self.e1(x); e2 = self.e2(self.pool(e1)); e3 = self.e3(self.pool(e2))
            b = self.bott(self.pool(e3))
            d3 = self.d3(torch.cat([self.u3(b), e3], 1))
            d2 = self.d2(torch.cat([self.u2(d3), e2], 1))
            d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
            return self.out(d1)

    return UNet()


def _get_device():
    import torch
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _load_model():
    global _MODEL, _SIZE, _DEVICE
    if _MODEL is not None:
        return _MODEL
    if not _MODEL_PATH.exists():
        raise RuntimeError(f"Segmentasyon modeli yok: {_MODEL_PATH}. Önce U-Net eğitilmeli.")
    import torch
    _DEVICE = _get_device()
    ckpt = torch.load(_MODEL_PATH, map_location=_DEVICE)
    _SIZE = int(ckpt.get("size", 128))
    model = _build_unet()
    model.load_state_dict(ckpt["state_dict"])
    model.to(_DEVICE).eval()
    _MODEL = model
    return _MODEL


# ─── Yardımcılar ───────────────────────────────────────────────────────────────
def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        img = img.mean(axis=2)
    return img.astype(np.float32)


def _norm(vol: np.ndarray) -> np.ndarray:
    pos = vol[vol > 0]
    lo, hi = (np.percentile(pos, (1, 99)) if pos.size else (0.0, 1.0))
    vol = np.clip(vol, lo, hi)
    return ((vol - lo) / (hi - lo + 1e-6)).astype(np.float32)


def _infer_batch(slices_norm: np.ndarray, thr: float = 0.5) -> np.ndarray:
    """slices_norm: (N, H0, W0) normalize [0,1] → maske (N, H0, W0) uint8 (orijinal boyutta)."""
    import torch
    import torch.nn.functional as F
    model = _load_model()
    H0, W0 = slices_norm.shape[1:]
    x = torch.from_numpy(slices_norm)[:, None].float()
    x = F.interpolate(x, size=(_SIZE, _SIZE), mode="bilinear", align_corners=False).to(_DEVICE)
    with torch.no_grad():
        p = torch.sigmoid(model(x))
        p = F.interpolate(p, size=(H0, W0), mode="bilinear", align_corners=False)
    return (p[:, 0].cpu().numpy() > thr).astype(np.uint8)


def _postprocess_3d(mask3d: np.ndarray, min_voxels: int = 200, keep_largest: bool = True) -> np.ndarray:
    """
    3B bağlantılı-bileşen temizliği: dağınık yanlış-pozitif adacıkları at.
    Meningiom genelde tek kütle → varsayılan en büyük bileşeni tut.
    scipy yoksa maskeyi olduğu gibi döndürür (graceful).
    """
    try:
        from scipy import ndimage
    except Exception:
        return mask3d
    labels, n = ndimage.label(mask3d)
    if n == 0:
        return mask3d
    sizes = ndimage.sum(np.ones_like(mask3d), labels, index=np.arange(1, n + 1))
    if keep_largest:
        keep = {int(np.argmax(sizes)) + 1}
    else:
        keep = {i + 1 for i, s in enumerate(sizes) if s >= min_voxels}
    out = np.isin(labels, list(keep)).astype(np.uint8)
    return out


# ─── Dış API ───────────────────────────────────────────────────────────────────
def segment_slice(img_2d: np.ndarray) -> dict:
    """Tek 2D kesitten GTV maskesi (orijinal boyutta) + tümör piksel oranı."""
    t0 = time.perf_counter()
    gray = _norm(_to_gray(img_2d))
    mask = _infer_batch(gray[None])[0]
    return {
        "mask": mask,
        "tumor_fraction": float(mask.mean()),
        "size": _SIZE,
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


# ─── nnU-Net 3D (birincil, Dice 0.807) — model varsa kullanılır ───────────────
# Model klasörü git'e giremeyecek kadar büyük (checkpoint ~123MB); lokal/harici
# dağıtılır. Yoksa otomatik 2D U-Net'e (Dice 0.75) düşülür.
_NNUNET_DIR = _HERE / "finetuned_models" / "nnunet_men" / "nnUNetTrainer__nnUNetPlans__3d_fullres"
_NNUNET = None
_NNUNET_TRIED = False


def _load_nnunet():
    """nnUNetPredictor'ı lazy yükle. nnunetv2 yoksa veya model yoksa None döner."""
    global _NNUNET, _NNUNET_TRIED
    if _NNUNET_TRIED:
        return _NNUNET
    _NNUNET_TRIED = True
    ckpt = _NNUNET_DIR / "fold_0" / "checkpoint_best.pth"
    if not ckpt.exists():
        return None
    try:
        import os
        import torch
        # nnU-Net 3D çıkarımı CPU'da pratik değil (~dk/vaka). Yalnız CUDA'da kullan;
        # aksi halde None → hızlı 2D U-Net fallback. NNUNET_FORCE_CPU=1 ile zorlanabilir.
        if not torch.cuda.is_available() and os.environ.get("NNUNET_FORCE_CPU") != "1":
            return None
        from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
        dev = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        pred = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=True,
                               perform_everything_on_device=(dev.type == "cuda"), device=dev)
        pred.initialize_from_trained_model_folder(str(_NNUNET_DIR), use_folds=(0,),
                                                  checkpoint_name="checkpoint_best.pth")
        _NNUNET = pred
    except Exception as exc:  # pragma: no cover
        print(f"[seg] nnU-Net yüklenemedi, 2D'ye düşülüyor: {exc}")
        _NNUNET = None
    return _NNUNET


def _segment_nifti_nnunet(t1c_path: str):
    """nnU-Net 3D ile segmentasyon + gerçek hacim. Başarısızsa None (2D'ye düş)."""
    pred = _load_nnunet()
    if pred is None:
        return None
    try:
        import time as _t
        from nnunetv2.imageio.simpleitk_reader_writer import SimpleITKIO
        t0 = _t.perf_counter()
        img, props = SimpleITKIO().read_images([str(t1c_path)])
        seg = pred.predict_single_npy_array(img, props, None, None, False)
        seg = _postprocess_3d((seg > 0).astype(np.uint8), keep_largest=True)
        spacing = props["spacing"]  # mm; sıra fark etmez (hacim = çarpım)
        voxel_cm3 = float(np.prod(spacing)) / 1000.0
        tumor_voxels = int(seg.sum())
        ax = int(np.argmin(seg.shape))  # en ince eksen ≈ aksiyel dilim ekseni
        per = seg.sum(axis=tuple(i for i in range(seg.ndim) if i != ax))
        return {
            "volume_cm3": round(tumor_voxels * voxel_cm3, 2),
            "tumor_voxels": tumor_voxels,
            "voxel_cm3": round(voxel_cm3, 6),
            "num_tumor_slices": int((per > 0).sum()),
            "num_slices": int(seg.shape[ax]),
            "best_slice": int(per.argmax()) if per.max() > 0 else int(seg.shape[ax] // 2),
            "mask_shape": list(seg.shape),
            "engine": "nnunet_3d_fullres (Dice~0.81)",
            "latency_ms": (_t.perf_counter() - t0) * 1000.0,
        }
    except Exception as exc:  # pragma: no cover
        print(f"[seg] nnU-Net çıkarımı başarısız, 2D'ye düşülüyor: {exc}")
        return None


def segment_nifti(t1c_path: str) -> dict:
    """
    Tam T1c NIfTI'den 3B GTV → GERÇEK tümör hacmi (voksel sayısı × voksel hacmi).
    Öncelik: nnU-Net 3D (Dice~0.81). Yoksa 2D U-Net (Dice~0.75) fallback.
    """
    _nn = _segment_nifti_nnunet(t1c_path)
    if _nn is not None:
        return _nn
    import nibabel as nib
    t0 = time.perf_counter()
    nii = nib.load(str(t1c_path))
    vol = _norm(nii.get_fdata())
    zooms = nii.header.get_zooms()[:3]
    voxel_cm3 = float(np.prod(zooms)) / 1000.0  # mm³ → cm³

    Z = vol.shape[2]
    masks = _infer_batch(np.transpose(vol, (2, 0, 1)))  # (Z, H, W)
    # 3B post-processing: dağınık yanlış-pozitifleri temizle (hacim doğruluğu için kritik)
    masks = _postprocess_3d(masks, keep_largest=True)
    tumor_voxels = int(masks.sum())
    per_slice = masks.reshape(Z, -1).sum(1)
    tumor_slices = [int(z) for z in np.where(per_slice > 0)[0]]
    best_slice = int(per_slice.argmax()) if per_slice.max() > 0 else Z // 2

    return {
        "volume_cm3": round(tumor_voxels * voxel_cm3, 2),
        "tumor_voxels": tumor_voxels,
        "voxel_cm3": round(voxel_cm3, 5),
        "num_tumor_slices": len(tumor_slices),
        "num_slices": int(Z),
        "best_slice": best_slice,
        "mask_shape": list(masks.shape),
        "engine": "2d_unet_fallback (Dice~0.75)",
        "latency_ms": (time.perf_counter() - t0) * 1000.0,
    }


def get_segmentation_info() -> dict:
    nnunet_ready = (_NNUNET_DIR / "fold_0" / "checkpoint_best.pth").exists()
    active = "nnunet_3d_fullres" if _load_nnunet() is not None else "2d_unet_fallback"
    return {
        "task": "meningioma_gtv_segmentation",
        "modality": "T1c",
        "trained_on": "BraTS-MEN-RT (500 hasta)",
        "engines": {
            "primary": "nnU-Net 3D full-res (Dice~0.81)",
            "fallback": "2D U-Net 16-32-64-128 (Dice~0.75)",
        },
        "nnunet_model_available": nnunet_ready,
        "active_engine": active,  # CUDA yoksa fallback (CPU'da 3D pratik değil)
        "unet2d_available": _MODEL_PATH.exists(),
    }


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(segment_nifti(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(get_segmentation_info(), ensure_ascii=False, indent=2))
