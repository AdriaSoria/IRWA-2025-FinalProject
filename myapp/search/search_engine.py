import random
import numpy as np

from myapp.search.objects import Document

from myapp.search.algorithms import build_terms_query, build_terms_doc, average_vector
from myapp.search.objects import Document
from pathlib import Path
from typing import Dict, List
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from gensim.models import Word2Vec


DEFAULT_METADATA_PATH = Path(__file__).resolve().parents[1] / "products.json"


class Word2VecRetrieval:
    """
    Retrieval engine that performs boolean filtering + cosine ranking.
    Uses the preprocessed CSV for training (as done in the research notebook)
    while keeping JSON metadata to display complete product information.
    """

    def __init__(
        self,
        catalog_csv_path: Path,
        metadata_path: Path = DEFAULT_METADATA_PATH,
        vector_size: int = 200,
        window: int = 10,
        min_count: int = 2,
        epochs: int = 25,
    ) -> None:
        self.catalog_csv_path = Path(catalog_csv_path)
        self.metadata_path = Path(metadata_path)
        if not self.catalog_csv_path.exists():
            raise FileNotFoundError(
                f"Preprocessed CSV not found at {self.catalog_csv_path}. "
                "Please ensure productos_preprocesados.csv is available."
            )
        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Metadata JSON not found at {self.metadata_path}. "
                "Run the dataset export step to generate products.json."
            )

        self.vector_size = vector_size
        self.window = window
        self.min_count = min_count
        self.epochs = epochs

        self.catalog_df = self._load_catalog()
        self.metadata_docs = self._load_metadata_documents()
        self.terms = self._build_terms_matrix()
        self.model = self._train_word2vec()
        self.doc_vectors = self._build_document_vectors()

    # ------------------------------------------------------------------ #
    # Data loading helpers
    # ------------------------------------------------------------------ #

    def _load_catalog(self) -> pd.DataFrame:
        df = pd.read_csv(self.catalog_csv_path)
        df = df.fillna("")
        return df

    def _load_metadata_documents(self) -> Dict[str, Document]:
        docs: Dict[str, Document] = {}
        df = pd.read_json(self.metadata_path)
        for _, row in df.iterrows():
            try:
                doc = Document(**row.to_dict())
            except Exception:
                continue
            docs[doc.pid] = doc
        return docs

    def _compose_text(self, row: pd.Series) -> str:
        fields = ["title", "description", "brand", "category", "sub_category", "seller"]
        parts = [str(row.get(field, "")).strip() for field in fields if row.get(field)]
        return " ".join(parts)

    def _build_terms_matrix(self) -> List[List[str]]:
        corpus_terms: List[List[str]] = []
        for _, row in self.catalog_df.iterrows():
            corpus_terms.append(build_terms_doc(self._compose_text(row)))
        return corpus_terms

    def _train_word2vec(self) -> Word2Vec:
        sentences = [tokens for tokens in self.terms if tokens]
        if not sentences:
            raise ValueError("No valid sentences found to train Word2Vec.")
        model = Word2Vec(
            sentences=sentences,
            vector_size=self.vector_size,
            window=self.window,
            min_count=self.min_count,
            workers=4,
            sg=1,
            epochs=self.epochs,
        )
        return model

    def _build_document_vectors(self) -> np.ndarray:
        vectors = [average_vector(tokens, self.model) for tokens in self.terms]
        return np.vstack(vectors)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search(self, query: str, top_n: int = 20) -> List[Dict]:
        """
        Finds all documents that contain all query terms (conjunctive/AND semantics),
        then ranks these documents by cosine similarity between the query Word2Vec vector
        and each document's Word2Vec vector. Return top_n with metadata.
        """
        # Build query Word2Vec vector and get query tokens
        q_tokens = build_terms_query(query)
        q_w2v = average_vector(q_tokens, self.model)

        # Find documents that contain ALL query tokens
        matching_idx = []
        set_qtokens = set(q_tokens)
        for idx, doc_tokens in enumerate(self.terms):
            if set_qtokens.issubset(set(doc_tokens)):
                matching_idx.append(idx)

        if not matching_idx:
            # No documents match ALL terms, return empty DataFrame with columns
            return pd.DataFrame(columns=["pid", "title", "url", "cosine", "rank"])

        # Only keep doc_vectors and product metadata for matching docs
        filtered_vectors = self.doc_vectors[matching_idx]
        filtered_catalog = self.catalog_df.iloc[matching_idx]

        # Compute cosine similarity for matching docs
        cos = cosine_similarity(filtered_vectors, q_w2v.reshape(1, -1)).ravel()

        n_docs = cos.shape[0]
        n = min(top_n, n_docs)
        if n == 0:
            return []

        top_idx = np.argpartition(cos, -n)[-n:]
        top_idx = top_idx[np.argsort(cos[top_idx])[::-1]]  # sort by cosine desc

        results: List[Dict] = []
        for rank, rel_idx in enumerate(top_idx, start=1):
            row = filtered_catalog.iloc[rel_idx]
            pid = row.get("pid")
            metadata_doc = self.metadata_docs.get(pid)
            if metadata_doc:
                doc_dict = metadata_doc.model_dump()
            else:
                doc_dict = row.to_dict()
                doc_dict.setdefault("_id", pid)
            doc_dict["pid"] = pid
            doc_dict["title"] = doc_dict.get("title") or row.get("title", "")
            doc_dict["cosine"] = float(cos[rel_idx])
            doc_dict["rank"] = rank
            results.append(doc_dict)
        return results

