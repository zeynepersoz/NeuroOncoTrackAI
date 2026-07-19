from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from groq import Groq

from .report_validator import validate_report
from .system_prompt import SYSTEM_PROMPT, format_user_message
from .vector_store import VectorStore

logger = logging.getLogger("neurooncotrack.llm")


class RAGPipeline:
    def __init__(
        self,
        groq_api_key: str,
        vector_store: Optional[VectorStore] = None,
        model_name: str = "llama-3.3-70b-versatile",
        max_retries: int = 2,
        temperature: float = 0.2,
    ):
        self.client = Groq(api_key=groq_api_key)
        self.vector_store = vector_store
        self.model_name = model_name
        self.max_retries = max_retries
        self.temperature = temperature

    def retrieve(self, query_embedding: np.ndarray, k: int = 4) -> list[str]:
        if self.vector_store is None:
            return []
        return self.vector_store.search(query_embedding, k=k)

    def generate(self, model_output: dict, context_docs: list[str]) -> str:
        user_message = format_user_message(model_output, context_docs)

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
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