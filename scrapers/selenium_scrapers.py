"""
Selenium UC Mode 기반 스크래퍼 모음
────────────────────────────────────────────────────────────────
SeleniumBase UC Mode를 사용하는 사이트들을 한 파일에 모았습니다.
각 사이트는 독립 클래스로 분리되어 있으며, 공통 흐름은 SeleniumBaseScraper가 담당합니다.

포함 사이트:
  - JobKoreaScraper  : 잡코리아
  - JobplanetScraper : 잡플래닛
  - KakaoScraper     : 카카오
  - TossScraper      : 토스
  - RallitScraper    : 랠릿
"""

import re
import logging
from typing import List, Dict

from bs4 import BeautifulSoup

from config import MAX_PAGES, is_it_job
from scrapers.selenium_base import SeleniumBaseScraper

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 잡코리아
# ════════════════════════════════════════════════════════════════

_JK_LOC_RE  = re.compile(r"서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주")
_JK_EXP_RE  = re.compile(r"경력\s*\d|신입|무관|년\s*이상|년↑")
_JK_DATE_RE = re.compile(r"\d{2}/\d{2}|\d{4}-\d{2}-\d{2}")

_JK_KEYWORDS = {
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


def _jk_parse_card(card_el) -> dict:
    """잡코리아 카드에서 근무지/경력/마감일 추출"""
    parts = [p.strip() for p in card_el.get_text(separator="|").split("|") if p.strip()]
    loc = exp = deadline = ""
    for p in parts:
        if not loc and _JK_LOC_RE.search(p) and len(p) < 25:
            loc = p
        if not exp and _JK_EXP_RE.search(p) and len(p) < 20:
            exp = p
        if not deadline and _JK_DATE_RE.search(p):
            deadline = p.replace("마감", "").strip()
    return {"location": loc, "experience": exp, "deadline": deadline}


class JobKoreaScraper(SeleniumBaseScraper):
    site_name = "잡코리아"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        with self._get_sb_context() as sb:
            for keyword, label in _JK_KEYWORDS.items():
                for page in range(1, MAX_PAGES + 1):
                    url = (
                        f"https://www.jobkorea.co.kr/Search/"
                        f"?tabType=recruit&stext={keyword}&Page_No={page}"
                    )
                    if not self._wait_and_get(sb, url, "a[href*='/Recruit/GI_Read/']"):
                        break

                    soup = BeautifulSoup(sb.get_page_source(), "lxml")
                    card_map: dict[str, list] = {}
                    for link in soup.select("a[href*='/Recruit/GI_Read/']"):
                        m = re.search(r"/Recruit/GI_Read/(\d+)", link.get("href", ""))
                        if m:
                            card_map.setdefault(m.group(1), []).append(link)

                    if not card_map:
                        break

                    seen = set()
                    for rec_id, links in card_map.items():
                        if rec_id in seen:
                            continue
                        seen.add(rec_id)
                        text_links = [l for l in links if l.get_text(strip=True)]
                        if not text_links:
                            continue
                        title   = text_links[0].get_text(strip=True)
                        company = text_links[1].get_text(strip=True) if len(text_links) > 1 else ""
                        if not title or len(title) < 3:
                            continue

                        card = None
                        el = text_links[0]
                        for _ in range(8):
                            el = el.parent
                            if el is None:
                                break
                            cls = " ".join(el.get("class", []))
                            if "rounded-2xl" in cls and ("shadow" in cls or "p-7" in cls):
                                card = el
                                break

                        extra = _jk_parse_card(card) if card else {}
                        if not is_it_job(title):
                            continue
                        jobs.append(self._make_job(
                            title=title, company=company,
                            location=extra.get("location", ""),
                            experience=extra.get("experience", ""),
                            deadline=extra.get("deadline", ""),
                            url=f"https://www.jobkorea.co.kr/Recruit/GI_Read/{rec_id}",
                            keyword=label,
                        ))

                    logger.info("[잡코리아] '%s' 페이지 %d → %d건 누적", keyword, page, len(jobs))

        return jobs


# ════════════════════════════════════════════════════════════════
# 잡플래닛
# ════════════════════════════════════════════════════════════════

_JP_EXP_RE = re.compile(r"\d+년|신입|경력무관|무관")
_JP_LOC_RE = re.compile(r"서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주")

_JP_KEYWORDS = ["백엔드", "프론트엔드", "DevOps", "보안", "데이터엔지니어", "클라우드", "AI엔지니어"]


class JobplanetScraper(SeleniumBaseScraper):
    site_name = "잡플래닛"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        with self._get_sb_context() as sb:
            for keyword in _JP_KEYWORDS:
                for page in range(1, MAX_PAGES + 1):
                    url = f"https://www.jobplanet.co.kr/job/search?q={keyword}&page={page}"
                    if not self._wait_and_get(sb, url, "a[href*='posting_ids']"):
                        break

                    soup = BeautifulSoup(sb.get_page_source(), "lxml")
                    job_links = soup.select("a[href*='posting_ids']")
                    if not job_links:
                        break

                    for link in job_links:
                        href    = link.get("href", "")
                        url_job = href if href.startswith("http") else f"https://www.jobplanet.co.kr{href}"
                        parts   = [p.strip() for p in link.get_text(separator="|").split("|") if p.strip()]
                        if not parts:
                            continue

                        company = parts[0] if len(parts) > 0 else ""
                        title   = parts[1] if len(parts) > 1 else parts[0]
                        exp = loc = ""
                        for p in parts[2:]:
                            if not exp and _JP_EXP_RE.search(p) and len(p) < 20:
                                exp = p
                            if not loc and _JP_LOC_RE.search(p) and len(p) < 20:
                                loc = p
                        if len(parts) == 1:
                            title, company = parts[0], ""

                        if title:
                            if not is_it_job(title):
                                continue
                            jobs.append(self._make_job(
                                title=title, company=company, location=loc,
                                experience=exp, deadline="상시채용",
                                url=url_job, keyword=keyword,
                            ))

                    logger.info("[잡플래닛] '%s' 페이지 %d → %d건 누적", keyword, page, len(jobs))

        return jobs


# ════════════════════════════════════════════════════════════════
# 카카오
# ════════════════════════════════════════════════════════════════

_KAKAO_PARTS = {
    "TECHNOLOGY": "개발·기술",
    "SECURITY":   "보안",
    "DATA":       "데이터",
    "INFRA":      "인프라·DevOps",
}


class KakaoScraper(SeleniumBaseScraper):
    site_name = "카카오"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        with self._get_sb_context() as sb:
            for part, label in _KAKAO_PARTS.items():
                for page in range(1, MAX_PAGES + 1):
                    url = f"https://careers.kakao.com/jobs?part={part}&page={page}"
                    if not self._wait_and_get(sb, url, "div.area_info, div.wrap_info"):
                        break

                    soup  = BeautifulSoup(sb.get_page_source(), "lxml")
                    items = soup.select("div.area_info")
                    if not items:
                        break

                    for item in items:
                        title_tag = item.select_one("h4.tit_jobs, h3.tit_jobs")
                        title = title_tag.get_text(strip=True) if title_tag else ""
                        if not title:
                            continue

                        subinfo_dds   = item.select("dl.item_subinfo dd")
                        company       = subinfo_dds[0].get_text(strip=True) if subinfo_dds else "카카오"
                        list_info_dds = item.select("dl.list_info dd")
                        deadline      = list_info_dds[0].get_text(strip=True) if list_info_dds else "상시채용"
                        location      = list_info_dds[1].get_text(strip=True) if len(list_info_dds) > 1 else "판교"

                        parent  = item.find_parent("li")
                        link    = parent.select_one("a[href*='/jobs/']") if parent else None
                        if not link:
                            link = item.find_parent("a")
                        href    = link["href"] if link and link.has_attr("href") else ""
                        url_job = (f"https://careers.kakao.com{href}" if href.startswith("/") else href) or url

                        jobs.append(self._make_job(
                            title=title, company=company, location=location,
                            experience="", deadline=deadline,
                            url=url_job, keyword=label,
                        ))

                    logger.info("[카카오] %s 페이지 %d → %d건 누적", label, page, len(jobs))
                    if len(items) < 10:
                        break

        return jobs


# ════════════════════════════════════════════════════════════════
# 토스
# ════════════════════════════════════════════════════════════════

_TOSS_IT_LABELS = {
    "개발", "보안", "데이터", "인프라", "devops", "sre", "ai",
    "머신러닝", "백엔드", "프론트엔드", "풀스택", "ios", "android",
    "engineer", "developer", "security", "data", "infra", "software",
}


class TossScraper(SeleniumBaseScraper):
    site_name = "토스"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        with self._get_sb_context() as sb:
            url = "https://toss.im/career/jobs"
            if not self._wait_and_get(sb, url, "li.css-1lnizc9"):
                logger.warning("[토스] 페이지 로드 실패")
                return jobs

            soup  = BeautifulSoup(sb.get_page_source(), "lxml")
            items = soup.select("li.css-1lnizc9")
            logger.info("[토스] 공고 카드 %d개 발견", len(items))

            for item in items:
                title_tag = item.select_one("p[data-desktop-list-item-title]")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title:
                    continue

                combined = title.lower() + " " + " ".join(
                    s.get_text(strip=True) for s in item.select("span")
                ).lower()
                if not any(kw in combined for kw in _TOSS_IT_LABELS):
                    continue

                all_texts = [t.strip() for t in item.get_text(separator="|").split("|") if t.strip()]
                company   = all_texts[-1] if all_texts else "토스"
                link      = item.find_parent("a") or item.select_one("a[href]")
                href      = link["href"] if link and link.has_attr("href") else ""
                url_job   = f"https://toss.im{href}" if href.startswith("/") else href or url
                keyword   = " · ".join(t for t in all_texts[1:-1] if t != title)[:50] or "개발·기술"

                jobs.append(self._make_job(
                    title=title, company=company, location="서울",
                    experience="", deadline="상시채용",
                    url=url_job, keyword=keyword,
                ))

        logger.info("[토스] 총 %d건 수집", len(jobs))
        return jobs


# ════════════════════════════════════════════════════════════════
# 랠릿
# ════════════════════════════════════════════════════════════════

_RALLIT_POSITIONS = {
    "BACKEND":   "백엔드",
    "FRONTEND":  "프론트엔드",
    "DEVOPS":    "DevOps·인프라",
    "DATA":      "데이터",
    "SECURITY":  "보안",
    "MOBILE":    "모바일",
    "AI":        "AI·ML",
}


class RallitScraper(SeleniumBaseScraper):
    site_name = "랠릿"

    def scrape(self) -> List[Dict]:
        jobs: List[Dict] = []

        with self._get_sb_context() as sb:
            for pos_type, label in _RALLIT_POSITIONS.items():
                page = 0
                while page < MAX_PAGES:
                    url = f"https://www.rallit.com/positions?jobType={pos_type}&page={page}"
                    if not self._wait_and_get(sb, url, "article"):
                        break

                    soup  = BeautifulSoup(sb.get_page_source(), "lxml")
                    items = soup.select("article")
                    if not items:
                        break

                    prev = len(jobs)
                    for item in items:
                        title_tag = item.select_one("h2, h3, h4")
                        if title_tag:
                            title = title_tag.get_text(strip=True)
                        else:
                            ps    = item.select("p")
                            t     = max(ps, key=lambda x: len(x.get_text()), default=None)
                            title = t.get_text(strip=True)[:80] if t else ""

                        if not title or len(title) < 3:
                            continue

                        company = ""
                        for el in item.select("span, p"):
                            txt = el.get_text(strip=True)
                            if txt and txt != title and 1 < len(txt) < 40:
                                company = txt
                                break

                        link    = item.select_one("a[href*='/positions/']") or item.find_parent("a")
                        href    = link["href"] if link and link.has_attr("href") else ""
                        url_job = f"https://www.rallit.com{href}" if href.startswith("/") else href

                        jobs.append(self._make_job(
                            title=title, company=company, location="",
                            experience="", deadline="상시채용",
                            url=url_job, keyword=label,
                        ))

                    added = len(jobs) - prev
                    logger.info("[랠릿] %s 페이지 %d → +%d건 (누적 %d건)", label, page, added, len(jobs))
                    if added == 0:
                        break
                    page += 1

        return jobs
