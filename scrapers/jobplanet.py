"""
잡플래닛 스크래퍼 (Selenium)
  - Next.js SPA → Selenium으로 렌더링 후 파싱
  - 공고 링크: a[href*='posting_ids'] 패턴
  - 링크 텍스트 구조: 회사명 | 공고제목 | 경력조건
  - https://www.jobplanet.co.kr/job/search
"""

import re
import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.selenium_base import SeleniumBaseScraper

logger = logging.getLogger(__name__)

_EXP_RE = re.compile(r"\d+년|신입|경력무관|무관")
_LOC_RE = re.compile(r"서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주")

SEARCH_KEYWORDS = [
    "백엔드", "프론트엔드", "DevOps", "보안",
    "데이터엔지니어", "클라우드", "AI엔지니어",
]


class JobplanetScraper(SeleniumBaseScraper):
    site_name = "잡플래닛"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        driver = self._get_driver()

        try:
            for keyword in SEARCH_KEYWORDS:
                for page in range(1, MAX_PAGES + 1):
                    url = f"https://www.jobplanet.co.kr/job/search?q={keyword}&page={page}"
                    ok = self._wait_and_get(
                        driver, url,
                        "a[href*='posting_ids']",
                        timeout=20,
                    )
                    if not ok:
                        logger.info("[잡플래닛] '%s' 페이지 %d: 로드 실패", keyword, page)
                        break

                    soup = BeautifulSoup(driver.page_source, "lxml")
                    job_links = soup.select("a[href*='posting_ids']")
                    if not job_links:
                        logger.info("[잡플래닛] '%s' 페이지 %d: 공고 없음", keyword, page)
                        break

                    for link in job_links:
                        href    = link.get("href", "")
                        url_job = href if href.startswith("http") else f"https://www.jobplanet.co.kr{href}"

                        # 링크 텍스트 파싱: 회사명 | 공고제목 | 경력
                        parts = [p.strip() for p in link.get_text(separator="|").split("|") if p.strip()]
                        if not parts:
                            continue

                        # [0] = 회사명, [1] = 제목, [2] = 경력 (순서 고정)
                        company = parts[0] if len(parts) > 0 else ""
                        title   = parts[1] if len(parts) > 1 else parts[0]
                        exp     = ""
                        loc     = ""

                        # 경력/근무지는 나머지 파트에서 패턴 매칭
                        for p in parts[2:]:
                            if not exp and _EXP_RE.search(p) and len(p) < 20:
                                exp = p
                            if not loc and _LOC_RE.search(p) and len(p) < 20:
                                loc = p

                        # 파트가 1개뿐이면 제목으로 처리
                        if len(parts) == 1:
                            title   = parts[0]
                            company = ""

                        if title:
                            jobs.append(self._make_job(
                                title=title, company=company, location=loc,
                                experience=exp, deadline="상시채용",
                                url=url_job, keyword=keyword,
                            ))

                    logger.info("[잡플래닛] '%s' 페이지 %d → %d건 누적", keyword, page, len(jobs))
        finally:
            driver.quit()

        return jobs
