from unittest.mock import MagicMock

import numpy as np

from llm.embedder import Embedder


def test_embedder_lazy_loading():
    embedder = Embedder()
    assert embedder._model is None


def test_encode_returns_float32():
    embedder = Embedder()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.random.rand(2, 384).astype(np.float64)
    embedder._model = mock_model

    result = embedder.encode(["test1", "test2"])

    assert result.dtype == np.float32


def test_encode_single_string_becomes_list():
    embedder = Embedder()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.random.rand(1, 384).astype(np.float32)
    embedder._model = mock_model

    embedder.encode("tek bir cümle")

    called_texts = mock_model.encode.call_args[0][0]
    assert isinstance(called_texts, list)
    assert called_texts == ["tek bir cümle"]


def test_encode_output_shape():
    embedder = Embedder()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.random.rand(3, 384).astype(np.float32)
    embedder._model = mock_model

    result = embedder.encode(["a", "b", "c"])

    assert result.shape == (3, 384)


def test_dimension_returns_int():
    embedder = Embedder()
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    embedder._model = mock_model

    dim = embedder.dimension()

    assert dim == 384
    assert isinstance(dim, int)


def test_load_model_caches():
    embedder = Embedder()
    mock_model = MagicMock()
    embedder._model = mock_model

    first = embedder._load_model()
    second = embedder._load_model()

    assert first is second