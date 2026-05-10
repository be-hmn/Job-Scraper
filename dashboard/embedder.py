"""
임베딩 추상 레이어
─────────────────────────────────────────────────────────────
현재: TF-IDF (설치 없이 즉시 사용, 한국어 형태소 불필요)
확장: sentence-transformers 로컬 모델 or AWS Bedrock / OpenAI API

교체 방법:
  .env 에 EMBEDDER=tfidf | local | bedrock | openai 설정
"""

import os
import numpy as np
from typing import List

EMBEDDER_TYPE = os.getenv("EMBEDDER", "tfidf")  # 기본값: tfidf


# ── 공통 인터페이스 ──────────────────────────────────────────────
class BaseEmbedder:
    def fit(self, texts: List[str]) -> None: ...
    def encode(self, texts: List[str]) -> np.ndarray: ...
    def encode_query(self, query: str) -> np.ndarray: ...


# ── TF-IDF (기본, 설치 불필요) ───────────────────────────────────
class TFIDFEmbedder(BaseEmbedder):
    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._vec = TfidfVectorizer(
            analyzer="char_wb",   # 문자 n-gram → 한국어에 효과적
            ngram_range=(2, 4),
            max_features=20_000,
            sublinear_tf=True,
        )
        self._matrix = None

    def fit(self, texts: List[str]) -> None:
        self._matrix = self._vec.fit_transform(texts)

    def encode(self, texts: List[str]) -> np.ndarray:
        return self._vec.transform(texts)

    def encode_query(self, query: str) -> np.ndarray:
        return self._vec.transform([query])


# ── sentence-transformers 로컬 모델 ─────────────────────────────
class LocalEmbedder(BaseEmbedder):
    """
    다국어 모델: paraphrase-multilingual-MiniLM-L12-v2
    첫 실행 시 ~120MB 자동 다운로드
    """
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self.MODEL_NAME)
        self._matrix = None

    def fit(self, texts: List[str]) -> None:
        self._matrix = self._model.encode(texts, show_progress_bar=False)

    def encode(self, texts: List[str]) -> np.ndarray:
        return self._model.encode(texts, show_progress_bar=False)

    def encode_query(self, query: str) -> np.ndarray:
        return self._model.encode([query], show_progress_bar=False)


# ── AWS Bedrock (Titan Embeddings) ──────────────────────────────
class BedrockEmbedder(BaseEmbedder):
    """
    AWS Bedrock Titan Embeddings V2
    필요: boto3, AWS 자격증명 설정
    """
    MODEL_ID = "amazon.titan-embed-text-v2:0"

    def __init__(self):
        import boto3, json
        self._client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        self._json = json
        self._matrix = None

    def _embed_one(self, text: str) -> np.ndarray:
        body = self._json.dumps({"inputText": text[:8000]})
        resp = self._client.invoke_model(modelId=self.MODEL_ID, body=body)
        return np.array(self._json.loads(resp["body"].read())["embedding"])

    def fit(self, texts: List[str]) -> None:
        self._matrix = np.vstack([self._embed_one(t) for t in texts])

    def encode(self, texts: List[str]) -> np.ndarray:
        return np.vstack([self._embed_one(t) for t in texts])

    def encode_query(self, query: str) -> np.ndarray:
        return self._embed_one(query).reshape(1, -1)


# ── OpenAI Embeddings ────────────────────────────────────────────
class OpenAIEmbedder(BaseEmbedder):
    """
    OpenAI text-embedding-3-small
    필요: openai 패키지, OPENAI_API_KEY 환경변수
    """
    MODEL = "text-embedding-3-small"

    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._matrix = None

    def _embed(self, texts: List[str]) -> np.ndarray:
        resp = self._client.embeddings.create(model=self.MODEL, input=texts)
        return np.array([d.embedding for d in resp.data])

    def fit(self, texts: List[str]) -> None:
        self._matrix = self._embed(texts)

    def encode(self, texts: List[str]) -> np.ndarray:
        return self._embed(texts)

    def encode_query(self, query: str) -> np.ndarray:
        return self._embed([query])


# ── 팩토리 ───────────────────────────────────────────────────────
def get_embedder(embedder_type: str = None) -> BaseEmbedder:
    t = (embedder_type or EMBEDDER_TYPE).lower()
    if t == "local":
        return LocalEmbedder()
    elif t == "bedrock":
        return BedrockEmbedder()
    elif t == "openai":
        return OpenAIEmbedder()
    else:
        return TFIDFEmbedder()
