"""
네이버 채용 스크래퍼
  - https://recruit.navercorp.com/rcrt/list.do (HTML 크롤링)
  - 셀렉터: li.card_item > h4.card_title, dl.card_info dd.info_text
  - onclick="show('공고ID')" 에서 URL 추출
"""

import re
import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://recruit.navercorp.com/rcrt/list.do"
DETAIL_URL = "https://recruit.navercorp.com/rcrt/view.do?annoId={}"

# 네이버 직군 필터 (URL 파라미터 없이 전체 수집 후 키워드 필터링)
IT_KEYWORDS = {
    "개발", "엔지니어", "engineer", "developer", "devops", "보안", "security",
    "데이터", "data", "인프라", "infra", "ai", "ml", "backend", "frontend",
    "sre", "cloud", "클라우드",
}


class NaverScraper(BaseScraper):
    site_name = "네이버"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        for page in range(1, MAX_PAGES + 1):
            params = {"pageNo": page}
            resp = self.get(BASE_URL, params=params,
                            headers={"Referer": "https://recruit.navercorp.com/"})
            if resp is None:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.select("li.card_item")
            if not items:
                break

            for item in items:
                title_tag = item.select_one("h4.card_title")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title:
                    continue

                # IT/개발/보안 직군 필터링
                if not any(kw in title.lower() for kw in IT_KEYWORDS):
                    # dl.card_info 에서 직무 분야도 확인
                    info_texts = [dd.get_text(strip=True).lower()
                                  for dd in item.select("dl.card_info dd.info_text")]
                    if not any(kw in " ".join(info_texts) for kw in IT_KEYWORDS):
                        continue

                # onclick="show('공고ID')" 에서 ID 추출
                link_tag = item.select_one("a.card_link")
                anno_id  = ""
                if link_tag and link_tag.has_attr("onclick"):
                    m = re.search(r"show\('(\d+)'\)", link_tag["onclick"])
                    if m:
                        anno_id = m.group(1)
                url = DETAIL_URL.format(anno_id) if anno_id else ""

                # dl.card_info 파싱
                info = {}
                dl = item.select_one("dl.card_info")
                if dl:
                    dts = dl.select("dt")
                    dds = dl.select("dd.info_text")
                    for dt, dd in zip(dts, dds):
                        info[dt.get_text(strip=True)] = dd.get_text(strip=True)

                dept     = info.get("모집 부서", "")
                field    = info.get("모집 분야", "")
                career   = info.get("모집 경력", "")
                period   = info.get("모집 기간", "")
                deadline = period.split("~")[-1].strip() if "~" in period else period

                jobs.append(self._make_job(
                    title=title,
                    company="네이버",
                    location="성남",
                    experience=career,
                    deadline=deadline,
                    url=url,
                    keyword=f"{dept} {field}".strip() or "개발·기술",
                ))

            logger.info("[네이버] 페이지 %d → %d건 누적", page, len(jobs))

            # 마지막 페이지 감지
            if len(items) < 10:
                break

        return jobs
