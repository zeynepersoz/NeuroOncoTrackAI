from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np


class VectorStore:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.documents: list[str] = []

    def add_documents(self, texts: list[str], embeddings: np.ndarray) -> None:
        embeddings = embeddings.astype(np.float32)
        if embeddings.shape[1] != self.dimension:
            raise ValueError(
                f"Embedding boyutu uyuşmuyor: beklenen {self.dimension}, "
                f"gelen {embeddings.shape[1]}"
            )
        self.index.add(embeddings)
        self.documents.extend(texts)

    def search(self, query_embedding: np.ndarray, k: int = 4) -> list[str]:
        k = min(k, self.index.ntotal)
        if k == 0:
            return []
        query = query_embedding.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(query, k)
        return [self.documents[i] for i in indices[0]]

    def count(self) -> int:
        return self.index.ntotal

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path.with_suffix(".faiss")))
        docs_path = path.with_suffix(".txt")
        docs_path.write_text("\n===DOC_SEP===\n".join(self.documents), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> VectorStore:
        path = Path(path)
        index = faiss.read_index(str(path.with_suffix(".faiss")))
        docs_path = path.with_suffix(".txt")
        documents = docs_path.read_text(encoding="utf-8").split("\n===DOC_SEP===\n")
        store = cls(dimension=index.d)
        store.index = index
        store.documents = documents
        return store