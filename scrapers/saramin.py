"""
사람인 스크래퍼
  1) Open API  (API 키가 있을 때 우선 사용)
  2) HTML 크롤링 (API 키 없을 때 폴백)
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import (
    SARAMIN_API_KEY,
    SARAMIN_API_URL,
    IT_SECURITY_KEYWORDS,
    MAX_PAGES,
)
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SaraminScraper(BaseScraper):
    site_name = "사람인"

    # HTML 크롤링용 IT/보안 직종 코드
    # 사람인 직종 대분류: 84=IT개발·데이터, 86=보안·경호
    CATEGORY_CODES = ["84", "86"]

    def scrape(self) -> List[Dict]:
        if SARAMIN_API_KEY:
            logger.info("[사람인] Open API 모드로 수집합니다.")
            return self._scrape_api()
        else:
            logger.info("[사람인] HTML 크롤링 모드로 수집합니다. (API 키 없음)")
            return self._scrape_html()

    # ── Open API ────────────────────────────────────────────────
    def _scrape_api(self) -> List[Dict]:
        jobs: List[Dict] = []
        for keyword in IT_SECURITY_KEYWORDS:
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "access-key": SARAMIN_API_KEY,
                    "keywords": keyword,
                    "job_mid_cd": "2",   # IT·인터넷·통신
                    "count": 40,
                    "start": (page - 1) * 40,
                    "fields": "posting-date,expiration-date,keyword,salary,experience-level,required-education-level",
                    "sort": "pd",        # 최신순
                }
                resp = self.get(SARAMIN_API_URL, params=params)
                if resp is None:
                    break

                data = resp.json()
                items = (
                    data.get("jobs", {}).get("job", [])
                )
                if not items:
                    break

                for item in items:
                    position = item.get("position", {})
                    company  = item.get("company", {}).get("detail", {})
                    jobs.append(
                        self._make_job(
                            title=position.get("title", ""),
                            company=company.get("name", ""),
                            location=position.get("location", {}).get("name", ""),
                            experience=position.get("experience-level", {}).get("name", ""),
                            deadline=item.get("expiration-date", ""),
                            url=item.get("url", ""),
                            keyword=keyword,
                        )
                    )
            logger.info("[사람인 API] 키워드 '%s' 수집 완료 (%d건)", keyword, len(jobs))
        return jobs

    # ── HTML 크롤링 ─────────────────────────────────────────────
    def _scrape_html(self) -> List[Dict]:
        jobs: List[Dict] = []
        base_url = "https://www.saramin.co.kr/zf_user/jobs/list/job-category"

        for cat in self.CATEGORY_CODES:
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "cat_kewd": cat,
                    "page": page,
                    "panel_type": "",
                    "search_optional_item": "n",
                    "search_done": "y",
                    "panel_count": "y",
                }
                resp = self.get(base_url, params=params)
                if resp is None:
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select("div.item_recruit")
                if not items:
                    break

                for item in items:
                    title_tag = item.select_one("h2.job_tit a")
                    company_tag = item.select_one("strong.corp_name a")
                    loc_tag = item.select_one("p.job_condition span:nth-of-type(1)")
                    exp_tag = item.select_one("p.job_condition span:nth-of-type(2)")
                    deadline_tag = item.select_one("span.date")

                    title   = title_tag.get_text(strip=True) if title_tag else ""
                    company = company_tag.get_text(strip=True) if company_tag else ""
                    loc     = loc_tag.get_text(strip=True) if loc_tag else ""
                    exp     = exp_tag.get_text(strip=True) if exp_tag else ""
                    deadline = deadline_tag.get_text(strip=True) if deadline_tag else ""
                    href    = title_tag["href"] if title_tag and title_tag.has_attr("href") else ""
                    url     = f"https://www.saramin.co.kr{href}" if href.startswith("/") else href

                    if title:
                        jobs.append(
                            self._make_job(
                                title=title,
                                company=company,
                                location=loc,
                                experience=exp,
                                deadline=deadline,
                                url=url,
                                keyword=f"cat_{cat}",
                            )
                        )

                logger.info(
                    "[사람인 HTML] 카테고리 %s, 페이지 %d → %d건 누적",
                    cat, page, len(jobs),
                )
        return jobs
