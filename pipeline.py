"""
채용 공고 데이터 정제 파이프라인
==============================
기본 실행: python pipeline.py
  - DB에서 미정제 공고를 읽어 정제 후 DB 업데이트

CSV 입력: python pipeline.py --input output/파일명.csv
  - CSV 파일을 읽어 정제 후 DB에 저장

처리 순서:
  1. 데이터 로드 (DB 또는 CSV)
  2. uid 생성 (SHA-256)
  3. 원본 통계 스냅샷 저장
  4. Fuzzy Matching 기반 중복 제거
  5. 경력 수치화 (min_exp / max_exp)
  6. 기술 스택 추출 (tech_stack)
  7. 검색용 텍스트 전처리 (_search_text)
  8. DB 저장 (upsert)
"""

import re
import json
import hashlib
import logging
import argparse
import os
import glob
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
from rapidfuzz import fuzz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR      = "output"
STATS_FILE      = os.path.join(OUTPUT_DIR, "pipeline_stats.json")
FUZZY_THRESHOLD = 90

TECH_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Golang",
    "Kotlin", "Swift", "C++", "C#", "Rust", "Scala", "Ruby", "PHP",
    "React", "Vue", "Angular", "Next.js", "Nuxt", "Spring", "Django",
    "FastAPI", "Flask", "Node.js", "Express", "NestJS", "Laravel",
    "Docker", "Kubernetes", "K8s", "Terraform", "Ansible", "Jenkins",
    "GitHub Actions", "GitLab CI", "ArgoCD", "Helm",
    "AWS", "GCP", "Azure", "Cloudflare",
    "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
    "Cassandra", "DynamoDB", "Oracle", "MSSQL", "SQLite",
    "Spark", "Kafka", "Airflow", "dbt", "Hadoop", "Flink",
    "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
    "LLM", "RAG", "MLflow", "Kubeflow",
    "SIEM", "SOC", "WAF", "IDS", "IPS", "OWASP", "Burp Suite",
    "Metasploit", "Splunk", "QRadar",
    "Git", "Linux", "Nginx", "gRPC", "GraphQL", "REST", "MSA",
]

_EXP_PATTERNS = [
    (re.compile(r"(\d+)\s*[~\-]\s*(\d+)\s*년"), "range"),
    (re.compile(r"(\d+)\s*년\s*(이상|↑)"),       "min_only"),
    (re.compile(r"경력\s*(\d+)\s*년"),            "single"),
    (re.compile(r"신입"),                          "entry"),
    (re.compile(r"경력\s*무관|무관"),              "any"),
]

_TECH_PATTERNS = {
    kw: re.compile(r"(?<![a-zA-Z])" + re.escape(kw) + r"(?![a-zA-Z])", re.IGNORECASE)
    for kw in TECH_KEYWORDS
}


# ════════════════════════════════════════════════════════════════
# 정제 함수들
# ════════════════════════════════════════════════════════════════

