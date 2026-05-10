"""
점핏(Jumpit) 스크래퍼
점핏은 내부 REST API를 사용합니다.
  - https://jumpit.saramin.co.kr/api/positions
  - tagIds: 보안(34), 백엔드(1), 프론트엔드(2), 풀스택(3), DevOps(4), 클라우드(5)
"""

import logging
from typing import List, Dict

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_URL = "https://api.jumpit.co.kr/api/positions"

# 점핏 태그 ID (IT/보안 관련)
TAG_IDS = {
    1:  "백엔드",
    2:  "프론트엔드",
    3:  "풀스택",
    4:  "DevOps·인프라",
    5:  "클라우드",
    34: "보안",
    6:  "데이터엔지니어",
    7:  "AI·ML",
}


class JumpitScraper(BaseScraper):
    site_name = "점핏"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        for tag_id, label in TAG_IDS.items():
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "tagIds": tag_id,
                    "page": page,
                    "sort": "rsp_rate",
                }
                headers_extra = {
                    "Referer": "https://jumpit.saramin.co.kr/",
                    "Accept": "application/json",
                }
                resp = self.get(API_URL, params=params, headers=headers_extra)
                if resp is None:
                    break

                try:
                    data = resp.json()
                except ValueError:
                    logger.warning("[점핏] JSON 파싱 실패")
                    break

                items = data.get("result", {}).get("positions", [])
                if not items:
                    break

                for item in items:
                    pos_id   = item.get("id", "")
                    title    = item.get("title", "")
                    company  = item.get("companyName", "")
                    loc      = ", ".join(item.get("locations", []))
                    exp_min  = item.get("minCareer", 0)
                    exp_max  = item.get("maxCareer", None)
                    if exp_max:
                        exp = f"{exp_min}~{exp_max}년"
                    elif exp_min == 0:
                        exp = "신입"
                    else:
                        exp = f"{exp_min}년 이상"
                    deadline = item.get("closeDate", "") or "상시채용"
                    url      = f"https://jumpit.saramin.co.kr/position/{pos_id}" if pos_id else ""

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
                    "[점핏] %s 페이지 %d → %d건 누적", label, page, len(jobs)
                )

                total = data.get("result", {}).get("totalCount", 0)
                if page * 20 >= total:
                    break

        return jobs
