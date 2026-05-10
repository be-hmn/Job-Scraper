"""
잡플래닛 스크래퍼
  - 잡플래닛 채용공고 API 사용
  - IT/보안 직군 필터링
"""

import logging
from typing import List, Dict

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_URL = "https://www.jobplanet.co.kr/api/v1/job_postings"

# 잡플래닛 직군 코드 (IT/보안)
JOB_TYPES = {
    "developer": "개발자",
    "security": "보안",
    "devops": "DevOps·인프라",
    "data": "데이터",
}


class JobplanetScraper(BaseScraper):
    site_name = "잡플래닛"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        for job_type, label in JOB_TYPES.items():
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "job_type": job_type,
                    "page": page,
                    "per_page": 20,
                    "order_by": "latest",
                }
                headers_extra = {
                    "Referer": "https://www.jobplanet.co.kr/job",
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                }
                resp = self.get(API_URL, params=params, headers=headers_extra)
                if resp is None:
                    break

                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("[잡플래닛] JSON 파싱 실패")
                    break

                items = data.get("job_postings", [])
                if not items:
                    break

                for item in items:
                    post_id  = item.get("id", "")
                    title    = item.get("title", "")
                    company  = item.get("company", {}).get("name", "")
                    loc      = item.get("location", "")
                    exp      = item.get("experience", "")
                    deadline = item.get("deadline", "") or "상시채용"
                    url      = f"https://www.jobplanet.co.kr/job/search?posting_ids={post_id}" if post_id else ""

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
                    "[잡플래닛] %s 페이지 %d → %d건 누적", label, page, len(jobs)
                )

                total = data.get("total_count", 0)
                if page * 20 >= total:
                    break

        return jobs
