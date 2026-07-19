"""
NeuroOncoTrack-AI — Unified AI Service
=======================================

Bu paket iki bağımsız AI servisini tek çatı altında birleştirir:

  * mert/    → Preprocessing (HD-BET, N4, registration) + XAI + RAG (Groq/Llama)
  * zeynep/  → Sınıflandırma (v3 RF+HGB ensemble, MobileNetV2 backbone)

Backend yalnızca `ai_service.bridge.run_pipeline()` fonksiyonunu çağırır.
Alt modüllerin iç detayları dışarıya sızmaz.
"""

__version__ = "1.0.0"
