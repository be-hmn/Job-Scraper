"""
잡코리아 스크래퍼 (HTML 크롤링)
IT개발·데이터 / 보안·네트워크 카테고리
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class JobKoreaScraper(BaseScraper):
    site_name = "잡코리아"

    # 잡코리아 직무 코드: 10031=IT개발, 10032=보안·네트워크
    DUTY_CODES = {
        "10031": "IT개발",
        "10032": "보안·네트워크",
    }

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        base_url = "https://www.jobkorea.co.kr/Search/"

        for code, label in self.DUTY_CODES.items():
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "stext": "",
                    "tabType": "recruit",
                    "duty": code,
                    "Page_No": page,
                }
                resp = self.get(base_url, params=params)
                if resp is None:
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select("li.list-post")
                if not items:
                    # 대안 셀렉터 시도
                    items = soup.select("div.recruit-info")
                if not items:
                    logger.info("[잡코리아] %s 페이지 %d: 공고 없음, 종료", label, page)
                    break

                for item in items:
                    title_tag   = item.select_one("a.title")
                    company_tag = item.select_one("a.name")
                    loc_tag     = item.select_one("p.option span.loc")
                    exp_tag     = item.select_one("p.option span.exp")
                    deadline_tag = item.select_one("span.date")

                    title   = title_tag.get_text(strip=True) if title_tag else ""
                    company = company_tag.get_text(strip=True) if company_tag else ""
                    loc     = loc_tag.get_text(strip=True) if loc_tag else ""
                    exp     = exp_tag.get_text(strip=True) if exp_tag else ""
                    deadline = deadline_tag.get_text(strip=True) if deadline_tag else ""

                    href = ""
                    if title_tag and title_tag.has_attr("href"):
                        href = title_tag["href"]
                    url = (
                        f"https://www.jobkorea.co.kr{href}"
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
                                keyword=label,
                            )
                        )

                logger.info(
                    "[잡코리아] %s 페이지 %d → %d건 누적", label, page, len(jobs)
                )
        return jobs
