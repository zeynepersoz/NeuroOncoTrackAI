from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from core.end_to_end import (
    build_query_from_output,
    build_vector_store,
    load_guidelines,
)
from llm.system_prompt import REQUIRED_DISCLAIMER


def test_load_guidelines_splits_paragraphs(tmp_path):
    guide = tmp_path / "test.txt"
    guide.write_text("Paragraf bir.\n\nParagraf iki.\n\nParagraf üç.", encoding="utf-8")

    chunks = load_guidelines(tmp_path)

    assert len(chunks) == 3
    assert chunks[0] == "Paragraf bir."
    assert chunks[2] == "Paragraf üç."


def test_load_guidelines_multiple_files(tmp_path):
    (tmp_path / "a.txt").write_text("Birinci dosya.", encoding="utf-8")
    (tmp_path / "b.txt").write_text("İkinci dosya.", encoding="utf-8")

    chunks = load_guidelines(tmp_path)

    assert len(chunks) == 2


def test_load_guidelines_skips_empty_paragraphs(tmp_path):
    guide = tmp_path / "test.txt"
    guide.write_text("Bir.\n\n\n\n\nİki.", encoding="utf-8")

    chunks = load_guidelines(tmp_path)

    assert len(chunks) == 2


def test_load_guidelines_empty_dir(tmp_path):
    chunks = load_guidelines(tmp_path)
    assert chunks == []


def test_build_query_all_fields():
    q = build_query_from_output({
        "idh_status": "mutant",
        "mgmt_status": "metile",
        "who_grade": "IV",
        "tumor_volume": 45.2,
    })

    assert "IDH mutant" in q
    assert "MGMT metile" in q
    assert "WHO Grade IV" in q
    assert "tümör hacmi" in q


def test_build_query_partial_fields():
    q = build_query_from_output({"tumor_volume": 30.0})
    assert "tümör hacmi" in q
    assert "IDH" not in q


def test_build_query_empty_output():
    q = build_query_from_output({})
    assert q == "beyin tümörü değerlendirme"


def test_build_vector_store_correct_count():
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = np.random.rand(3, 8).astype(np.float32)

    store = build_vector_store(["a", "b", "c"], mock_embedder)

    assert store.count() == 3


def test_build_vector_store_searchable():
    mock_embedder = MagicMock()
    embeddings = np.random.rand(3, 8).astype(np.float32)
    mock_embedder.encode.return_value = embeddings

    store = build_vector_store(["WHO Grade IV", "IDH mutant", "MGMT metile"], mock_embedder)
    results = store.search(embeddings[0], k=1)

    assert len(results) == 1
    assert results[0] == "WHO Grade IV"


@patch("core.end_to_end.Embedder")
@patch("core.end_to_end.RAGPipeline")
def test_pipeline_generate_report(mock_rag_cls, mock_embedder_cls, tmp_path):
    guide = tmp_path / "test.txt"
    guide.write_text("Kılavuz paragrafı.", encoding="utf-8")

    mock_embedder = MagicMock()
    mock_embedder.encode.return_value = np.random.rand(1, 8).astype(np.float32)
    mock_embedder_cls.return_value = mock_embedder

    valid_report = (
        f"BULGULAR\nTest.\n\nDEĞERLENDİRME\nTest.\n\nÖNERİ\nTest.\n\n{REQUIRED_DISCLAIMER}"
    )
    mock_rag = MagicMock()
    mock_rag.generate_report.return_value = {
        "is_valid": True,
        "report": valid_report,
        "attempt": 1,
    }
    mock_rag_cls.return_value = mock_rag

    from core.end_to_end import NeuroOncoTrackPipeline
    pipeline = NeuroOncoTrackPipeline(
        groq_api_key="test-key",
        guidelines_dir=tmp_path,
    )
    result = pipeline.generate_report({"tumor_volume": 45.2})

    assert result["is_valid"] is True
    assert result["attempt"] == 1