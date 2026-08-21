from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from llm.embedder import Embedder
from llm.rag_pipeline import RAGPipeline
from llm.vector_store import VectorStore

logger = logging.getLogger("neurooncotrack.core")


def load_guidelines(guidelines_dir: Path) -> list[str]:
    guidelines_dir = Path(guidelines_dir)
    chunks = []
    for filepath in sorted(guidelines_dir.glob("*.txt")):
        text = filepath.read_text(encoding="utf-8")
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks.extend(paragraphs)
    logger.info("Kılavuz yüklendi: %d dosya, %d parça", len(list(guidelines_dir.glob("*.txt"))), len(chunks))
    return chunks


def build_vector_store(chunks: list[str], embedder: Embedder) -> VectorStore:
    embeddings = embedder.encode(chunks)
    store = VectorStore(dimension=embeddings.shape[1])
    store.add_documents(chunks, embeddings)
    logger.info("VectorStore oluşturuldu: %d belge, %d boyut", store.count(), embeddings.shape[1])
    return store


def build_query_from_output(model_output: dict) -> str:
    parts = []

    label = model_output.get("label")
    if label is not None:
        parts.append(f"tümör tipi {label}")
    else:
        parts.append("belirsiz sınıflandırma düşük güven")

    radiomics = model_output.get("radiomics", {})
    if "volume_cm3" in radiomics:
        parts.append("tümör hacmi segmentasyon")
    if "et_wt_ratio" in radiomics:
        parts.append("ET WT oranı kontrast tutan bölge")

    if model_output.get("reject_reason"):
        parts.append(f"belirsizlik nedeni {model_output['reject_reason']}")

    if not parts:
        parts.append("beyin tümörü değerlendirme")

    return ", ".join(parts)


class NeuroOncoTrackPipeline:
    def __init__(
        self,
        groq_api_key: str,
        guidelines_dir: Path,
        model_name: str = "llama-3.3-70b-versatile",
    ):
        logger.info("Pipeline başlatılıyor...")

        self.embedder = Embedder()

        chunks = load_guidelines(guidelines_dir)
        self.vector_store = build_vector_store(chunks, self.embedder)

        self.rag = RAGPipeline(
            groq_api_key=groq_api_key,
            vector_store=self.vector_store,
            model_name=model_name,
        )

        logger.info("Pipeline hazır.")

    def generate_report(self, model_output: dict) -> dict:
        query_text = build_query_from_output(model_output)
        logger.info("Sorgu: %s", query_text)

        query_embedding = self.embedder.encode(query_text)[0]

        result = self.rag.generate_report(
            model_output=model_output,
            query_embedding=query_embedding,
        )

        return result

    def search_guidelines(self, query: str, k: int = 4) -> list[str]:
        query_embedding = self.embedder.encode(query)[0]
        return self.vector_store.search(query_embedding, k=k)