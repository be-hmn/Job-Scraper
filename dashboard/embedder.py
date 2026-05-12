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

    주의: Titan Embeddings는 배치 API가 없어 건당 1회 호출.
    공고 수가 많으면 fit() 시간이 오래 걸리고 비용이 발생합니다.
    캐싱을 통해 재호출을 최소화합니다.
    """
    MODEL_ID = "amazon.titan-embed-text-v2:0"

    def __init__(self):
        import boto3, json
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        self._json   = json
        self._matrix = None  # fit() 결과 캐시

    def _embed_one(self, text: str) -> np.ndarray:
        body = self._json.dumps({"inputText": text[:8000]})
        resp = self._client.invoke_model(modelId=self.MODEL_ID, body=body)
        return np.array(self._json.loads(resp["body"].read())["embedding"])

    def _embed_batch(self, texts: List[str]) -> np.ndarray:
        """진행 상황을 로깅하며 배치 임베딩"""
        import logging
        logger = logging.getLogger(__name__)
        vectors = []
        for i, text in enumerate(texts):
            vectors.append(self._embed_one(text))
            if (i + 1) % 50 == 0:
                logger.info("[Bedrock] 임베딩 진행: %d / %d", i + 1, len(texts))
        return np.vstack(vectors)

    def fit(self, texts: List[str]) -> None:
        """전체 공고 임베딩 — 결과를 캐시해서 재호출 방지"""
        import logging
        logging.getLogger(__name__).info(
            "[Bedrock] %d건 임베딩 시작 (건당 1회 API 호출)", len(texts)
        )
        self._matrix = self._embed_batch(texts)

    def encode(self, texts: List[str]) -> np.ndarray:
        return self._embed_batch(texts)

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

# 각 임베더에 필요한 패키지 목록
_REQUIRED_PACKAGES = {
    "local":   ("sentence_transformers", "pip install sentence-transformers"),
    "bedrock": ("boto3",                 "pip install boto3"),
    "openai":  ("openai",                "pip install openai"),
}


def _check_package(module_name: str, install_hint: str) -> bool:
    """패키지 설치 여부 확인. 없으면 False 반환."""
    import importlib
    if importlib.util.find_spec(module_name) is None:
        import logging
        logging.getLogger(__name__).error(
            "'%s' 패키지가 설치되지 않았습니다. 설치 명령: %s",
            module_name, install_hint,
        )
        return False
    return True


def get_embedder(embedder_type: str = None) -> BaseEmbedder:
    t = (embedder_type or EMBEDDER_TYPE).lower()

    if t == "local":
        pkg, hint = _REQUIRED_PACKAGES["local"]
        if not _check_package(pkg, hint):
            return TFIDFEmbedder()
        return LocalEmbedder()

    elif t == "bedrock":
        pkg, hint = _REQUIRED_PACKAGES["bedrock"]
        if not _check_package(pkg, hint):
            return TFIDFEmbedder()
        return BedrockEmbedder()

    elif t == "openai":
        pkg, hint = _REQUIRED_PACKAGES["openai"]
        if not _check_package(pkg, hint):
            return TFIDFEmbedder()
        return OpenAIEmbedder()

    else:
        return TFIDFEmbedder()
