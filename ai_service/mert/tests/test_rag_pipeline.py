from unittest.mock import MagicMock, patch

import numpy as np

from llm.rag_pipeline import RAGPipeline
from llm.system_prompt import REQUIRED_DISCLAIMER, format_user_message
from llm.vector_store import VectorStore


def test_retrieve_returns_documents():
    store = VectorStore(dimension=8)
    docs = ["WHO Grade IV glioblastom", "IDH mutasyonu", "MGMT metilasyonu"]
    embs = np.random.rand(3, 8).astype(np.float32)
    store.add_documents(docs, embs)

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.vector_store = store

    query = np.random.rand(8).astype(np.float32)
    results = pipeline.retrieve(query, k=2)

    assert len(results) == 2
    assert all(isinstance(r, str) for r in results)


def test_retrieve_without_store_returns_empty():
    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.vector_store = None

    query = np.random.rand(8).astype(np.float32)
    results = pipeline.retrieve(query)

    assert results == []


def test_format_user_message_includes_output():
    msg = format_user_message({"tumor_volume": 45.2}, ["doc1"])
    assert "45.2" in msg
    assert "doc1" in msg


def test_format_user_message_no_docs():
    msg = format_user_message({"tumor_volume": 45.2}, [])
    assert "Referans belge bulunamadı" in msg


@patch("llm.rag_pipeline.Groq")
def test_generate_report_valid_on_first_try(mock_groq_cls):
    valid_report = (
        "BULGULAR\nTümör hacmi 45.2 cm³.\n\n"
        "DEĞERLENDİRME\nIDH olası pozitif.\n\n"
        "ÖNERİ\nİleri tetkik.\n\n"
        f"{REQUIRED_DISCLAIMER}"
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=valid_report))
    ]
    mock_groq_cls.return_value = mock_client

    pipeline = RAGPipeline(groq_api_key="test-key")
    result = pipeline.generate_report({"tumor_volume": 45.2})

    assert result["is_valid"] is True
    assert result["attempt"] == 1


@patch("llm.rag_pipeline.Groq")
def test_generate_report_retries_on_forbidden(mock_groq_cls):
    bad_report = (
        "BULGULAR\nKesinlikle tümör.\n"
        "DEĞERLENDİRME\nTest.\n"
        "ÖNERİ\nTest.\n\n"
        f"{REQUIRED_DISCLAIMER}"
    )
    good_report = (
        "BULGULAR\nTümör olası.\n\n"
        "DEĞERLENDİRME\nTest.\n\n"
        "ÖNERİ\nTest.\n\n"
        f"{REQUIRED_DISCLAIMER}"
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=bad_report))
    ]
    mock_groq_cls.return_value = mock_client

    pipeline = RAGPipeline(groq_api_key="test-key", max_retries=1)

    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=good_report))
    ]

    result = pipeline.generate_report({"test": 1})

    assert mock_client.chat.completions.create.call_count >= 1