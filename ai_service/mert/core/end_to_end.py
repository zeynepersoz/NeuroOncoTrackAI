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
    if "idh_status" in model_output:
        parts.append(f"IDH {model_output['idh_status']}")
    if "mgmt_status" in model_output:
        parts.append(f"MGMT {model_output['mgmt_status']}")
    if "who_grade" in model_output:
        parts.append(f"WHO Grade {model_output['who_grade']}")
    if "tumor_volume" in model_output:
        parts.append("tümör hacmi segmentasyon")
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