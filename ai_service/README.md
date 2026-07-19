# NeuroOncoTrack-AI · Unified AI Service

> **TEKNOFEST 2026 — Onkolojide YZ** için birleşik AI mikroservisi.
> Backend planı **değişmez**. Bu servis iki geliştiricinin (Mert + Zeynep) modüllerini tek çatı altında sunar.

## Mimarî

```
ai_service/
├── mert/                    # Mert'in zip'i AYNEN (dokunulmaz)
│   ├── preprocessing/       #   HD-BET, N4, SimpleITK registration, z-score
│   ├── augmentation/        #   MONAI transforms (training)
│   ├── xai/                 #   Grad-CAM++ + 3-plane overlay
│   ├── llm/                 #   Groq (Llama 3.3-70B) + FAISS RAG + validator
│   ├── core/                #   NeuroOncoTrackPipeline (RAG orchestrator)
│   └── data/guidelines/     #   WHO CNS 5 mini-korpus
│
├── zeynep/                  # Zeynep'in v2/v3 predictor'ları AYNEN
│   ├── v3_predictor.py      #   RF+HGB (1310 slice cache) — glioma-güçlü
│   ├── v2_predictor.py      #   RF+HGB (780 slice cache)  — meningioma-güçlü
│   ├── cache/               #   Feature cache (v1, v2 npz)
│   └── finetuned_models/    #   *.pkl + metrik JSON'ları
│
├── bridge.py                # ★ Tek orkestratör — iki dünyayı birleştirir
├── serve.py                 # ★ FastAPI mikroservisi (backend HTTP proxy)
├── requirements.txt         # Birleşik + çakışma çözümlü
└── README.md                # bu dosya
```

**Kural**: `mert/` ve `zeynep/` altındaki kodlara HİÇ dokunulmaz. Değişiklik olduğunda kendi geliştiricisi güncellemesini yapar; `bridge.py` peer-orchestration ile bağlar.

## Akış

```
       ┌───────────────────────────────────────────────────────────┐
       │  BACKEND (FastAPI Gateway)                                │
       │      └── /ai/infer  → HTTP POST → ai_service:8100/infer   │
       └───────────────────────────────────────────────────────────┘
                                    ↓
       ┌───────────────────────────────────────────────────────────┐
       │  ai_service.bridge.run_pipeline(patient_id, paths, mode)  │
       └───────────────────────────────────────────────────────────┘
             │           │            │             │
             ▼           ▼            ▼             ▼
        [preprocess] [classify]     [xai]        [report]
         Mert         Zeynep         Mert          Mert
        (HD-BET,     (v3 RF+HGB    (Grad-CAM++    (Groq/Llama
         N4, reg,     ensemble)     overlay)       + FAISS RAG
         normalize)                                + validator)
             │           │            │             │
             └────┬──────┴─────┬──────┴─────────────┘
                  ▼            ▼
             result.json    result.stages{...}  (tek JSON dönüş)
```

Bir aşama patlarsa diğerleri çalışmaya devam eder; hatalar `stages.<x>.error` ve top-level `errors[]` alanlarına yazılır.

## Modlar

| mode | Preprocess | Classify | XAI | Report | Kullanım |
|---|---|---|---|---|---|
| `full` | ✓ HD-BET+N4+reg | ✓ | ✓ | ✓ (RAG) | Üretim |
| `fast` | ✗ | ✓ | ✓ | ✓ (RAG) | Ham NIfTI, hızlı demo |
| `classify_only` | ✗ | ✓ | ✗ | ✗ | Batch inference, benchmark |

## Predictor seçimi

| predictor | Cache | Glioma recall | Meningioma recall | Notlar |
|---|---|---|---|---|
| `v3` | 1310 slice, 1010 case | **0.9761** (GCV) / 0.6774 (external, +TTA sonrası) | 0.7967 | Varsayılan |
| `v2` | 780 slice | ~0.90 | **0.94** (external) | Meningioma ağırlıklı vakalar için |

External gap analizi ve seçim gerekçesi: `zeynep/finetuned_models/*.json`.

## Kurulum

```bash
# 1) Sanal ortam
python3 -m venv .venv && source .venv/bin/activate

# 2) Sistem paketleri
brew install dcm2niix libomp     # macOS
# apt install dcm2niix libgomp1  # Linux

# 3) Python bağımlılıkları
pip install -r ai_service/requirements.txt

# 4) HD-BET (opsiyonel, "full" mod için)
pip install git+https://github.com/MIC-DKFZ/HD-BET.git

# 5) Groq API key (RAG için)
export GROQ_API_KEY=gsk_...
```

## Kullanım

### Python'dan doğrudan

