"""
radiogenomics.py — Radyomik özellik çıkarımı + IDH/MGMT tahmini (gerçek model).
pyradiomics derlenmediği için nibabel+numpy+skimage ile hafif ama gerçek radyomik
özellik seti: first-order (T1c & FLAIR), şekil (mask), GLCM doku. UCSF-PDGM (501
glioma, gerçek IDH/MGMT etiketi) ile eğitilir; sahte % YOK.
"""
from __future__ import annotations
import numpy as np

FEATURES = [
    # first-order (tümör maskesi içinde) — T1c ve FLAIR
    "t1c_mean","t1c_std","t1c_skew","t1c_kurtosis","t1c_entropy","t1c_p10","t1c_p90",
    "fl_mean","fl_std","fl_skew","fl_kurtosis","fl_entropy",
    # şekil (maskeden)
    "volume_cm3","surface_vox","sphericity","extent_ratio",
    # GLCM doku (tümörün en büyük kesitinde, T1c)
    "glcm_contrast","glcm_homogeneity","glcm_energy","glcm_correlation",
]


def _firstorder(vals: np.ndarray, prefix: str) -> dict:
    from scipy.stats import skew, kurtosis
    v = vals.astype(np.float64)
    if v.size < 10:
        return {f"{prefix}_{k}": 0.0 for k in ["mean","std","skew","kurtosis","entropy","p10","p90"]}
    hist, _ = np.histogram(v, bins=32, density=True); hist = hist[hist > 0]
    ent = float(-(hist * np.log(hist + 1e-12)).sum())
    d = {f"{prefix}_mean": float(v.mean()), f"{prefix}_std": float(v.std()),
         f"{prefix}_skew": float(skew(v)), f"{prefix}_kurtosis": float(kurtosis(v)),
         f"{prefix}_entropy": ent}
    if prefix == "t1c":
        d[f"{prefix}_p10"] = float(np.percentile(v, 10)); d[f"{prefix}_p90"] = float(np.percentile(v, 90))
    return d


def _shape(mask: np.ndarray, spacing=(1.0,1.0,1.0)) -> dict:
    vox = float(mask.sum())
    vox_vol = spacing[0]*spacing[1]*spacing[2]
    volume_cm3 = vox * vox_vol / 1000.0
    # yüzey ~ komşuluk farkı
    from scipy import ndimage
    er = ndimage.binary_erosion(mask)
    surface = float((mask & ~er).sum())
    # sferisite: (36π V²)^(1/3) / A  (voxel yaklaşık)
    V = vox * vox_vol; A = surface * (spacing[0]*spacing[1])
    sph = float((np.pi**(1/3) * (6*V)**(2/3)) / (A + 1e-6)) if A > 0 else 0.0
    # bbox doluluk
    idx = np.argwhere(mask)
    if len(idx):
        bb = idx.max(0) - idx.min(0) + 1
        extent = float(vox / (bb.prod() + 1e-6))
    else:
        extent = 0.0
    return {"volume_cm3": volume_cm3, "surface_vox": surface,
            "sphericity": min(sph,1.5), "extent_ratio": extent}


def _glcm(t1c: np.ndarray, mask: np.ndarray) -> dict:
    from skimage.feature import graycomatrix, graycoprops
    zs = mask.sum((0,1)); 
    if zs.max() == 0: return {"glcm_contrast":0.0,"glcm_homogeneity":0.0,"glcm_energy":0.0,"glcm_correlation":0.0}
    z = int(zs.argmax())
    sl = t1c[:,:,z]; m = mask[:,:,z]
    if m.sum() < 10: return {"glcm_contrast":0.0,"glcm_homogeneity":0.0,"glcm_energy":0.0,"glcm_correlation":0.0}
    vals = sl[m]; lo,hi = np.percentile(vals,2),np.percentile(vals,98)
    q = np.clip((sl - lo)/(hi-lo+1e-6),0,1); q = (q*31).astype(np.uint8); q[~m] = 0
    g = graycomatrix(q, distances=[1], angles=[0,np.pi/2], levels=32, symmetric=True, normed=True)
    return {"glcm_contrast": float(graycoprops(g,"contrast").mean()),
            "glcm_homogeneity": float(graycoprops(g,"homogeneity").mean()),
            "glcm_energy": float(graycoprops(g,"energy").mean()),
            "glcm_correlation": float(graycoprops(g,"correlation").mean())}


def extract_features(t1c: np.ndarray, flair: np.ndarray, mask: np.ndarray, spacing=(1.0,1.0,1.0)) -> dict:
    mask = mask.astype(bool)
    f = {}
    f.update(_firstorder(t1c[mask], "t1c"))
    f.update(_firstorder(flair[mask], "fl"))
    f.update(_shape(mask, spacing))
    f.update(_glcm(t1c, mask))
    return {k: f.get(k, 0.0) for k in FEATURES}
