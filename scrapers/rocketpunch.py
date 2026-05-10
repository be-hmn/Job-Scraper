"""
로켓펀치 스크래퍼
  - https://api.rocketpunch.com/v1/job/search
  - 스타트업 IT/보안 채용 특화
"""

import logging
from typing import List, Dict

from config import IT_SECURITY_KEYWORDS, MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_URL = "https://api.rocketpunch.com/v1/job/search"

# 로켓펀치 검색 키워드 (보안/IT 핵심만)
SEARCH_KEYWORDS = [
    "보안",
    "정보보안",
    "백엔드",
    "프론트엔드",
    "DevOps",
    "클라우드",
    "데이터엔지니어",
    "AI",
]


class RocketpunchScraper(BaseScraper):
    site_name = "로켓펀치"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        for keyword in SEARCH_KEYWORDS:
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "q": keyword,
                    "page": page,
                }
                headers_extra = {
                    "Referer": "https://www.rocketpunch.com/",
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                }
                resp = self.get(API_URL, params=params, headers=headers_extra)
                if resp is None:
                    break

                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("[로켓펀치] JSON 파싱 실패")
                    break

                items = data.get("data", {}).get("results", [])
                if not items:
                    break

                for item in items:
                    job_id   = item.get("id", "")
                    title    = item.get("title", "")
                    company  = item.get("company", {}).get("name", "")
                    loc      = item.get("location", "")
                    exp      = item.get("career_type", "")
                    deadline = item.get("close_date", "") or "상시채용"
                    url      = f"https://www.rocketpunch.com/jobs/{job_id}" if job_id else ""

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
                    "[로켓펀치] '%s' 페이지 %d → %d건 누적", keyword, page, len(jobs)
                )

                has_next = data.get("data", {}).get("has_next", False)
                if not has_next:
                    break

        return jobs
