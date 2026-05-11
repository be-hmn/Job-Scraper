"""
카카오 채용 스크래퍼 (Selenium)
  - SPA, API 401 → Selenium으로 렌더링 후 파싱
  - 공고 카드: div.area_info > div.wrap_info > h4.tit_jobs
  - https://careers.kakao.com/jobs
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.selenium_base import SeleniumBaseScraper

logger = logging.getLogger(__name__)

JOB_PARTS = {
    "TECHNOLOGY": "개발·기술",
    "SECURITY":   "보안",
    "DATA":       "데이터",
    "INFRA":      "인프라·DevOps",
}


class KakaoScraper(SeleniumBaseScraper):
    site_name = "카카오"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        driver = self._get_driver()

        try:
            for part, label in JOB_PARTS.items():
                for page in range(1, MAX_PAGES + 1):
                    url = f"https://careers.kakao.com/jobs?part={part}&page={page}"
                    # div.area_info 가 렌더링될 때까지 대기
                    ok = self._wait_and_get(driver, url, "div.area_info, div.wrap_info", timeout=20)
                    if not ok:
                        logger.info("[카카오] %s 페이지 %d: 로드 실패", label, page)
                        break

                    soup = BeautifulSoup(driver.page_source, "lxml")
                    items = soup.select("div.area_info")

                    if not items:
                        logger.info("[카카오] %s 페이지 %d: 공고 없음", label, page)
                        break

                    for item in items:
                        title_tag = item.select_one("h4.tit_jobs, h3.tit_jobs")
                        title = title_tag.get_text(strip=True) if title_tag else ""
                        if not title:
                            continue

                        # 회사명: dl.item_subinfo 첫 번째 dd
                        subinfo_dds = item.select("dl.item_subinfo dd")
                        company = subinfo_dds[0].get_text(strip=True) if subinfo_dds else "카카오"

                        # 마감일: dl.list_info 첫 번째 dd
                        list_info_dds = item.select("dl.list_info dd")
                        deadline = list_info_dds[0].get_text(strip=True) if list_info_dds else "상시채용"

                        # 근무지: dl.list_info 두 번째 dd
                        location = list_info_dds[1].get_text(strip=True) if len(list_info_dds) > 1 else "판교"

                        # 공고 URL: 부모 li 또는 a 태그에서 추출
                        parent = item.find_parent("li")
                        link = parent.select_one("a[href*='/jobs/']") if parent else None
                        if not link:
                            link = item.find_parent("a")
                        href = link["href"] if link and link.has_attr("href") else ""
                        url_job = (
                            f"https://careers.kakao.com{href}"
                            if href.startswith("/") else href
                        ) or url

                        jobs.append(self._make_job(
                            title=title, company=company, location=location,
                            experience="", deadline=deadline,
                            url=url_job, keyword=label,
                        ))

                    logger.info("[카카오] %s 페이지 %d → %d건 누적", label, page, len(jobs))

                    # 마지막 페이지 감지
                    if len(items) < 10:
                        break
        finally:
            driver.quit()

        return jobs
