"""
채용 공고 검색 엔진
─────────────────────────────────────────────────────────────
1. 필터 검색  : 출처 / 근무지 / 경력 / 기술스택 / 키워드 조합
2. 시맨틱 검색: 자연어 쿼리 → 코사인 유사도 랭킹
3. 하이브리드 : 필터 먼저 좁힌 뒤 시맨틱 재랭킹

파이프라인 처리 후 컬럼 추가 지원:
  - min_exp / max_exp : 경력 수치 (Int64, nullable)
  - tech_stack        : 기술 스택 리스트 (str 직렬화 → 파싱)
  - uid               : SHA-256 해시
"""

import ast
import os
import glob
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from sklearn.metrics.pairwise import cosine_similarity

from dashboard.embedder import get_embedder, BaseEmbedder


# ── 데이터 로드 ─────────────────────────────────────────────────

def load_latest_csv(output_dir: str = "output") -> pd.DataFrame:
    """output/ 폴더에서 가장 최신 CSV를 로드한다."""
    files = sorted(glob.glob(os.path.join(output_dir, "*.csv")))
    if not files:
        return pd.DataFrame()
    return pd.read_csv(files[-1], encoding="utf-8-sig")


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    # tech_stack 컬럼이 문자열로 저장된 경우 리스트로 복원
    if "tech_stack" in df.columns:
        df["tech_stack"] = df["tech_stack"].apply(_parse_tech_stack)
    return df


def list_csv_files(output_dir: str = "output") -> List[str]:
    return sorted(glob.glob(os.path.join(output_dir, "*.csv")), reverse=True)


def _parse_tech_stack(val) -> list:
    """CSV에서 읽은 tech_stack 문자열을 리스트로 변환"""
    if isinstance(val, list):
        return val
    if not isinstance(val, str) or not val.strip():
        return []
    try:
        result = ast.literal_eval(val)
        return result if isinstance(result, list) else []
    except Exception:
        return []


# ── 경력 필터 헬퍼 ──────────────────────────────────────────────

def _exp_matches(row: pd.Series, experience: str) -> bool:
    """
    경력 필터 매칭.
    min_exp/max_exp 컬럼이 있으면 수치 기반, 없으면 텍스트 기반.
    """
    if experience == "전체":
        return True

    exp_range = {
        "신입":    (0, 0),
        "1~3년":   (1, 3),
        "3~5년":   (3, 5),
        "5년 이상": (5, 99),
    }
    target_min, target_max = exp_range.get(experience, (None, None))
    if target_min is None:
        return True

    # 수치 컬럼 우선
    if "min_exp" in row.index and pd.notna(row.get("min_exp")):
        job_min = int(row["min_exp"])
        job_max = int(row["max_exp"]) if pd.notna(row.get("max_exp")) else job_min
        # 경력무관(-1)은 모든 필터에 매칭
        if job_min == -1:
            return True
        # 범위 겹침 여부
        return job_min <= target_max and (job_max is None or job_max >= target_min)

    # 텍스트 폴백
    text_map = {
        "신입":    ["신입", "0~", "0년"],
        "1~3년":   ["1~", "2~", "3~", "1년", "2년", "3년"],
        "3~5년":   ["3~", "4~", "5~", "3년", "4년", "5년"],
        "5년 이상": ["5~", "6~", "7~", "8~", "9~", "10~", "5년", "6년", "7년"],
    }
    keywords = text_map.get(experience, [])
    exp_text = str(row.get("경력", "") or "")
    return any(k in exp_text for k in keywords)


# ── 검색 엔진 ───────────────────────────────────────────────────

