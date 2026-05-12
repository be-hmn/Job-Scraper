"""
사람인 스크래퍼
  1) Open API  (API 키가 있을 때 우선 사용)
  2) HTML 크롤링 (API 키 없을 때 폴백)
     - 셀렉터: div.list_item (2025년 이후 구조)
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import (
    SARAMIN_API_KEY,
    SARAMIN_API_URL,
    IT_SECURITY_KEYWORDS,
    MAX_PAGES,
    is_it_job,
)
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SaraminScraper(BaseScraper):
    site_name = "사람인"

    # IT개발(84), 보안·경호(86), 인턴(87 = 인턴·파견·아르바이트 중 IT 인턴)
    # 사람인 고용형태 파라미터: employment_tp_cd=5 (인턴)
    CATEGORY_CODES = ["84", "86"]
    INTERN_CATEGORY = "84"  # IT개발 카테고리에서 인턴 고용형태 필터

    def scrape(self) -> List[Dict]:
        if SARAMIN_API_KEY:
            logger.info("[사람인] Open API 모드로 수집합니다.")
            return self._scrape_api()
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
                    "job_mid_cd": "2",
                    "count": 40,
                    "start": (page - 1) * 40,
                    "fields": "posting-date,expiration-date,keyword,salary,experience-level,required-education-level",
                    "sort": "pd",
                }
                resp = self.get(SARAMIN_API_URL, params=params)
                if resp is None:
                    break
                data = resp.json()
                items = data.get("jobs", {}).get("job", [])
                if not items:
                    break
                for item in items:
                    position = item.get("position", {})
                    company  = item.get("company", {}).get("detail", {})
                    jobs.append(self._make_job(
                        title=position.get("title", ""),
                        company=company.get("name", ""),
                        location=position.get("location", {}).get("name", ""),
                        experience=position.get("experience-level", {}).get("name", ""),
                        deadline=item.get("expiration-date", ""),
                        url=item.get("url", ""),
                        keyword=keyword,
                    ))
            logger.info("[사람인 API] 키워드 '%s' 수집 완료 (%d건)", keyword, len(jobs))
        return jobs

    # ── HTML 크롤링 ─────────────────────────────────────────────
    def _scrape_html(self) -> List[Dict]:
        jobs: List[Dict] = []
        base_url = "https://www.saramin.co.kr/zf_user/jobs/list/job-category"

        # (카테고리 코드, 고용형태 코드, 레이블)
        # employment_tp_cd: 1=정규직, 2=계약직, 3=파견직, 4=프리랜서, 5=인턴, 6=아르바이트
        targets = [
            ("84", None, None),   # IT개발 전체
            ("86", None, None),   # 보안 전체
            ("84", "5",  "인턴"), # IT개발 인턴만
        ]

        for cat, emp_tp, emp_label in targets:
            for page in range(1, MAX_PAGES + 1):
                params = {
                    "cat_kewd": cat,
                    "page": page,
                    "panel_type": "",
                    "search_optional_item": "n",
                    "search_done": "y",
                    "panel_count": "y",
                }
                if emp_tp:
                    params["employment_tp_cd"] = emp_tp

                resp = self.get(base_url, params=params)
                if resp is None:
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select("div.list_item")
                if not items:
                    break

                for item in items:
                    title_tag    = item.select_one("div.job_tit a.str_tit")
                    company_tag  = item.select_one("div.company_nm a.str_tit")
                    loc_tag      = item.select_one("p.work_place")
                    exp_tag      = item.select_one("p.career")
                    sector_tags  = item.select("div.job_meta span.job_sector span")
                    deadline_tag = item.select_one("span.date")

                    title    = title_tag.get_text(strip=True) if title_tag else ""
                    company  = company_tag.get_text(strip=True) if company_tag else ""
                    loc      = loc_tag.get_text(strip=True) if loc_tag else ""
                    exp      = exp_tag.get_text(strip=True) if exp_tag else ""
                    kw_base  = ", ".join(t.get_text(strip=True) for t in sector_tags[:3]) if sector_tags else f"cat_{cat}"
                    keyword  = f"{kw_base} (인턴)" if emp_label else kw_base
                    deadline = deadline_tag.get_text(strip=True) if deadline_tag else ""

                    href = title_tag["href"] if title_tag and title_tag.has_attr("href") else ""
                    url  = f"https://www.saramin.co.kr{href}" if href.startswith("/") else href

                    if title:
                        if not is_it_job(title):
                            continue
                        jobs.append(self._make_job(
                            title=title, company=company, location=loc,
                            experience=exp, deadline=deadline,
                            url=url, keyword=keyword,
                        ))

                label_str = f"카테고리 {cat}" + (f" [{emp_label}]" if emp_label else "")
                logger.info("[사람인 HTML] %s, 페이지 %d → %d건 누적", label_str, page, len(jobs))
        return jobs
