"""
점핏(Jumpit) 스크래퍼
점핏은 내부 REST API를 사용합니다.
  - https://api.jumpit.co.kr/api/positions
  - tagIds: 보안(34), 백엔드(1), 프론트엔드(2), 풀스택(3), DevOps(4), 클라우드(5)
  - jobType=INTERN: 인턴십 공고 별도 수집
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

    def _fetch_positions(self, params: dict) -> List[Dict]:
        """공통 포지션 수집 로직"""
        jobs: List[Dict] = []
        label = params.get("_label", "")

        for page in range(1, MAX_PAGES + 1):
            req_params = {k: v for k, v in params.items() if not k.startswith("_")}
            req_params["page"] = page

            resp = self.get(API_URL, params=req_params, headers={
                "Referer": "https://jumpit.saramin.co.kr/",
                "Accept":  "application/json",
            })
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
                pos_id  = item.get("id", "")
                title   = item.get("title", "")
                company = item.get("companyName", "")
                loc     = ", ".join(item.get("locations", []))
                exp_min = item.get("minCareer", 0)
                exp_max = item.get("maxCareer", None)
                if exp_max:
                    exp = f"{exp_min}~{exp_max}년"
                elif exp_min == 0:
                    exp = "신입"
                else:
                    exp = f"{exp_min}년 이상"
                deadline = item.get("closeDate", "") or "상시채용"
                url      = f"https://jumpit.saramin.co.kr/position/{pos_id}" if pos_id else ""

                if title:
                    jobs.append(self._make_job(
                        title=title, company=company, location=loc,
                        experience=exp, deadline=deadline,
                        url=url, keyword=label,
                    ))

            logger.info("[점핏] %s 페이지 %d → %d건 누적", label, page, len(jobs))

            total = data.get("result", {}).get("totalCount", 0)
            if page * 20 >= total:
                break

        return jobs

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        # ── 일반 공고 (직군별) ────────────────────────────────────
        for tag_id, label in TAG_IDS.items():
            jobs.extend(self._fetch_positions({
                "tagIds": tag_id,
                "sort":   "rsp_rate",
                "_label": label,
            }))

        # ── 인턴십 공고 (전 직군) ─────────────────────────────────
        jobs.extend(self._fetch_positions({
            "jobType": "INTERN",
            "sort":    "rsp_rate",
            "_label":  "인턴십",
        }))

        return jobs
