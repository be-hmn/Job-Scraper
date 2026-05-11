"""
쿠팡 채용 스크래퍼
  - https://www.coupang.jobs (Greenhouse ATS 기반 내부 API)
  - IT/개발/보안 직군 수집
"""

import logging
from typing import List, Dict

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Greenhouse 기반 공개 API
API_URL = "https://boards-api.greenhouse.io/v1/boards/coupang/jobs"

IT_KEYWORDS = {
    "engineer", "developer", "devops", "security", "data", "backend",
    "frontend", "infrastructure", "sre", "cloud", "ai", "ml",
    "개발", "보안", "데이터", "인프라", "엔지니어",
}


class CoupangScraper(BaseScraper):
    site_name = "쿠팡"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        headers_extra = {
            "Referer": "https://www.coupang.jobs/",
            "Accept": "application/json",
        }
        resp = self.get(API_URL, headers=headers_extra)
        if resp is None:
            return jobs

        try:
            data = resp.json()
        except ValueError:
            logger.warning("[쿠팡] JSON 파싱 실패")
            return jobs

        items = data.get("jobs", [])

        for item in items:
            title    = item.get("title", "")
            dept     = item.get("departments", [{}])
            dept_name = dept[0].get("name", "") if dept else ""
            loc_list = item.get("offices", [{}])
            loc      = loc_list[0].get("name", "") if loc_list else ""

            # IT/개발/보안 직군만 필터링
            combined = (title + " " + dept_name).lower()
            if not any(kw in combined for kw in IT_KEYWORDS):
                continue

            job_id   = item.get("id", "")
            url      = item.get("absolute_url", f"https://www.coupang.jobs/jobs/{job_id}")
            deadline = "상시채용"
            exp      = ""

            if title:
                jobs.append(
                    self._make_job(
                        title=title,
                        company="쿠팡",
                        location=loc,
                        experience=exp,
                        deadline=deadline,
                        url=url,
                        keyword=dept_name or "개발·기술",
                    )
                )

        logger.info("[쿠팡] 총 %d건 수집", len(jobs))
        return jobs
