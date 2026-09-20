from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

from .report_validator import validate_report
from .system_prompt import SYSTEM_PROMPT, format_user_message
from .vector_store import VectorStore

logger = logging.getLogger("neurooncotrack.llm")

# Taslak (LLM-A) modeli. Groq varsayılan; OPENAI_API_KEY varsa OpenAI'ye geçer.
DEFAULT_GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
DEFAULT_OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")


def _drafter_provider() -> str:
    """Sağlayıcı seç: DRAFTER_PROVIDER env, yoksa OPENAI_API_KEY varsa openai."""
    p = (os.environ.get("DRAFTER_PROVIDER") or "").strip().lower()
    if p in ("openai", "groq"):
        return p
    return "openai" if os.environ.get("OPENAI_API_KEY") else "groq"


class RAGPipeline:
    def __init__(
        self,
        groq_api_key: str,
        vector_store: Optional[VectorStore] = None,
        model_name: str = DEFAULT_GROQ_MODEL,
        max_retries: int = 2,
        temperature: float = 0.2,
    ):
        self.provider = _drafter_provider()
        if self.provider == "openai":
            from openai import OpenAI  # type: ignore
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
            # bridge, groq model adını geçer; OpenAI'de OPENAI_MODEL kullan.
            self.model_name = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        else:
            from groq import Groq  # type: ignore
            self.client = Groq(api_key=groq_api_key)
            self.model_name = model_name
        self.vector_store = vector_store
        self.max_retries = max_retries
        self.temperature = temperature

    def retrieve(self, query_embedding: np.ndarray, k: int = 4) -> list[str]:
        if self.vector_store is None:
            return []
        return self.vector_store.search(query_embedding, k=k)

    def generate(self, model_output: dict, context_docs: list[str]) -> str:
        user_message = format_user_message(model_output, context_docs)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        # Bazı yeni OpenAI modelleri (gpt-5.x) sabit temperature ister → önce
        # temperature ile dene, reddedilirse temperature'sız tekrar dene.
        try:
            response = self.client.chat.completions.create(
                model=self.model_name, messages=messages,
                temperature=self.temperature,
            )
        except Exception:
            response = self.client.chat.completions.create(
                model=self.model_name, messages=messages,
            )
        return response.choices[0].message.content

    def generate_report(
        self,
        model_output: dict,
        query_embedding: Optional[np.ndarray] = None,
    ) -> dict:
        context_docs = self.retrieve(query_embedding) if query_embedding is not None else []

        last_result = None
        for attempt in range(1, self.max_retries + 2):
            logger.info("Rapor üretiliyor (deneme %d/%d)", attempt, self.max_retries + 1)

            raw_report = self.generate(model_output, context_docs)
            result = validate_report(raw_report, model_output)
            result["attempt"] = attempt

            if result["is_valid"]:
                logger.info("Rapor geçerli (deneme %d)", attempt)
                return result

            logger.warning(
                "Rapor geçersiz (deneme %d): eksik=%s, yasak=%s, sayısal=%s",
                attempt,
                result["missing_sections"],
                result["forbidden_phrases"],
                result["numeric_mismatches"],
            )
            last_result = result

            self.temperature = max(0.1, self.temperature - 0.05)

        logger.error("Rapor %d denemede de geçerli üretilemedi", self.max_retries + 1)
        last_result["max_retries_exceeded"] = True
        return last_result