class JobSearchEngine:
    def __init__(self, df: pd.DataFrame, embedder_type: str = "tfidf"):
        self.df = df.copy().reset_index(drop=True)
        self._embedder: BaseEmbedder = get_embedder(embedder_type)
        self._indexed = False
        self._build_search_text()

    def _build_search_text(self):
        """검색에 사용할 통합 텍스트 컬럼 생성 (파이프라인 컬럼 포함)"""
        # 파이프라인 처리 후 _search_text 컬럼이 있으면 재사용
        if "_search_text" in self.df.columns:
            return

        cols = ["공고제목", "회사명", "근무지", "경력", "검색키워드", "출처"]
        # tech_stack 리스트도 검색 텍스트에 포함
        if "tech_stack" in self.df.columns:
            tech_text = self.df["tech_stack"].apply(
                lambda x: " ".join(x) if isinstance(x, list) else ""
            )
        else:
            tech_text = pd.Series([""] * len(self.df))

        existing = [c for c in cols if c in self.df.columns]
        base_text = self.df[existing].fillna("").agg(" ".join, axis=1)
        self.df["_search_text"] = base_text + " " + tech_text

    def build_index(self):
        """임베딩 인덱스 구축 (최초 1회)"""
        if not self._indexed:
            self._embedder.fit(self.df["_search_text"].tolist())
            self._indexed = True

    # ── 내부용 필터 ─────────────────────────────────────────────
    def _filter(
        self,
        keyword: str = "",
        sources: List[str] = None,
        locations: List[str] = None,
        experience: str = "전체",
        tech_stack: List[str] = None,
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
            exp_mask = result.apply(lambda row: _exp_matches(row, experience), axis=1)
            result = result[exp_mask]

        # 기술 스택 필터 (tech_stack 컬럼이 있을 때만)
        if tech_stack and "tech_stack" in result.columns:
            tech_lower = [t.lower() for t in tech_stack]
            stack_mask = result["tech_stack"].apply(
                lambda x: any(t.lower() in tech_lower for t in (x if isinstance(x, list) else []))
            )
            result = result[stack_mask]

        return result  # _search_text 포함

    # ── 필터 검색 (공개 API) ────────────────────────────────────
    def filter_search(
        self,
        keyword: str = "",
        sources: List[str] = None,
        locations: List[str] = None,
        experience: str = "전체",
        tech_stack: List[str] = None,
    ) -> pd.DataFrame:
        result = self._filter(
            keyword=keyword, sources=sources,
            locations=locations, experience=experience,
            tech_stack=tech_stack,
        )
        return result.drop(columns=["_search_text"], errors="ignore")

    # ── 시맨틱 검색 ─────────────────────────────────────────────
    def semantic_search(
        self,
        query: str,
        top_k: int = 20,
        pre_filter: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        self.build_index()

        base = pre_filter if pre_filter is not None else self.df
        if base.empty:
            return base.drop(columns=["_search_text"], errors="ignore")

        texts = (
            base["_search_text"].tolist()
            if "_search_text" in base.columns
            else self.df.loc[base.index, "_search_text"].tolist()
        )

        q_vec   = self._embedder.encode_query(query)
        doc_vecs = self._embedder.encode(texts)
        scores  = cosine_similarity(q_vec, doc_vecs)[0]

        top_idx = np.argsort(scores)[::-1][:top_k]
        result  = base.iloc[top_idx].copy()
        result["유사도"] = np.round(scores[top_idx] * 100, 1)

        return result.drop(columns=["_search_text"], errors="ignore")

    # ── 하이브리드 검색 ─────────────────────────────────────────
    def hybrid_search(
        self,
        query: str,
        sources: List[str] = None,
        locations: List[str] = None,
        experience: str = "전체",
        tech_stack: List[str] = None,
        top_k: int = 20,
    ) -> pd.DataFrame:
        filtered = self._filter(
            keyword="",
            sources=sources,
            locations=locations,
            experience=experience,
            tech_stack=tech_stack,
        )
        return self.semantic_search(query, top_k=top_k, pre_filter=filtered)

    # ── 통계 ────────────────────────────────────────────────────
    def stats(self) -> Dict:
        df = self.df
        base = {
            "total":        len(df),
            "by_source":    df["출처"].value_counts().to_dict(),
            "by_location":  df["근무지"].fillna("미기재").value_counts().head(10).to_dict(),
            "by_keyword":   df["검색키워드"].value_counts().head(10).to_dict(),
            "deadline_soon": len(
                df[df["마감일"].fillna("").str.match(r"\d{4}-\d{2}-\d{2}")]
            ),
        }
        # 파이프라인 처리 후 추가 통계
        if "tech_stack" in df.columns:
            from collections import Counter
            all_techs: Counter = Counter()
            df["tech_stack"].dropna().apply(
                lambda x: all_techs.update(x) if isinstance(x, list) else None
            )
            base["top_tech"] = dict(all_techs.most_common(15))
        if "min_exp" in df.columns:
            base["exp_dist"] = df["min_exp"].value_counts().dropna().to_dict()
        return base
