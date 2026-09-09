# NeuroOncoTrack-AI — Tam Entegre Sürüm (`main`)

Beyin tümörü MR analizi ve klinik karar destek platformu. Bu `main` branch'i
**backend + frontend + AI** servislerini tek repoda birleştirir (Teknofest 2026,
Etik: TÜTF-GOBAEK 2026/205).

> Diğer branch'ler (`ai`, `feature/backend`, `frontend`) ekip üyelerinin çalışma
> dalları; `main` bunların entegre ve çalışır anlık görüntüsüdür.

## Yapı
```
ai_service/     AI mikroservisi (:8100) — Mert (ön işleme/XAI/RAG) + Zeynep (sınıflandırma/segmentasyon)
  zeynep/       4-sınıf sınıflandırıcı, çift-LLM rapor (report_dual.py), 3D segmentasyon,
                patoloji servisi (pathology_serve.py :8110), pod GPU servisi (seg_serve.py)
backend/        FastAPI (:8001) — auth + admin (+ app/api/ai_gateway.py = AI uçları TEK YERDE)
frontend/       React 19 + Vite (:5173) — klinik çalışma alanı + admin paneli
```

## AI uçları nerede (tek yer)
Backend'e AI için eklenen tüm yollar **`backend/app/api/ai_gateway.py`** içinde:
- `GET /api/library` — vaka kütüphanesi (2D demo + 3D referans vakaları)
- `POST /api/analyze` — 2D jpg → sınıflandırma+rapor+görüntü · 3D NIfTI → pod GPU segmentasyon+hacim+overlay
- `POST /api/report` — çift-LLM klinik rapor
`main.py` bunu `ENABLE_AI_GATEWAY` (vars. açık) ile bağlar.

## Kurulum & çalıştırma
Önce sırları hazırla (repoda YOK):
- `backend/.env` ← `backend/.env.example`'dan doldur (DB, JWT, MFA, CORS).
- `backend/keys/` ← RS256 anahtar çifti üret: `openssl genpkey -algorithm RSA -out keys/private.pem && openssl rsa -in keys/private.pem -pubout -out keys/public.pem`
- `frontend/.env` ← `frontend/.env.example` (VITE_BACKEND_URL, VITE_AI_SERVICE_URL, VITE_API_MODE).
- AI için `GROQ_API_KEY` env (rapor). Model: nnU-Net 3D checkpoint repoda yok (>100MB) — ayrıca indirilir.

```bash
# 1) Postgres + Redis (docker)
docker compose -f backend/docker-compose.yml up -d      # :5433, :6379

# 2) Backend (:8001)
cd backend && python3.11 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8001

# 3) AI servisi (:8100) — Python 3.11 (TF 2.21 + torch)
cd ai_service && uvicorn serve:app --host 0.0.0.0 --port 8100
#    export GROQ_API_KEY=...  GROQ_MODEL=openai/gpt-oss-120b  GROQ_REVIEWER_MODEL=openai/gpt-oss-20b

# 4) Patoloji servisi (:8110)
cd ai_service/zeynep && uvicorn pathology_serve:app --host 0.0.0.0 --port 8110

# 5) Frontend (:5173)
cd frontend && npm install && npm run dev
```

## 3D segmentasyon (GPU)
2D sınıflandırma/rapor Mac/CPU'da çalışır; **3D nnU-Net segmentasyonu GPU ister**.
Pod'da `ai_service/zeynep/seg_serve.py` çalışır (`:8100`), Mac'e SSH tüneliyle bağlanır:
```bash
ssh -f -N -L 8200:127.0.0.1:8100 -p <pod-port> -i ~/.ssh/id_ed25519 root@<pod-ip>
export AI_SEG_URL=http://127.0.0.1:8200   # backend bunu kullanır
```

## Modeller
- Sınıflandırma (`rf_kaggle4.pkl`, `hgb_kaggle4.pkl`), patoloji (`crc_model.pt`), 2D U-Net (`unet_men.pt`) → repoda.
- nnU-Net 3D checkpoint (~118MB) → repoda değil (GitHub 100MB limiti); Release/Drive'dan `ai_service/zeynep/finetuned_models/nnunet_men/` altına.

## Güvenlik / KVKK
Sırlar (`.env`, `keys/`, `*.pem`) `.gitignore`'da; commit edilmez. Hastane verisi eğitime/servise
**sokulmaz**, yalnız de-identify edilmiş doğrulama için kullanılır.
