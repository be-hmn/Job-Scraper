"""
공통 유틸리티: 중복 제거, CSV 저장, 로깅 설정
"""

import os
import logging
from datetime import datetime
from typing import List, Dict

import pandas as pd

from config import OUTPUT_DIR, CSV_FILENAME


def setup_logging(level: int = logging.INFO) -> None:
    """콘솔 + 파일 로깅 설정"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "scraper.log")

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def deduplicate(jobs: List[Dict]) -> List[Dict]:
    """
    중복 제거 전략 (우선순위 순):
      1) (title, company) 둘 다 있으면 해당 조합으로 중복 판단
      2) company가 비어있으면 url 기준으로 중복 판단
      3) url도 없으면 title만으로 판단 (느슨한 기준)

    같은 공고가 여러 사이트에 올라온 경우 첫 번째 항목만 유지.
    """
    seen_title_company: set = set()
    seen_url: set = set()
    unique: List[Dict] = []

    for job in jobs:
        title   = job.get("title", "").strip()
        company = job.get("company", "").strip()
        url     = job.get("url", "").strip()

        if not title:
            continue  # 제목 없는 항목은 무조건 제외

        if company:
            # 전략 1: (title, company) 조합
            key = (title, company)
            if key in seen_title_company:
                continue
            seen_title_company.add(key)
            if url:
                seen_url.add(url)
        elif url:
            # 전략 2: URL 기준 (company nan인 사이트 대응)
            if url in seen_url:
                continue
            seen_url.add(url)
            # title만으로도 seen에 추가해 다른 사이트 중복 방지
            seen_title_company.add((title, ""))
        else:
            # 전략 3: title만
            key = (title, "")
            if key in seen_title_company:
                continue
            seen_title_company.add(key)

        unique.append(job)

    return unique


def _jobs_to_dataframe(jobs: List[Dict]) -> pd.DataFrame:
    """
    스크래퍼가 반환한 raw 공고 리스트를 DataFrame으로 변환.
    컬럼명을 한글로 매핑한다.
    """
    df = pd.DataFrame(jobs, columns=[
        "title", "company", "location", "experience",
        "deadline", "url", "source", "keyword",
    ])
    df.rename(columns={
        "title":      "공고제목",
        "company":    "회사명",
        "location":   "근무지",
        "experience": "경력",
        "deadline":   "마감일",
        "url":        "공고URL",
        "source":     "출처",
        "keyword":    "검색키워드",
    }, inplace=True)
    return df


def save_csv(jobs: List[Dict], filename: str = None) -> str:
    """
    채용 공고 목록을 CSV로 저장하고 파일 경로를 반환한다.
    파일명에 타임스탬프를 붙여 덮어쓰기를 방지한다.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(CSV_FILENAME)
        filename = f"{base}_{ts}{ext}"

    path = os.path.join(OUTPUT_DIR, filename)

    df = pd.DataFrame(jobs, columns=[
        "title", "company", "location", "experience",
        "deadline", "url", "source", "keyword",
    ])

    df.rename(columns={
        "title":      "공고제목",
        "company":    "회사명",
        "location":   "근무지",
        "experience": "경력",
        "deadline":   "마감일",
        "url":        "공고URL",
        "source":     "출처",
        "keyword":    "검색키워드",
    }, inplace=True)

    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def print_summary(jobs: List[Dict]) -> None:
    """사이트별 수집 건수 요약 출력"""
    from collections import Counter
    counter = Counter(j["source"] for j in jobs)
    print("\n" + "=" * 50)
    print(f"  총 수집 공고: {len(jobs)}건")
    print("=" * 50)
    for site, cnt in sorted(counter.items(), key=lambda x: -x[1]):
        print(f"  {site:<15} {cnt:>5}건")
    print("=" * 50 + "\n")