```python
from ai_service.bridge import run_pipeline

result = run_pipeline(
    patient_id="BRATS-GLI-00123-000",
    modality_paths={
        "t1":    "raw/t1.nii.gz",
        "t1c":   "raw/t1c.nii.gz",
        "t2":    "raw/t2.nii.gz",
        "flair": "raw/flair.nii.gz",
    },
    output_dir="processed/BRATS-GLI-00123-000",
    mode="full",                # "full" | "fast" | "classify_only"
    device="auto",              # cuda > mps > cpu
    predictor="v3",             # "v3" | "v2"
    extra_features={            # segmentasyon çıktısı (varsa)
        "tumor_volume_cm3": 45.2,
        "et_wt_ratio": 0.42,
    },
)

print(result["summary"]["prediction"])
print(result["stages"]["report"]["payload"]["report"])
```

### HTTP servisi olarak

```bash
uvicorn ai_service.serve:app --host 0.0.0.0 --port 8100
```

```bash
curl -s http://localhost:8100/health | jq
curl -s -X POST http://localhost:8100/infer \
  -H "content-type: application/json" \
  -d '{
    "patient_id": "BRATS-GLI-00123-000",
    "modality_paths": {"t1c": "raw/t1c.nii.gz"},
    "output_dir": "processed/case1",
    "mode": "fast"
  }' | jq
```

## Dönüş şeması

```jsonc
{
  "patient_id": "…",
  "pipeline_version": "1.0.0",
  "timestamp": "2026-07-19T14:00:00+00:00",
  "mode": "full",
  "device": "mps",
  "stages": {
    "preprocess": { "status": "ok",     "elapsed_ms": 12034.5, "payload": { "processed_paths": {…}, "qc_flags": [] } },
    "classify":   { "status": "ok",     "elapsed_ms": 812.1,   "payload": { "prediction": "glioma", "confidence": 0.94, "probabilities": {…}, "model_id": "v3_rf_hgb_expanded_cache" } },
    "xai":        { "status": "ok",     "elapsed_ms": 210.4,   "payload": { "overlay_path": "…/gradcam_overlay.png" } },
    "report":     { "status": "ok",     "elapsed_ms": 3120.2,  "payload": { "is_valid": true, "sections": {…}, "fhir": {…}, "validation": {…} } }
  },
  "summary": {
    "prediction": "glioma",
    "confidence": 0.94,
    "who_grade_hint": "III-IV (…)",
    "tumor_area_ratio_2d": 0.083,
    "tumor_volume_cm3": 45.2,
    "et_wt_ratio": 0.42,
    "report_valid": true
  },
  "errors": [],
  "total_elapsed_ms": 16177.2
}
```

## Backend'e entegrasyon (backend planı DEĞİŞMEZ)

Backend planındaki `/ai/*` endpoint'leri iç HTTP çağrısıyla bu servise proxy'lenir:

```python
# backend/services/ai_orchestrator.py (öneri, Zeynep+Mert kaynağı dışı)
import httpx
AI_SERVICE_URL = os.environ["AI_SERVICE_URL"]  # http://ai:8100

async def infer(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{AI_SERVICE_URL}/infer", json=payload)
        r.raise_for_status()
        return r.json()
```

Backend hiçbir Zeynep/Mert modülünü doğrudan import etmez → **iç değişiklikler backend'i etkilemez**.

## Yol haritası (post-hackathon)

- [ ] Grad-CAM++ için TF↔PyTorch köprüsü (şu an `bridge._stage_xai` pseudo-CAM üretiyor)
- [ ] ResUnet 3D segmentasyondan gerçek `tumor_volume_cm3` alma (bridge içine opsiyonel enjeksiyon)
- [ ] Multi-slice ensemble (v3_predictor `predict_v3_multislice` zaten hazır — bridge'te henüz kullanılmıyor)
- [ ] Model registry versiyonlama (v3 → v4 geçişinde canary deploy)
- [ ] Prometheus metrikleri (`ai_service_infer_seconds` histogram)

## Sorun giderme

| Belirti | Sebep | Çözüm |
|---|---|---|
| `preprocess: HD-BET kurulu değil` | HD-BET yok | `mode="fast"` kullan veya `pip install git+https://github.com/MIC-DKFZ/HD-BET.git` |
| `report: skipped` | GROQ_API_KEY yok | `export GROQ_API_KEY=…` |
| `libomp not found` (macOS) | LightGBM/OMP eksik | `brew install libomp` |
| `torch.cuda.is_available() == False` | GPU yok | `device="mps"` (Mac) veya `"cpu"` |
| `T1c dilimi okunamadı` | Modalite eksik/bozuk | En az `t1c` NIfTI yolunu doğrula |
