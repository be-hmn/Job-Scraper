"""
링크드인 코리아 스크래퍼
  - LinkedIn Jobs API (비공개 내부 API)
  - IT/보안 관련 키워드로 한국 채용 공고 수집
"""

import logging
from typing import List, Dict

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# LinkedIn 비공개 Jobs API
API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

SEARCH_QUERIES = {
    "정보보안 엔지니어": "information security engineer",
    "백엔드 개발자":     "backend developer",
    "DevOps 엔지니어":  "devops engineer",
    "클라우드 엔지니어": "cloud engineer",
    "보안관제":          "security operations",
    "AI 엔지니어":       "AI engineer",
}


class ProgrammersScraper(BaseScraper):
    """링크드인 코리아 채용 스크래퍼 (클래스명 유지로 main.py 호환)"""

    site_name = "링크드인"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        for label, query in SEARCH_QUERIES.items():
            for page in range(MAX_PAGES):
                params = {
                    "keywords": query,
                    "location": "South Korea",
                    "start": page * 25,
                    "count": 25,
                    "f_TPR": "r604800",   # 최근 1주일
                }
                headers_extra = {
                    "Referer": "https://www.linkedin.com/jobs/search/",
                    "Accept": "application/json, text/html",
                    "X-Requested-With": "XMLHttpRequest",
                }
                resp = self.get(API_URL, params=params, headers=headers_extra)
                if resp is None:
                    break

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select("li")

                fetched = 0
                for item in items:
                    title_tag   = item.select_one("h3.base-search-card__title")
                    company_tag = item.select_one("h4.base-search-card__subtitle a")
                    loc_tag     = item.select_one("span.job-search-card__location")
                    deadline_tag = item.select_one("time")
                    link_tag    = item.select_one("a.base-card__full-link")

                    title   = title_tag.get_text(strip=True) if title_tag else ""
                    company = company_tag.get_text(strip=True) if company_tag else ""
                    loc     = loc_tag.get_text(strip=True) if loc_tag else ""
                    deadline = deadline_tag.get("datetime", "") if deadline_tag else ""
                    url     = link_tag["href"].split("?")[0] if link_tag and link_tag.has_attr("href") else ""

                    if title:
                        jobs.append(
                            self._make_job(
                                title=title,
                                company=company,
                                location=loc,
                                experience="",
                                deadline=deadline,
                                url=url,
                                keyword=label,
                            )
                        )
                        fetched += 1

                logger.info(
                    "[링크드인] '%s' 페이지 %d → %d건 누적", label, page + 1, len(jobs)
                )

                if fetched < 25:
                    break

        return jobs
