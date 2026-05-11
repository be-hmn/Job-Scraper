"""
토스 채용 스크래퍼 (Selenium)
  - SPA(Next.js) → Selenium으로 렌더링 후 파싱
  - 공고 카드: li.css-1lnizc9
  - 제목: p[data-desktop-list-item-title]
  - https://toss.im/career/jobs
"""

import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from scrapers.selenium_base import SeleniumBaseScraper

logger = logging.getLogger(__name__)

IT_LABELS = {
    "개발", "보안", "데이터", "인프라", "devops", "sre", "ai",
    "머신러닝", "백엔드", "프론트엔드", "풀스택", "ios", "android",
    "engineer", "developer", "security", "data", "infra", "software",
}


class TossScraper(SeleniumBaseScraper):
    site_name = "토스"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        driver = self._get_driver()

        try:
            url = "https://toss.im/career/jobs"
            # li.css-1lnizc9 가 렌더링될 때까지 대기
            ok = self._wait_and_get(driver, url, "li.css-1lnizc9", timeout=20)
            if not ok:
                logger.warning("[토스] 페이지 로드 실패")
                return jobs

            soup = BeautifulSoup(driver.page_source, "lxml")
            items = soup.select("li.css-1lnizc9")
            logger.info("[토스] 공고 카드 %d개 발견", len(items))

            for item in items:
                # 제목
                title_tag = item.select_one("p[data-desktop-list-item-title]")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title:
                    continue

                # IT/개발/보안 직군 필터링
                combined = title.lower()
                # 태그/직군 텍스트도 확인
                spans = item.select("span")
                tag_text = " ".join(s.get_text(strip=True) for s in spans).lower()
                combined += " " + tag_text

                if not any(kw in combined for kw in IT_LABELS):
                    continue

                # 회사명: 마지막 텍스트 블록 (보통 "토스", "토스뱅크" 등)
                all_texts = [t.strip() for t in item.get_text(separator="|").split("|") if t.strip()]
                company = all_texts[-1] if all_texts else "토스"

                # URL: 부모 a 태그 또는 data 속성
                link = item.find_parent("a") or item.select_one("a[href]")
                href = link["href"] if link and link.has_attr("href") else ""
                url_job = f"https://toss.im{href}" if href.startswith("/") else href or "https://toss.im/career/jobs"

                # 직군 키워드
                keyword = " · ".join(t for t in all_texts[1:-1] if t != title)[:50] or "개발·기술"

                jobs.append(self._make_job(
                    title=title, company=company, location="서울",
                    experience="", deadline="상시채용",
                    url=url_job, keyword=keyword,
                ))

        finally:
            driver.quit()

        logger.info("[토스] 총 %d건 수집", len(jobs))
        return jobs
