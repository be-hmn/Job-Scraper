"""
채용 공고 검색 엔진
─────────────────────────────────────────────────────────────
1. 필터 검색  : 출처 / 근무지 / 경력 / 키워드 조합
2. 시맨틱 검색: 자연어 쿼리 → 코사인 유사도 랭킹
3. 하이브리드 : 필터 먼저 좁힌 뒤 시맨틱 재랭킹
"""

import os
import glob
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from sklearn.metrics.pairwise import cosine_similarity

from dashboard.embedder import get_embedder, BaseEmbedder


# ── 데이터 로드 ──────────────────────────────────────────────────
def load_latest_csv(output_dir: str = "output") -> pd.DataFrame:
    """output/ 폴더에서 가장 최신 CSV를 로드한다."""
    files = sorted(glob.glob(os.path.join(output_dir, "*.csv")))
    if not files:
        return pd.DataFrame()
    return pd.read_csv(files[-1], encoding="utf-8-sig")


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def list_csv_files(output_dir: str = "output") -> List[str]:
    return sorted(glob.glob(os.path.join(output_dir, "*.csv")), reverse=True)


# ── 검색 엔진 ────────────────────────────────────────────────────
class JobSearchEngine:
    def __init__(self, df: pd.DataFrame, embedder_type: str = "tfidf"):
        self.df = df.copy().reset_index(drop=True)
        self._embedder: BaseEmbedder = get_embedder(embedder_type)
        self._indexed = False
        self._build_search_text()

    def _build_search_text(self):
        """검색에 사용할 통합 텍스트 컬럼 생성"""
        cols = ["공고제목", "회사명", "근무지", "경력", "검색키워드", "출처"]
        existing = [c for c in cols if c in self.df.columns]
        self.df["_search_text"] = self.df[existing].fillna("").agg(" ".join, axis=1)

    def build_index(self):
        """임베딩 인덱스 구축 (최초 1회)"""
        if not self._indexed:
            self._embedder.fit(self.df["_search_text"].tolist())
            self._indexed = True

    # ── 필터 검색 ────────────────────────────────────────────────
    def filter_search(
        self,
        keyword: str = "",
        sources: List[str] = None,
        locations: List[str] = None,
        experience: str = "전체",
    ) -> pd.DataFrame:
        result = self.df.copy()

        if keyword:
            kw = keyword.lower()
            mask = result["_search_text"].str.lower().str.contains(kw, na=False)
            result = result[mask]

        if sources:
            result = result[result["출처"].isin(sources)]

        if locations:
            loc_mask = result["근무지"].fillna("").apply(
                lambda x: any(loc in x for loc in locations)
            )
            result = result[loc_mask]

        if experience != "전체":
            exp_map = {
                "신입": ["신입", "0~", "0년"],
                "1~3년": ["1~", "2~", "3~", "1년", "2년", "3년"],
                "3~5년": ["3~", "4~", "5~", "3년", "4년", "5년"],
                "5년 이상": ["5~", "6~", "7~", "8~", "9~", "10~", "5년", "6년", "7년"],
            }
            keywords = exp_map.get(experience, [])
            if keywords:
                exp_mask = result["경력"].fillna("").apply(
                    lambda x: any(k in x for k in keywords)
                )
                result = result[exp_mask]

        return result.drop(columns=["_search_text"], errors="ignore")

    # ── 시맨틱 검색 ─────────────────────────────────────────────
    def semantic_search(
        self,
        query: str,
        top_k: int = 20,
        pre_filter: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        자연어 쿼리로 가장 관련성 높은 공고를 반환한다.
        pre_filter: 필터 검색 결과를 먼저 좁힌 뒤 시맨틱 재랭킹할 때 사용
        """
        self.build_index()

        base = pre_filter if pre_filter is not None else self.df
        if base.empty:
            return base

        # 쿼리 임베딩
        q_vec = self._embedder.encode_query(query)

        # 후보 문서 임베딩
        texts = base["_search_text"].tolist() if "_search_text" in base.columns else \
                self.df.loc[base.index, "_search_text"].tolist()

        doc_vecs = self._embedder.encode(texts)

        # 코사인 유사도
        scores = cosine_similarity(q_vec, doc_vecs)[0]

        # 상위 k개 인덱스
        top_idx = np.argsort(scores)[::-1][:top_k]
        result = base.iloc[top_idx].copy()
        result["유사도"] = np.round(scores[top_idx] * 100, 1)

        return result.drop(columns=["_search_text"], errors="ignore")

    # ── 하이브리드 검색 ──────────────────────────────────────────
    def hybrid_search(
        self,
        query: str,
        sources: List[str] = None,
        locations: List[str] = None,
        experience: str = "전체",
        top_k: int = 20,
    ) -> pd.DataFrame:
        """필터로 후보를 좁힌 뒤 시맨틱 재랭킹"""
        filtered = self.filter_search(
            keyword="",
            sources=sources,
            locations=locations,
            experience=experience,
        )
        # 필터 결과에 _search_text 복원
        filtered = filtered.copy()
        filtered["_search_text"] = self.df.loc[filtered.index, "_search_text"].values

        return self.semantic_search(query, top_k=top_k, pre_filter=filtered)

    # ── 통계 ─────────────────────────────────────────────────────
    def stats(self) -> Dict:
        df = self.df
        return {
            "total": len(df),
            "by_source": df["출처"].value_counts().to_dict(),
            "by_location": df["근무지"].fillna("미기재").value_counts().head(10).to_dict(),
            "by_keyword": df["검색키워드"].value_counts().head(10).to_dict(),
            "deadline_soon": len(
                df[df["마감일"].fillna("").str.match(r"\d{4}-\d{2}-\d{2}")]
            ),
        }
