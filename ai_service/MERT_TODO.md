# Mert için Aksiyon Listesi
_ai_service/ birleştirme testinden çıkan geliştirme önerileri_

> **Not:** Bu liste `mert/` dizininde YALNIZCA Mert'in yapması gereken değişikliklerdir.
> Zeynep tarafında (`bridge.py`, `serve.py`, test scriptleri) her şey hazır.

---

## 🔴 Kritik (pipeline'ı bloke ediyor)

### 1. `main.py` boş (0 byte)
Şu an paketin entry-point'i yok. Ya sil ya da minimum CLI ekle:
```python
# main.py
if __name__ == "__main__":
    from core.end_to_end import NeuroOncoTrackPipeline
    print("neurooncotrack-ai module loaded. Use core.end_to_end.NeuroOncoTrackPipeline.")
```

### 2. `preprocessing/pipeline.py` — default `device="cuda"`
Mac'te / CPU sunucuda `cuda` yok, HD-BET patlar. Default'u `"auto"` yap:
```python
def preprocess_patient(patient, quarantine_root, device: str = "auto"):
    if device == "auto":
        try:
            import torch
            if torch.cuda.is_available(): device = "cuda"
            elif torch.backends.mps.is_available(): device = "mps"
            else: device = "cpu"
        except ImportError:
            device = "cpu"
```

### 3. HD-BET opsiyonel yap (CPU-only fallback)
`preprocessing/skull_strip.py` — HD-BET yoksa **Otsu + morfoloji** ile basit brain-mask üretsin,
`patient.qc_flags.append("skull_strip_fallback_used")` ekle. Böylece pipeline **her ortamda** çalışır.

---

## 🟡 Uyum (ai_service ile daha temiz çalışması için)

### 4. `preprocessing/utils.py` — BraTS 2023 modaliteler için alias
Şu an `REQUIRED_MODALITIES = ("t1", "t1c", "t2", "flair")`.
BraTS-GLI 2023 dosyaları `t1n`, `t1c`, `t2w`, `t2f` olarak geliyor.
Bir alias dict eklenirse hastane / araştırma verisi de sorunsuz çalışır:
```python
MODALITY_ALIASES = {
    "t1n": "t1", "t1w": "t1",
    "t1c": "t1c", "t1gd": "t1c", "t1ce": "t1c",
    "t2w": "t2", "t2": "t2",
    "t2f": "flair", "flair": "flair", "fla": "flair",
}
```
(Şu an `smoke_test.py` içinde ben manuel map yapıyorum — Mert'in tarafında olursa daha temiz.)

### 5. `requirements.txt` — numpy pin
`numpy==2.4.4` yazıyor. TensorFlow 2.15/2.16 ile çakışıyor.
Zeynep tarafında `numpy>=1.26.0,<2.0` gerekli. Merged `ai_service/requirements.txt` bunu düzeltti,
ama Mert kendi requirements'ında da `numpy>=1.26.0,<2.0` yapsın.

### 6. `.env.example` ekle
`llm/rag_pipeline.py` `GROQ_API_KEY` bekliyor. Yeni geliştiriciler için:
```
# .env.example
GROQ_API_KEY=your_key_here
```

---

## 🟢 Nice-to-have (TEKNOFEST puanı arttırır)

### 7. Segmentation modeli (opsiyonel)
Şu an sadece `xai/grad_cam_pp.py` (classification için) var.
Eğer TensorFlow tabanlı bir U-Net veya nnU-Net entegre edilirse:
- Zeynep'in TF modelinden gerçek Grad-CAM++ üretilebilir
- Tümör core/edema/enhancing hacimleri model çıktısından gelir (şu an ground-truth seg gerekli)

### 8. `xai/grad_cam_pp.py` — TF backbone adapter
Şu an PyTorch-only. TF model + Grad-CAM++ için ince bir wrapper eklenirse
Zeynep'in MobileNetV2'sinde de çalışır (şu an bridge.py brain-masked pseudo-CAM kullanıyor).

### 9. `preprocessing/qc.py` — quarantine yerine warning tercihi
Şu an `run_pre_pipeline_qc` critical flag koyduğunda hasta karantinaya gidiyor ve
pipeline durur. Backend'e gösterilebilir bir "yellow flag" seviyesi eklenirse
bazı vakalar bilgi ile devam eder.

### 10. `tests/` genişletme
Şu an `test_end_to_end.py` var. `tests/test_preprocessing_mock.py` benzeri
NIfTI-mock ile birim testler eklenirse CI'da çalışır.

---

## Test sonuçları (Mert'in katmanı için referans)
- `mert.preprocessing` import ✅ (SimpleITK kuruldu)
- `mert.xai.overlay` import ✅
- `mert.llm.rag_pipeline` import ✅ (faiss kuruldu)
- HD-BET henüz test edilmedi — Python 3.11 ortamında + `pip install hd-bet` ile denenecek
- Pipeline "full" mode: HD-BET olmadan preprocess_patient'ın nasıl davrandığı gözlemlenmedi

---

## İletişim
Zeynep tarafında herhangi bir şey netleştirilecekse önce `ai_service/README.md` ve
`ai_service/bridge.py` dokümantasyonuna bak. Bridge'in beklediği `Patient` API'si tam olarak
Mert'in `preprocessing/utils.py::Patient` sınıfıdır (değiştirmedik).
