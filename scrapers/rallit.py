"""
랠릿(Rallit) 스크래퍼 (Selenium)
  - Next.js SPA → Selenium으로 렌더링 후 파싱
  - 공고 카드: article 태그 (CSS-in-JS 클래스 무관)
  - 카드 구조: h2/h3(제목) + 첫 번째 짧은 span(회사명)
  - https://www.rallit.com/positions
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.selenium_base import SeleniumBaseScraper

logger = logging.getLogger(__name__)

POSITIONS = {
    "BACKEND":   "백엔드",
    "FRONTEND":  "프론트엔드",
    "DEVOPS":    "DevOps·인프라",
    "DATA":      "데이터",
    "SECURITY":  "보안",
    "MOBILE":    "모바일",
    "AI":        "AI·ML",
}


class RallitScraper(SeleniumBaseScraper):
    site_name = "랠릿"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        driver = self._get_driver()

        try:
            for pos_type, label in POSITIONS.items():
                page = 0
                while page < MAX_PAGES:
                    url = f"https://www.rallit.com/positions?jobType={pos_type}&page={page}"
                    ok = self._wait_and_get(driver, url, "article", timeout=20)
                    if not ok:
                        logger.info("[랠릿] %s 페이지 %d: 로드 실패", label, page)
                        break

                    soup = BeautifulSoup(driver.page_source, "lxml")
                    items = soup.select("article")
                    if not items:
                        logger.info("[랠릿] %s 페이지 %d: 공고 없음", label, page)
                        break

                    prev_count = len(jobs)
                    for item in items:
                        # 제목: h2/h3/h4 우선, 없으면 가장 긴 p
                        title_tag = item.select_one("h2, h3, h4")
                        if title_tag:
                            title = title_tag.get_text(strip=True)
                        else:
                            ps = item.select("p")
                            title = max(ps, key=lambda x: len(x.get_text()), default=None)
                            title = title.get_text(strip=True)[:80] if title else ""

                        if not title or len(title) < 3:
                            continue

                        # 회사명: 제목이 아닌 첫 번째 짧은 텍스트 블록
                        company = ""
                        for el in item.select("span, p"):
                            txt = el.get_text(strip=True)
                            if txt and txt != title and 1 < len(txt) < 40:
                                company = txt
                                break

                        # URL: /positions/{id} 링크
                        link = item.select_one("a[href*='/positions/']")
                        if not link:
                            link = item.find_parent("a")
                        href    = link["href"] if link and link.has_attr("href") else ""
                        url_job = f"https://www.rallit.com{href}" if href.startswith("/") else href

                        jobs.append(self._make_job(
                            title=title, company=company, location="",
                            experience="", deadline="상시채용",
                            url=url_job, keyword=label,
                        ))

                    added = len(jobs) - prev_count
                    logger.info("[랠릿] %s 페이지 %d → +%d건 (누적 %d건)", label, page, added, len(jobs))

                    # 더 이상 새 공고가 없으면 종료
                    if added == 0:
                        break
                    page += 1

        finally:
            driver.quit()

        return jobs
