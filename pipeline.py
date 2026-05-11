"""
채용 공고 데이터 정제 파이프라인
==============================
실행: python pipeline.py [--input output/파일명.csv] [--output output/cleaned_job_postings.csv]

기능:
  A. Fuzzy Matching 기반 고도화 중복 제거 (RapidFuzz, 유사도 90% 이상)
  B. 경력 수치화 (min_exp / max_exp), 기술 스택 추출 (tech_stack)
  C. SHA-256 uid 기반 증분 저장 (기존 파일에 신규 공고만 Append)
  D. description 텍스트 전처리 (자연어 검색 매칭용)
"""

import re
import hashlib
import logging
import argparse
import os
import glob
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

# ── 로깅 설정 ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── 상수 ─────────────────────────────────────────────────────────
OUTPUT_DIR   = "output"
CLEANED_FILE = os.path.join(OUTPUT_DIR, "cleaned_job_postings.csv")
FUZZY_THRESHOLD = 90  # 유사도 임계값 (%)

# 기술 스택 키워드 (대소문자 무관 매칭)
TECH_KEYWORDS = [
    # 언어
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang",
    "Kotlin", "Swift", "C++", "C#", "Rust", "Scala", "Ruby", "PHP",
    # 프레임워크/라이브러리
    "React", "Vue", "Angular", "Next.js", "Nuxt", "Spring", "Django",
    "FastAPI", "Flask", "Node.js", "Express", "NestJS", "Laravel",
    # 인프라/DevOps
    "Docker", "Kubernetes", "K8s", "Terraform", "Ansible", "Jenkins",
    "GitHub Actions", "GitLab CI", "ArgoCD", "Helm",
    # 클라우드
    "AWS", "GCP", "Azure", "Cloudflare",
    # 데이터베이스
    "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
    "Cassandra", "DynamoDB", "Oracle", "MSSQL", "SQLite",
    # 데이터/AI
    "Spark", "Kafka", "Airflow", "dbt", "Hadoop", "Flink",
    "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
    "LLM", "RAG", "MLflow", "Kubeflow",
    # 보안
    "SIEM", "SOC", "WAF", "IDS", "IPS", "OWASP", "Burp Suite",
    "Metasploit", "Splunk", "QRadar",
    # 기타
    "Git", "Linux", "Nginx", "gRPC", "GraphQL", "REST", "MSA",
]

# 경력 추출 패턴
_EXP_PATTERNS = [
    # "3~5년", "3-5년", "3년~5년"
    (re.compile(r"(\d+)\s*[~\-]\s*(\d+)\s*년"), "range"),
    # "3년 이상", "3년↑"
    (re.compile(r"(\d+)\s*년\s*(이상|↑)"), "min_only"),
    # "경력 3년", "경력3년"
    (re.compile(r"경력\s*(\d+)\s*년"), "single"),
    # "신입"
    (re.compile(r"신입"), "entry"),
    # "경력무관", "무관"
    (re.compile(r"경력\s*무관|무관"), "any"),
    # "10년↑" (숫자+↑)
    (re.compile(r"(\d+)\s*년\s*↑"), "min_only"),
]


# ════════════════════════════════════════════════════════════════
# A. 텍스트 전처리
# ════════════════════════════════════════════════════════════════

