"""
인크루트 스크래퍼 (HTML 크롤링)
  - IT/보안 직종 카테고리 크롤링
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class IncruitScraper(BaseScraper):
    site_name = "인크루트"

    # 인크루트 직종 코드: IT·인터넷(1), 보안(관련 키워드 검색)
    SEARCH_KEYWORDS = ["정보보안", "보안엔지니어", "백엔드개발", "프론트엔드개발", "DevOps", "클라우드"]

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        base_url = "https://job.incruit.com/jobdb_list/searchjob.asp"

        for keyword in self.SEARCH_KEYWORDS:
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "sf": "1",
                    "w1": keyword,
                    "col": "jt",
                    "page": page,
                }
                resp = self.get(base_url, params=params)
                if resp is None:
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select("div.c_row")
                if not items:
                    items = soup.select("li.cell_list")
                if not items:
                    logger.info("[인크루트] '%s' 페이지 %d: 공고 없음", keyword, page)
                    break

                for item in items:
                    title_tag   = item.select_one("a.job_tit") or item.select_one("a.tit")
                    company_tag = item.select_one("a.company") or item.select_one("span.company")
                    loc_tag     = item.select_one("span.loc")
                    exp_tag     = item.select_one("span.exp")
                    deadline_tag = item.select_one("span.date") or item.select_one("em.date")

                    title   = title_tag.get_text(strip=True) if title_tag else ""
                    company = company_tag.get_text(strip=True) if company_tag else ""
                    loc     = loc_tag.get_text(strip=True) if loc_tag else ""
                    exp     = exp_tag.get_text(strip=True) if exp_tag else ""
                    deadline = deadline_tag.get_text(strip=True) if deadline_tag else ""

                    href = ""
                    if title_tag and title_tag.has_attr("href"):
                        href = title_tag["href"]
                    url = (
                        f"https://job.incruit.com{href}"
                        if href.startswith("/")
                        else href
                    )

                    if title:
                        jobs.append(
                            self._make_job(
                                title=title,
                                company=company,
                                location=loc,
                                experience=exp,
                                deadline=deadline,
                                url=url,
                                keyword=keyword,
                            )
                        )

                logger.info(
                    "[인크루트] '%s' 페이지 %d → %d건 누적", keyword, page, len(jobs)
                )
        return jobs
