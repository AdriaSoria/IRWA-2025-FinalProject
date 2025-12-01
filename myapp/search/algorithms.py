"""
Search algorithms powered by Word2Vec + cosine similarity ranking.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Sequence, TYPE_CHECKING

import nltk
import numpy as np
import pandas as pd
from gensim.models import Word2Vec
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize
from sklearn.metrics.pairwise import cosine_similarity

if TYPE_CHECKING:
    from myapp.search.search_engine import Word2VecRetrieval


def _ensure_nltk_resources() -> None:
    """Download required NLTK corpora if they are missing."""
    resources = {
        "punkt": "tokenizers/punkt",
        "stopwords": "corpora/stopwords",
    }
    for name, resource_path in resources.items():
        try:
            nltk.data.find(resource_path)
        except LookupError:
            nltk.download(name, quiet=True)


_ensure_nltk_resources()

STEMMER = PorterStemmer()
STOP_WORDS = set(stopwords.words("english"))


def build_terms_query(text: str) -> List[str]:
    """
    Tokenize and normalize the user query into lowercase, stemmed tokens.
    """
    if not text:
        return []
    cleaned = re.sub(r"[^a-z\s]", " ", text.lower())
    tokens = [tok for tok in word_tokenize(cleaned) if tok and tok not in STOP_WORDS]
    return [STEMMER.stem(tok) for tok in tokens]


def build_terms_doc(text: str) -> List[str]:
    """
    Tokenize catalogue content into lowercase alphanumeric tokens.
    """
    if not text:
        return []
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return [tok for tok in word_tokenize(cleaned) if tok.strip()]


def average_vector(tokens: Sequence[str], model: Word2Vec) -> np.ndarray:
    """Compute the average Word2Vec embedding for a bag of tokens."""
    if not tokens:
        return np.zeros(model.wv.vector_size, dtype=np.float32)
    vectors = [model.wv[tok] for tok in tokens if tok in model.wv]
    if not vectors:
        return np.zeros(model.wv.vector_size, dtype=np.float32)
    return np.mean(vectors, axis=0)


MYAPP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA_PATH = MYAPP_DIR / "products.json"
DEFAULT_CSV_PATH = PROJECT_ROOT / "data" / "productos_preprocesados.csv"




@lru_cache(maxsize=1)
def get_retrieval_engine(
    catalog_csv_path: Path = DEFAULT_CSV_PATH,
    metadata_path: Path = DEFAULT_METADATA_PATH,
) -> "Word2VecRetrieval":
    from myapp.search.search_engine import Word2VecRetrieval

    return Word2VecRetrieval(catalog_csv_path=catalog_csv_path, metadata_path=metadata_path)


def search_top20_w2v(
    query: str,
    top_n: int = 20,
    catalog_csv_path: Path = DEFAULT_CSV_PATH,
    metadata_path: Path = DEFAULT_METADATA_PATH,
) -> List[Dict]:
    engine = get_retrieval_engine(catalog_csv_path=catalog_csv_path, metadata_path=metadata_path)
    return engine.search(query=query, top_n=top_n)