def preprocess_text(text: str) -> str:
    """
    자연어 검색 매칭을 위한 텍스트 전처리.
    - 특수문자 제거 (단, 기술 스택 관련 문자 보존: +, #, .)
    - 연속 공백 정규화
    - 소문자 변환
    """
    if not isinstance(text, str):
        return ""
    # C++, C#, .NET 등 보존을 위해 알파벳/숫자/한글/공백/+#. 만 유지
    text = re.sub(r"[^\w\s\+\#\.\-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def build_search_text(row: pd.Series) -> str:
    """검색용 통합 텍스트 생성 (공고제목 + 회사명 + 검색키워드)"""
    parts = [
        str(row.get("공고제목", "") or ""),
        str(row.get("회사명", "") or ""),
        str(row.get("검색키워드", "") or ""),
        str(row.get("경력", "") or ""),
    ]
    return preprocess_text(" ".join(parts))


# ════════════════════════════════════════════════════════════════
# B-1. 경력 수치화
# ════════════════════════════════════════════════════════════════

def parse_experience(text: str) -> tuple[int, int]:
    """
    경력 텍스트에서 (min_exp, max_exp) 추출.
    반환값: (min, max) — 신입=0,0 / 무관=-1,-1 / 미기재=None,None
    """
    if not isinstance(text, str) or not text.strip():
        return (None, None)

    for pattern, kind in _EXP_PATTERNS:
        m = pattern.search(text)
        if m:
            if kind == "range":
                return (int(m.group(1)), int(m.group(2)))
            elif kind == "min_only":
                return (int(m.group(1)), None)
            elif kind == "single":
                v = int(m.group(1))
                return (v, v)
            elif kind == "entry":
                return (0, 0)
            elif kind == "any":
                return (-1, -1)

    return (None, None)


def add_experience_columns(df: pd.DataFrame) -> pd.DataFrame:
    """경력 컬럼에서 min_exp / max_exp 파생 컬럼 생성 (Vectorized)"""
    # 경력 컬럼이 없으면 공고제목에서도 시도
    exp_text = df["경력"].fillna("").astype(str)
    # 경력 컬럼이 비어있으면 공고제목에서 보완
    mask_empty = exp_text.str.strip() == ""
    exp_text[mask_empty] = df.loc[mask_empty, "공고제목"].fillna("").astype(str)

    parsed = exp_text.map(parse_experience)
    df["min_exp"] = parsed.map(lambda x: x[0] if x else None).astype("Int64")
    df["max_exp"] = parsed.map(lambda x: x[1] if x else None).astype("Int64")
    return df


# ════════════════════════════════════════════════════════════════
# B-2. 기술 스택 추출
# ════════════════════════════════════════════════════════════════

# 미리 컴파일된 패턴 (단어 경계 적용)
_TECH_PATTERNS = {
    kw: re.compile(r"(?<![a-zA-Z])" + re.escape(kw) + r"(?![a-zA-Z])", re.IGNORECASE)
    for kw in TECH_KEYWORDS
}


def extract_tech_stack(text: str) -> list[str]:
    """텍스트에서 기술 스택 키워드 추출"""
    if not isinstance(text, str):
        return []
    found = [kw for kw, pat in _TECH_PATTERNS.items() if pat.search(text)]
    return found


def add_tech_stack_column(df: pd.DataFrame) -> pd.DataFrame:
    """공고제목 + 검색키워드 통합 텍스트에서 tech_stack 컬럼 생성"""
    combined = (
        df["공고제목"].fillna("").astype(str)
        + " "
        + df["검색키워드"].fillna("").astype(str)
    )
    df["tech_stack"] = combined.map(extract_tech_stack)
    return df


# ════════════════════════════════════════════════════════════════
# C. SHA-256 uid 생성
# ════════════════════════════════════════════════════════════════

def make_uid(row: pd.Series) -> str:
    """회사명 + 공고제목 + URL 조합의 SHA-256 해시"""
    raw = "|".join([
        str(row.get("회사명", "") or "").strip(),
        str(row.get("공고제목", "") or "").strip(),
        str(row.get("공고URL", "") or "").strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_uid_column(df: pd.DataFrame) -> pd.DataFrame:
    """uid 컬럼 추가 (Vectorized)"""
    df["uid"] = df.apply(make_uid, axis=1)
    return df


# ════════════════════════════════════════════════════════════════
# A. Fuzzy Matching 기반 중복 제거
# ════════════════════════════════════════════════════════════════

def fuzzy_deduplicate(df: pd.DataFrame, threshold: int = FUZZY_THRESHOLD) -> pd.DataFrame:
    """
    (회사명 + 공고제목) 결합 텍스트의 RapidFuzz 유사도가 threshold% 이상이면
    동일 공고로 간주하고 마감일이 최신인 것만 유지.

    성능 최적화:
    - 먼저 uid 기준 정확 중복 제거
    - 이후 출처별로 그룹화하여 Fuzzy 비교 범위 축소
    """
    before = len(df)

    # 1단계: uid 기준 정확 중복 제거
    df = df.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)
    logger.info("  정확 중복 제거: %d건 → %d건", before, len(df))

    # 2단계: Fuzzy 중복 제거
    # 비교 키: 회사명 + 공고제목 소문자 결합
    df["_fuzzy_key"] = (
        df["회사명"].fillna("").astype(str).str.strip().str.lower()
        + " "
        + df["공고제목"].fillna("").astype(str).str.strip().str.lower()
    )

    # 마감일 기준 정렬 (최신 우선 — 마감일 없으면 뒤로)
    df["_sort_key"] = df["마감일"].fillna("").astype(str)
    df = df.sort_values("_sort_key", ascending=False).reset_index(drop=True)

    keep_mask = [True] * len(df)
    keys = df["_fuzzy_key"].tolist()

    for i in range(len(df)):
        if not keep_mask[i]:
            continue
        for j in range(i + 1, len(df)):
            if not keep_mask[j]:
                continue
            score = fuzz.token_sort_ratio(keys[i], keys[j])
            if score >= threshold:
                keep_mask[j] = False  # 최신(i)을 유지, 오래된(j) 제거

    df = df[keep_mask].reset_index(drop=True)
    df = df.drop(columns=["_fuzzy_key", "_sort_key"], errors="ignore")

    logger.info("  Fuzzy 중복 제거 (임계값 %d%%): → %d건", threshold, len(df))
    return df


# ════════════════════════════════════════════════════════════════
# C. 증분 저장 (Hash 기반 Append)
# ════════════════════════════════════════════════════════════════

def incremental_save(new_df: pd.DataFrame, output_path: str) -> pd.DataFrame:
    """
    기존 파일의 uid와 대조하여 신규 공고만 Append 저장.
    기존 파일이 없으면 전체 저장.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if os.path.exists(output_path):
        existing = pd.read_csv(output_path, encoding="utf-8-sig")
        existing_uids = set(existing["uid"].dropna().tolist())
        new_only = new_df[~new_df["uid"].isin(existing_uids)]
        logger.info(
            "  증분 저장: 기존 %d건 / 신규 %d건 / 추가 대상 %d건",
            len(existing), len(new_df), len(new_only),
        )
        if not new_only.empty:
            combined = pd.concat([existing, new_only], ignore_index=True)
            combined.to_csv(output_path, index=False, encoding="utf-8-sig")
            logger.info("  저장 완료: 총 %d건 → %s", len(combined), output_path)
        else:
            logger.info("  신규 공고 없음 — 파일 유지")
        return new_only
    else:
        new_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info("  최초 저장: %d건 → %s", len(new_df), output_path)
        return new_df


# ════════════════════════════════════════════════════════════════
# 메인 파이프라인
# ════════════════════════════════════════════════════════════════

def run_pipeline(input_path: str, output_path: str) -> pd.DataFrame:
    """
    전체 정제 파이프라인 실행.
    반환값: 최종 정제된 DataFrame
    """
    logger.info("=" * 60)
    logger.info("파이프라인 시작")
    logger.info("  입력: %s", input_path)
    logger.info("  출력: %s", output_path)
    logger.info("=" * 60)

    # ── 로드 ────────────────────────────────────────────────────
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    logger.info("[1/6] 로드 완료: %d건", len(df))

    # ── uid 생성 ─────────────────────────────────────────────────
    df = add_uid_column(df)
    logger.info("[2/6] uid 생성 완료: %d건", len(df))

    # ── Fuzzy 중복 제거 ──────────────────────────────────────────
    logger.info("[3/6] 중복 제거 시작...")
    df = fuzzy_deduplicate(df, threshold=FUZZY_THRESHOLD)
    logger.info("[3/6] 중복 제거 완료: %d건", len(df))

    # ── 경력 수치화 ──────────────────────────────────────────────
    df = add_experience_columns(df)
    filled = df["min_exp"].notna().sum()
    logger.info("[4/6] 경력 수치화 완료: %d건 파싱 성공 / %d건 미파싱", filled, len(df) - filled)

    # ── 기술 스택 추출 ───────────────────────────────────────────
    df = add_tech_stack_column(df)
    has_stack = (df["tech_stack"].map(len) > 0).sum()
    logger.info("[5/6] 기술 스택 추출 완료: %d건에서 키워드 발견", has_stack)

    # ── 검색용 텍스트 전처리 ─────────────────────────────────────
    df["_search_text"] = df.apply(build_search_text, axis=1)
    logger.info("[6/6] 검색 텍스트 전처리 완료: %d건", len(df))

    # ── 증분 저장 ────────────────────────────────────────────────
    new_records = incremental_save(df, output_path)

    logger.info("=" * 60)
    logger.info("파이프라인 완료 — 최종 %d건 / 신규 %d건", len(df), len(new_records))
    logger.info("=" * 60)

    return df


def get_latest_csv(directory: str = OUTPUT_DIR) -> Optional[str]:
    """output/ 폴더에서 가장 최신 원본 CSV 반환 (cleaned 제외)"""
    files = sorted(
        [f for f in glob.glob(os.path.join(directory, "it_security_jobs_*.csv"))],
        reverse=True,
    )
    return files[0] if files else None


# ════════════════════════════════════════════════════════════════
# CLI 진입점
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="채용 공고 데이터 정제 파이프라인")
    parser.add_argument(
        "--input", "-i",
        default=None,
        help="입력 CSV 경로 (기본: output/ 폴더의 최신 it_security_jobs_*.csv)",
    )
    parser.add_argument(
        "--output", "-o",
        default=CLEANED_FILE,
        help=f"출력 CSV 경로 (기본: {CLEANED_FILE})",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=int,
        default=FUZZY_THRESHOLD,
        help=f"Fuzzy 유사도 임계값 %% (기본: {FUZZY_THRESHOLD})",
    )
    args = parser.parse_args()

    input_path = args.input or get_latest_csv()
    if not input_path:
        logger.error("입력 파일을 찾을 수 없습니다. --input 옵션으로 경로를 지정하세요.")
        raise SystemExit(1)

    run_pipeline(input_path, args.output)
