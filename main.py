"""
IT/보안 채용 공고 통합 스크래퍼
실행: python main.py [--sites 사람인 원티드 ...]
      python main.py --schedule  # 매일 새벽 2시에 자동 수집
      python main.py --csv       # DB 대신 CSV로 저장 (디버깅용)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

# __file__ 기반 루트 경로 — GitHub Actions / Streamlit Cloud 등 CWD가 다른 환경 대응
_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_ROOT)  # 항상 프로젝트 루트를 CWD로 고정

from scrapers.saramin           import SaraminScraper
from scrapers.wanted            import WantedScraper
from scrapers.jumpit            import JumpitScraper
from scrapers.linkedin          import LinkedInScraper
from scrapers.naver             import NaverScraper
from scrapers.coupang           import CoupangScraper
from scrapers.selenium_scrapers import (
    JobKoreaScraper,
    JobplanetScraper,
    KakaoScraper,
    TossScraper,
    RallitScraper,
)
from utils import setup_logging, deduplicate, save_csv, print_summary

logger = logging.getLogger(__name__)

# ── GitHub Actions / CI 환경 감지 ────────────────────────────────
_IS_CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

if _IS_CI:
    # Ubuntu CI 환경: Selenium이 사용할 Chrome 옵션을 환경변수로 전달
    # selenium_base.py / SeleniumBase가 이 값을 읽어 headless 모드로 실행
    os.environ.setdefault("CHROME_OPTIONS", "--headless=new,--no-sandbox,--disable-dev-shm-usage,--disable-gpu")
    logger.info("CI 환경 감지: Chrome headless 옵션 적용")

ALL_SCRAPERS = {
    "사람인":   SaraminScraper,
    "잡코리아": JobKoreaScraper,
    "원티드":   WantedScraper,
    "점핏":     JumpitScraper,
    "잡플래닛": JobplanetScraper,
    "링크드인": LinkedInScraper,
    "랠릿":     RallitScraper,
    "카카오":   KakaoScraper,
    "네이버":   NaverScraper,
    "토스":     TossScraper,
    "쿠팡":     CoupangScraper,
}


def run_scraper(name: str, scraper_cls) -> List[Dict]:
    try:
        logger.info("▶ [%s] 수집 시작", name)
        jobs = scraper_cls().scrape()
        logger.info("✔ [%s] %d건 수집 완료", name, len(jobs))
        return jobs
    except Exception as e:
        logger.error("✘ [%s] 오류 발생: %s", name, e, exc_info=True)
        return []


def _collect(args) -> List[Dict]:
    """스크래퍼 실행 → 1차 중복 제거 → raw 공고 리스트 반환"""
    selected = {k: v for k, v in ALL_SCRAPERS.items() if k in args.sites}
    logger.info("수집 대상 사이트: %s", ", ".join(selected.keys()))

    all_jobs: List[Dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_scraper, name, cls): name
            for name, cls in selected.items()
        }
        for future in as_completed(futures):
            all_jobs.extend(future.result())

    logger.info("전체 수집 완료: %d건 (중복 포함)", len(all_jobs))

    if not args.no_dedup:
        before = len(all_jobs)
        all_jobs = deduplicate(all_jobs)
        logger.info("1차 중복 제거: %d건 → %d건", before, len(all_jobs))

    if not all_jobs:
        logger.warning("수집된 공고가 없습니다.")

    return all_jobs


def _run_once(args) -> None:
    all_jobs = _collect(args)
    if not all_jobs:
        return

    print_summary(all_jobs)

    if args.csv:
        # CSV 저장 모드 (디버깅/백업용)
        csv_path = save_csv(all_jobs, args.output)
        logger.info("CSV 저장 완료: %s", csv_path)
        print(f"  저장 위치: {csv_path}\n")
    else:
        # DB 저장 모드 (기본) — raw 데이터를 DB에 바로 저장 후 파이프라인 실행
        import pandas as pd
        from pipeline import run_pipeline_from_jobs
        logger.info("파이프라인 시작: %d건 처리 예정", len(all_jobs))
        run_pipeline_from_jobs(all_jobs)
        logger.info("파이프라인 완료 — DB: %s", os.path.join(_ROOT, "output", "job_database.db"))


def _run_scheduled(args) -> None:
    setup_logging()
    logger.info("스케줄 모드 시작 — 매일 %02d:00에 수집합니다. (Ctrl+C로 종료)", args.hour)

    while True:
        now      = datetime.now()
        next_run = now.replace(hour=args.hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        wait_sec = (next_run - now).total_seconds()
        logger.info("다음 수집 예정: %s (%.0f초 후)", next_run.strftime("%Y-%m-%d %H:%M"), wait_sec)

        try:
            time.sleep(wait_sec)
        except KeyboardInterrupt:
            logger.info("스케줄 모드 종료")
            sys.exit(0)

        logger.info("=== 스케줄 수집 시작: %s ===", datetime.now().strftime("%Y-%m-%d %H:%M"))
        try:
            _run_once(args)
        except Exception as e:
            logger.error("스케줄 수집 중 오류: %s", e, exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="IT/보안 채용 공고 통합 스크래퍼")
    parser.add_argument(
        "--sites", nargs="+",
        choices=list(ALL_SCRAPERS.keys()),
        default=list(ALL_SCRAPERS.keys()),
        help="수집할 사이트 목록 (기본: 전체)",
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="1차 중복 제거 비활성화",
    )
    parser.add_argument(
        "--workers", type=int, default=3,
        help="동시 실행 스크래퍼 수 (기본: 3)",
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="스케줄 모드: 매일 새벽 2시에 자동 수집",
    )
    parser.add_argument(
        "--hour", type=int, default=2,
        help="스케줄 모드 실행 시각 (0~23, 기본: 2시)",
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="DB 대신 CSV로 저장 (디버깅/백업용, --output 옵션과 함께 사용)",
    )
    parser.add_argument(
        "--output", default=None,
        help="CSV 저장 시 파일명 (--csv 옵션 사용 시, 기본: 타임스탬프 자동 생성)",
    )
    args = parser.parse_args()

    if args.schedule:
        _run_scheduled(args)
    else:
        setup_logging()
        _run_once(args)


if __name__ == "__main__":
    main()
