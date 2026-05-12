"""
동적 스크래퍼 테스트
각 스크래퍼를 실제로 실행해 응답 여부, 데이터 구조, 필드 유효성을 검증한다.

실행: python test_scrapers.py [--sites 사람인 원티드 ...]
"""

import sys
import time
import argparse
import traceback
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

sys.path.insert(0, ".")

from scrapers.saramin          import SaraminScraper
from scrapers.wanted           import WantedScraper
from scrapers.jumpit           import JumpitScraper
from scrapers.linkedin         import LinkedInScraper
from scrapers.naver            import NaverScraper
from scrapers.coupang          import CoupangScraper
from scrapers.selenium_scrapers import (
    JobKoreaScraper,
    JobplanetScraper,
    KakaoScraper,
    TossScraper,
    RallitScraper,
)
from scrapers.selenium_base import _find_chrome

logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

CHROME_AVAILABLE = bool(_find_chrome())

SELENIUM_SCRAPERS = {
    "잡코리아", "잡플래닛", "카카오", "토스", "랠릿"
}

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

REQUIRED_FIELDS = {"title", "company", "url", "source"}
ALL_FIELDS      = {"title", "company", "location", "experience", "deadline", "url", "source", "keyword"}


# ── 단일 스크래퍼 테스트 ─────────────────────────────────────────
def test_one(name: str, cls) -> Dict:
    result = {
        "name":    name,
        "status":  "FAIL",
        "count":   0,
        "elapsed": 0.0,
        "issues":  [],
        "sample":  None,
        "selenium": name in SELENIUM_SCRAPERS,
    }

    # Chrome 없으면 Selenium 스크래퍼 SKIP
    if name in SELENIUM_SCRAPERS and not CHROME_AVAILABLE:
        result["status"] = "SKIP"
        result["issues"].append("Chrome 미설치 (https://www.google.com/chrome/)")
        return result

    t0 = time.time()
    try:
        import config as cfg
        original_max = cfg.MAX_PAGES
        cfg.MAX_PAGES = 1

        jobs: List[Dict] = cls().scrape()

        cfg.MAX_PAGES = original_max
        result["elapsed"] = round(time.time() - t0, 1)
        result["count"]   = len(jobs)

        if not jobs:
            result["issues"].append("수집 결과 0건 (차단·구조변경 가능성)")
            result["status"] = "WARN"
            return result

        # ── 필드 유효성 검사 ──────────────────────────────────
        missing_required = set()
        empty_title_cnt  = 0
        empty_url_cnt    = 0
        wrong_source_cnt = 0
        extra_fields     = set()

        for job in jobs:
            for f in REQUIRED_FIELDS:
                if f not in job:
                    missing_required.add(f)
            if not job.get("title", "").strip():
                empty_title_cnt += 1
            if not job.get("url", "").strip():
                empty_url_cnt += 1
            if job.get("source", "") != cls.site_name:
                wrong_source_cnt += 1
            extra_fields |= set(job.keys()) - ALL_FIELDS

        if missing_required:
            result["issues"].append(f"필수 필드 누락: {missing_required}")
        if empty_title_cnt:
            result["issues"].append(f"빈 title {empty_title_cnt}건")
        if empty_url_cnt > len(jobs) * 0.3:
            result["issues"].append(f"URL 없는 항목 {empty_url_cnt}/{len(jobs)}건")
        if wrong_source_cnt:
            result["issues"].append(f"source 불일치 {wrong_source_cnt}건")
        if extra_fields:
            result["issues"].append(f"예상 외 필드: {extra_fields}")

        result["sample"] = jobs[0]
        result["status"] = "WARN" if result["issues"] else "PASS"

    except Exception as e:
        result["elapsed"] = round(time.time() - t0, 1)
        result["issues"].append(str(e)[:120])
        result["traceback"] = traceback.format_exc()
        result["status"] = "ERROR"

    return result


# ── 결과 출력 ────────────────────────────────────────────────────
def print_results(results: List[Dict]):
    PASS  = "\033[92mPASS \033[0m"
    WARN  = "\033[93mWARN \033[0m"
    ERROR = "\033[91mERROR\033[0m"
    FAIL  = "\033[91mFAIL \033[0m"
    SKIP  = "\033[90mSKIP \033[0m"

    color_map = {"PASS": PASS, "WARN": WARN, "ERROR": ERROR, "FAIL": FAIL, "SKIP": SKIP}

    print("\n" + "=" * 75)
    print(f"  {'사이트':<14} {'상태':<7} {'건수':>5}  {'시간':>6}  이슈")
    print("=" * 75)

    pass_cnt = warn_cnt = error_cnt = skip_cnt = 0
    for r in results:
        status_str = color_map.get(r["status"], r["status"])
        issues_str = " | ".join(r["issues"]) if r["issues"] else "-"
        selenium_mark = "[S]" if r.get("selenium") else "   "
        print(f"  {r['name']:<14} {status_str}  {r['count']:>5}건  {r['elapsed']:>5.1f}s  {selenium_mark} {issues_str}")
        if r["status"] == "PASS":   pass_cnt  += 1
        elif r["status"] == "WARN": warn_cnt  += 1
        elif r["status"] == "SKIP": skip_cnt  += 1
        else:                       error_cnt += 1

    print("=" * 75)
    print(f"  PASS {pass_cnt}  /  WARN {warn_cnt}  /  ERROR {error_cnt}  /  SKIP {skip_cnt}  (총 {len(results)}개)")
    if not CHROME_AVAILABLE:
        print(f"  ※ [S] 표시 사이트는 Chrome 필요. 설치 후 재실행: https://www.google.com/chrome/")
    print("=" * 75)

    # 샘플 데이터 출력
    for r in results:
        if r["status"] in ("PASS", "WARN") and r["sample"]:
            print(f"\n  ── 샘플 [{r['name']}] ──")
            for k, v in r["sample"].items():
                print(f"    {k:<12}: {str(v)[:80]}")
            break

    # ERROR 상세 트레이스백
    for r in results:
        if r.get("traceback"):
            print(f"\n  ── ERROR 트레이스백 [{r['name']}] ──")
            print(r["traceback"])


# ── 메인 ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="스크래퍼 동적 테스트")
    parser.add_argument("--sites", nargs="+", choices=list(ALL_SCRAPERS.keys()),
                        default=list(ALL_SCRAPERS.keys()))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    selected = {k: v for k, v in ALL_SCRAPERS.items() if k in args.sites}

    chrome_status = f"Chrome {'감지됨' if CHROME_AVAILABLE else '없음 → Selenium 사이트 SKIP'}"
    print(f"\n테스트 대상: {len(selected)}개 사이트  (workers={args.workers}, MAX_PAGES=1)")
    print(f"브라우저: {chrome_status}")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(test_one, name, cls): name for name, cls in selected.items()}
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            icon = {"PASS": "✔", "WARN": "△", "ERROR": "✘", "FAIL": "✘", "SKIP": "○"}.get(r["status"], "?")
            print(f"  {icon} {r['name']:<14} {r['status']}  {r['count']}건  {r['elapsed']}s")

    results.sort(key=lambda x: x["name"])
    print_results(results)


if __name__ == "__main__":
    main()
