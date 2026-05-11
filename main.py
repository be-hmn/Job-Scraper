"""
IT/보안 채용 공고 통합 스크래퍼
실행: python main.py [--sites 사람인 원티드 ...] [--no-dedup] [--output 파일명.csv]
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from scrapers.saramin     import SaraminScraper
from scrapers.jobkorea   import JobKoreaScraper
from scrapers.wanted     import WantedScraper
from scrapers.jumpit     import JumpitScraper
from scrapers.linkedin   import LinkedInScraper
from scrapers.jobplanet  import JobplanetScraper
from scrapers.kakao      import KakaoScraper
from scrapers.naver      import NaverScraper
from scrapers.toss       import TossScraper
from scrapers.coupang    import CoupangScraper
from scrapers.rallit     import RallitScraper
from utils import setup_logging, deduplicate, save_csv, print_summary

logger = logging.getLogger(__name__)

# 사용 가능한 스크래퍼 목록
ALL_SCRAPERS = {
    # ── 종합 채용 플랫폼 ──────────────────────────────────────
    "사람인":   SaraminScraper,
    "잡코리아": JobKoreaScraper,
    "원티드":   WantedScraper,
    "점핏":     JumpitScraper,
    "잡플래닛": JobplanetScraper,
    # ── 개발자 특화 플랫폼 ────────────────────────────────────
    "링크드인": LinkedInScraper,
    "랠릿":     RallitScraper,
    # ── 대기업 직접 채용 ──────────────────────────────────────
    "카카오":   KakaoScraper,
    "네이버":   NaverScraper,
    "토스":     TossScraper,
    "쿠팡":     CoupangScraper,
}


def run_scraper(name: str, scraper_cls) -> List[Dict]:
    """단일 스크래퍼 실행 (스레드 내부에서 호출)"""
    try:
        logger.info("▶ [%s] 수집 시작", name)
        jobs = scraper_cls().scrape()
        logger.info("✔ [%s] %d건 수집 완료", name, len(jobs))
        return jobs
    except Exception as e:
        logger.error("✘ [%s] 오류 발생: %s", name, e, exc_info=True)
        return []


def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="IT/보안 채용 공고 통합 스크래퍼"
    )
    parser.add_argument(
        "--sites",
        nargs="+",
        choices=list(ALL_SCRAPERS.keys()),
        default=list(ALL_SCRAPERS.keys()),
        help="수집할 사이트 목록 (기본: 전체)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="중복 제거 비활성화",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="저장할 CSV 파일명 (기본: 타임스탬프 자동 생성)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="동시 실행 스크래퍼 수 (기본: 3, 너무 높으면 차단 위험)",
    )
    args = parser.parse_args()

    selected = {k: v for k, v in ALL_SCRAPERS.items() if k in args.sites}
    logger.info("수집 대상 사이트: %s", ", ".join(selected.keys()))

    all_jobs: List[Dict] = []

    # 병렬 실행
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_scraper, name, cls): name
            for name, cls in selected.items()
        }
        for future in as_completed(futures):
            site_name = futures[future]
            jobs = future.result()
            all_jobs.extend(jobs)

    logger.info("전체 수집 완료: %d건 (중복 포함)", len(all_jobs))

    if not args.no_dedup:
        before = len(all_jobs)
        all_jobs = deduplicate(all_jobs)
        logger.info("중복 제거: %d건 → %d건", before, len(all_jobs))

    if not all_jobs:
        logger.warning("수집된 공고가 없습니다. 네트워크 상태나 사이트 구조 변경을 확인하세요.")
        sys.exit(0)

    csv_path = save_csv(all_jobs, args.output)
    logger.info("CSV 저장 완료: %s", csv_path)

    print_summary(all_jobs)
    print(f"  저장 위치: {csv_path}\n")


if __name__ == "__main__":
    main()
