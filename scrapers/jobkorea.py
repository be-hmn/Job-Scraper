"""
잡코리아 스크래퍼 (Selenium)
  - Next.js SPA → Selenium으로 렌더링 후 파싱
  - 공고 카드: div.w-full.rounded-2xl (shadow-list 포함)
  - 카드 텍스트 구조: [제목]|[회사명]|[근무지]|[직무태그]|[경력]|[마감일]
"""

import re
import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES
from scrapers.selenium_base import SeleniumBaseScraper

logger = logging.getLogger(__name__)

# 지역명 패턴
_LOC_RE  = re.compile(r"서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주")
# 경력 패턴
_EXP_RE  = re.compile(r"경력\s*\d|신입|무관|년\s*이상|년↑")
# 마감일 패턴
_DATE_RE = re.compile(r"\d{2}/\d{2}|\d{4}-\d{2}-\d{2}")

SEARCH_KEYWORDS = {
    "백엔드":         "백엔드",
    "프론트엔드":     "프론트엔드",
    "DevOps":         "DevOps·인프라",
    "보안":           "보안",
    "데이터엔지니어": "데이터",
    "클라우드":       "클라우드",
    "AI엔지니어":     "AI·ML",
    "개발 인턴":      "인턴",
    "보안 인턴":      "인턴",
}


def _parse_card(card_el) -> dict:
    """
    카드 div에서 근무지/경력/마감일을 추출한다.
    카드 텍스트 예시:
      오늘 뜬 따끈한 공고|스크랩|[제목]|시프트원㈜|경기 이천시|솔루션·SI|즉시 지원|경력10년↑|2시간 전 등록|•|06/10(수) 마감
    """
    parts = [p.strip() for p in card_el.get_text(separator="|").split("|") if p.strip()]
    loc = exp = deadline = ""
    for p in parts:
        if not loc and _LOC_RE.search(p) and len(p) < 25:
            loc = p
        if not exp and _EXP_RE.search(p) and len(p) < 20:
            exp = p
        if not deadline and _DATE_RE.search(p):
            deadline = p.replace("마감", "").strip()
    return {"location": loc, "experience": exp, "deadline": deadline}


class JobKoreaScraper(SeleniumBaseScraper):
    site_name = "잡코리아"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []
        driver = self._get_driver()

        try:
            for keyword, label in SEARCH_KEYWORDS.items():
                for page in range(1, MAX_PAGES + 1):
                    url = (
                        f"https://www.jobkorea.co.kr/Search/"
                        f"?tabType=recruit&stext={keyword}&Page_No={page}"
                    )
                    ok = self._wait_and_get(
                        driver, url,
                        "a[href*='/Recruit/GI_Read/']",
                        timeout=20,
                    )
                    if not ok:
                        logger.info("[잡코리아] '%s' 페이지 %d: 로드 실패", keyword, page)
                        break

                    soup = BeautifulSoup(driver.page_source, "lxml")

                    # ── 카드 단위 파싱 ──────────────────────────────────
                    # 같은 GI_Read ID를 공유하는 링크들을 그룹화
                    card_map: dict[str, list] = {}
                    for link in soup.select("a[href*='/Recruit/GI_Read/']"):
                        m = re.search(r"/Recruit/GI_Read/(\d+)", link.get("href", ""))
                        if m:
                            card_map.setdefault(m.group(1), []).append(link)

                    if not card_map:
                        logger.info("[잡코리아] '%s' 페이지 %d: 공고 없음", keyword, page)
                        break

                    seen = set()
                    for rec_id, links in card_map.items():
                        if rec_id in seen:
                            continue
                        seen.add(rec_id)

                        # 텍스트 있는 링크: [0]=제목, [1]=회사명
                        text_links = [l for l in links if l.get_text(strip=True)]
                        if not text_links:
                            continue

                        title   = text_links[0].get_text(strip=True)
                        company = text_links[1].get_text(strip=True) if len(text_links) > 1 else ""

                        if not title or len(title) < 3:
                            continue

                        # 카드 컨테이너 탐색: 제목 링크 기준으로 위로 올라가며 찾기
                        card = None
                        el = text_links[0]
                        for _ in range(8):
                            el = el.parent
                            if el is None:
                                break
                            cls = " ".join(el.get("class", []))
                            # "rounded-2xl"과 "shadow" 또는 "p-7"이 함께 있는 div
                            if "rounded-2xl" in cls and ("shadow" in cls or "p-7" in cls):
                                card = el
                                break

                        extra = _parse_card(card) if card else {}

                        jobs.append(self._make_job(
                            title=title,
                            company=company,
                            location=extra.get("location", ""),
                            experience=extra.get("experience", ""),
                            deadline=extra.get("deadline", ""),
                            url=f"https://www.jobkorea.co.kr/Recruit/GI_Read/{rec_id}",
                            keyword=label,
                        ))

                    logger.info("[잡코리아] '%s' 페이지 %d → %d건 누적", keyword, page, len(jobs))
        finally:
            driver.quit()

        return jobs
