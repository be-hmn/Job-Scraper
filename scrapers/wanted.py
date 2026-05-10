"""
원티드 스크래퍼
원티드는 SPA(React)이므로 내부 JSON API를 직접 호출합니다.
  - /api/v4/jobs  엔드포인트 사용
  - job_group_id: 518 = 개발, 655 = 보안
"""

import logging
from typing import List, Dict

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_URL = "https://www.wanted.co.kr/api/v4/jobs"

# 원티드 직군 ID
JOB_GROUPS = {
    518: "개발",
    655: "보안·네트워크",
}


class WantedScraper(BaseScraper):
    site_name = "원티드"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        for group_id, label in JOB_GROUPS.items():
            offset = 0
            limit  = 20

            for _ in range(MAX_PAGES):
                params = {
                    "country": "kr",
                    "job_sort": "job.latest_order",
                    "years": -1,
                    "locations": "all",
                    "job_group_id": group_id,
                    "offset": offset,
                    "limit": limit,
                }
                headers_extra = {
                    "Referer": "https://www.wanted.co.kr/",
                    "x-requested-with": "XMLHttpRequest",
                }
                resp = self.get(API_URL, params=params, headers=headers_extra)
                if resp is None:
                    break

                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("[원티드] JSON 파싱 실패")
                    break

                items = data.get("data", [])
                if not items:
                    break

                for item in items:
                    job_id  = item.get("id", "")
                    title   = item.get("position", "")
                    company = item.get("company", {}).get("name", "")
                    loc     = item.get("address", {}).get("location", "")
                    exp     = item.get("experience_level", {}).get("display", "")
                    deadline = item.get("due_time", "") or "상시채용"
                    url     = f"https://www.wanted.co.kr/wd/{job_id}" if job_id else ""

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

                offset += limit
                logger.info(
                    "[원티드] %s offset=%d → %d건 누적", label, offset, len(jobs)
                )

                # 마지막 페이지 감지
                if len(items) < limit:
                    break

        return jobs
