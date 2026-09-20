"""
zeynep/pathology_serve.py — Patoloji mikroservisi (bağımsız FastAPI)
================================================================================
Zeynep bölümü. Paylaşımlı serve.py'a dokunmadan, kendi başına çalışan
histopatoloji sınıflandırma servisi.

Çalıştırma:
    cd ai_service && uvicorn zeynep.pathology_serve:app --host 0.0.0.0 --port 8110

Endpoint'ler:
    GET  /health   → durum
    GET  /info     → model meta (9 sınıf, %94.8 test)
    POST /predict  → çok-parçalı (multipart) H&E görüntüsü → 9-sınıf doku tahmini
"""
from __future__ import annotations

import numpy as np

try:
    from fastapi import FastAPI, File, UploadFile, HTTPException
except ImportError as exc:  # pragma: no cover
    raise SystemExit("FastAPI gerekli: pip install fastapi 'uvicorn[standard]' python-multipart") from exc

from pathology_predictor import get_pathology_info, predict_pathology

app = FastAPI(title="NeuroOncoTrack-AI Patoloji Servisi", version="1.0.0",
              description="NCT-CRC-HE 9-sınıf histopatoloji doku sınıflandırıcı (ResNet-18).")


@app.get("/health")
def _health():
    info = get_pathology_info()
    return {"status": "healthy", "model_available": info["model_available"],
            "task": info["task"]}


@app.get("/info")
def _info():
    return get_pathology_info()


@app.post("/predict")
async def _predict(file: UploadFile = File(...)):
    import cv2
    data = await file.read()
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise HTTPException(status_code=400, detail="Görüntü çözülemedi.")
    try:
        return predict_pathology(arr)  # cv2 BGR → predictor içinde RGB'ye çevrilir
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"pathology_error: {exc}")


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PATH_SERVICE_PORT", "8110")))