def preprocess_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[^\w\s\+\#\.\-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def build_search_text(row: pd.Series) -> str:
    parts = [
        str(row.get("공고제목", "") or ""),
        str(row.get("회사명", "") or ""),
        str(row.get("검색키워드", "") or ""),
        str(row.get("경력", "") or ""),
    ]
    return preprocess_text(" ".join(parts))


def make_uid(row: pd.Series) -> str:
    raw = "|".join([
        str(row.get("회사명", "") or "").strip(),
        str(row.get("공고제목", "") or "").strip(),
        str(row.get("공고URL", "") or "").strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_uid_column(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["uid"] = df.apply(make_uid, axis=1)
    return df


def parse_experience(text: str) -> tuple:
    if not isinstance(text, str) or not text.strip():
        return (None, None)
    for pattern, kind in _EXP_PATTERNS:
        m = pattern.search(text)
        if m:
            if kind == "range":    return (int(m.group(1)), int(m.group(2)))
            elif kind == "min_only": return (int(m.group(1)), None)
            elif kind == "single": v = int(m.group(1)); return (v, v)
            elif kind == "entry":  return (0, 0)
            elif kind == "any":    return (-1, -1)
    return (None, None)


def add_experience_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    exp_text = df["경력"].fillna("").astype(str)
    exp_text = exp_text.where(
        exp_text.str.strip() != "",
        other=df["공고제목"].fillna("").astype(str),
    )
    parsed = exp_text.map(parse_experience)
    df["min_exp"] = parsed.map(lambda x: x[0] if x else None).astype("Int64")
    df["max_exp"] = parsed.map(lambda x: x[1] if x else None).astype("Int64")
    return df


def extract_tech_stack(text: str) -> list:
    if not isinstance(text, str):
        return []
    return [kw for kw, pat in _TECH_PATTERNS.items() if pat.search(text)]


def add_tech_stack_column(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    combined = (
        df["공고제목"].fillna("").astype(str)
        + " "
        + df["검색키워드"].fillna("").astype(str)
    )
    df["tech_stack"] = combined.map(extract_tech_stack)
    return df


def fuzzy_deduplicate(df: pd.DataFrame, threshold: int = FUZZY_THRESHOLD) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates(subset=["uid"], keep="first").reset_index(drop=True)
    logger.info("  정확 중복 제거: %d건 → %d건", before, len(df))

    df["_fuzzy_key"] = (
        df["회사명"].fillna("").astype(str).str.strip().str.lower()
        + " "
        + df["공고제목"].fillna("").astype(str).str.strip().str.lower()
    )
    df["_has_company"] = df["회사명"].fillna("").astype(str).str.strip() != ""
    df["_sort_key"]    = df["마감일"].fillna("").astype(str)
    df = df.sort_values("_sort_key", ascending=False).reset_index(drop=True)

    keep_mask   = [True] * len(df)
    keys        = df["_fuzzy_key"].tolist()
    has_company = df["_has_company"].tolist()

    for i in range(len(df)):
        if not keep_mask[i] or not has_company[i]:
            continue
        for j in range(i + 1, len(df)):
            if not keep_mask[j] or not has_company[j]:
                continue
            if fuzz.token_sort_ratio(keys[i], keys[j]) >= threshold:
                keep_mask[j] = False

    df = df[keep_mask].reset_index(drop=True)
    df = df.drop(columns=["_fuzzy_key", "_sort_key", "_has_company"], errors="ignore")

    removed = before - len(df)
    logger.info(
        "  Fuzzy 중복 제거 (임계값 %d%%, 회사명 없는 공고 제외): %d건 제거 → %d건 남음",
        threshold, removed, len(df),
    )
    return df


def snapshot_stats(df: pd.DataFrame, source_label: str) -> dict:
    by_source    = df["출처"].value_counts().to_dict()
    intern_count = int(df["공고제목"].str.contains("인턴|intern", case=False, na=False).sum())
    has_deadline = int(df["마감일"].fillna("").astype(str).str.strip().ne("").sum())
    no_company   = int(df["회사명"].fillna("").astype(str).str.strip().eq("").sum())

    stats = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source":       source_label,
        "total_raw":    len(df),
        "by_source":    by_source,
        "intern_count": intern_count,
        "has_deadline": has_deadline,
        "no_company":   no_company,
    }

    logger.info("  ┌─ 원본 통계 스냅샷 ─────────────────────────")
    logger.info("  │  총 공고 수    : %d건", stats["total_raw"])
    logger.info("  │  인턴 공고     : %d건", intern_count)
    logger.info("  │  마감일 있음   : %d건", has_deadline)
    logger.info("  │  회사명 없음   : %d건 (Fuzzy 비교 제외 대상)", no_company)
    logger.info("  │  출처별 건수   :")
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
        logger.info("  │    %-14s %d건", src, cnt)
    logger.info("  └────────────────────────────────────────────")
    return stats


def save_stats(stats: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    logger.info("  통계 저장 완료: %s", STATS_FILE)


# ════════════════════════════════════════════════════════════════
# 핵심 정제 로직 (입력 형태 무관)
# ════════════════════════════════════════════════════════════════

def _refine(df: pd.DataFrame, source_label: str, threshold: int) -> pd.DataFrame:
    """DataFrame을 받아 정제 후 반환 (저장은 호출자가 담당)"""
    logger.info("=" * 60)
    logger.info("파이프라인 시작  (%s, %d건)", source_label, len(df))
    logger.info("=" * 60)

    df = add_uid_column(df)
    logger.info("[1] uid 생성 완료")

    stats = snapshot_stats(df, source_label)
    save_stats(stats)
    logger.info("[2] 통계 스냅샷 저장")

    df = fuzzy_deduplicate(df, threshold)
    stats["total_after_dedup"] = len(df)
    stats["removed_by_dedup"]  = stats["total_raw"] - len(df)
    save_stats(stats)
    logger.info("[3] 중복 제거 완료: %d건", len(df))

    df = add_experience_columns(df)
    filled = int(df["min_exp"].notna().sum())
    logger.info("[4] 경력 수치화: %d건 파싱 성공", filled)

    df = add_tech_stack_column(df)
    has_stack = int((df["tech_stack"].map(len) > 0).sum())
    logger.info("[5] 기술 스택 추출: %d건에서 키워드 발견", has_stack)

    df["_search_text"] = df.apply(build_search_text, axis=1)
    logger.info("[6] 검색 텍스트 전처리 완료")

    return df


# ════════════════════════════════════════════════════════════════
# 진입점 1: main.py에서 raw 공고 리스트를 직접 전달
# ════════════════════════════════════════════════════════════════

def run_pipeline_from_jobs(jobs: List[Dict], threshold: int = FUZZY_THRESHOLD) -> None:
    """
    수집된 raw 공고 리스트를 받아 정제 후 DB에 저장.
    main.py에서 CSV 없이 직접 호출.
    """
    from utils import _jobs_to_dataframe
    from database import init_db, upsert_jobs

    df = _jobs_to_dataframe(jobs)
    df = _refine(df, source_label="main.py 직접 수집", threshold=threshold)

    init_db()
    inserted, updated = upsert_jobs(df)

    logger.info("=" * 60)
    logger.info("파이프라인 완료 — DB 신규 %d건 / 갱신 %d건", inserted, updated)
    logger.info("=" * 60)


# ════════════════════════════════════════════════════════════════
# 진입점 2: CSV 파일을 입력으로 받아 처리 (CLI 또는 레거시)
# ════════════════════════════════════════════════════════════════

def run_pipeline_from_csv(input_path: str, threshold: int = FUZZY_THRESHOLD) -> None:
    """CSV 파일을 읽어 정제 후 DB에 저장."""
    from database import init_db, upsert_jobs

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    logger.info("CSV 로드 완료: %d건 (%s)", len(df), input_path)

    df = _refine(df, source_label=os.path.basename(input_path), threshold=threshold)

    init_db()
    inserted, updated = upsert_jobs(df)

    logger.info("=" * 60)
    logger.info("파이프라인 완료 — DB 신규 %d건 / 갱신 %d건", inserted, updated)
    logger.info("=" * 60)


def get_latest_csv(directory: str = OUTPUT_DIR) -> Optional[str]:
    files = sorted(
        glob.glob(os.path.join(directory, "it_security_jobs_*.csv")),
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
        "--threshold", "-t",
        type=int,
        default=FUZZY_THRESHOLD,
        help=f"Fuzzy 유사도 임계값 %% (기본: {FUZZY_THRESHOLD})",
    )
    args = parser.parse_args()

    input_path = args.input or get_latest_csv()
    if not input_path:
        logger.error("입력 CSV 파일을 찾을 수 없습니다. --input 옵션으로 경로를 지정하세요.")
        raise SystemExit(1)

    run_pipeline_from_csv(input_path, threshold=args.threshold)
