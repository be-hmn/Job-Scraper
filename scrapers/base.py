"""
모든 스크래퍼의 기반 클래스
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

import requests
from config import HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

# HTTP 상태 코드별 메시지
_STATUS_HINTS = {
    401: "인증 필요 (로그인/API 키 확인)",
    403: "접근 차단 (IP 차단 또는 봇 감지)",
    404: "엔드포인트 없음 (API 구조 변경 가능성)",
    429: "요청 과다 (레이트 리밋 — 딜레이 증가 필요)",
    503: "서버 일시 불가 (잠시 후 재시도)",
}


class BaseScraper(ABC):
    """채용 공고 스크래퍼 추상 기반 클래스"""

    site_name: str = "Unknown"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get(
        self,
        url: str,
        params: dict = None,
        **kwargs,
    ) -> Optional[requests.Response]:
        """GET 요청 + 에러 처리 + 딜레이"""
        try:
            time.sleep(REQUEST_DELAY)
            resp = self.session.get(
                url, params=params, timeout=REQUEST_TIMEOUT, **kwargs
            )
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            hint   = _STATUS_HINTS.get(status, "")
            logger.warning(
                "[%s] HTTP %s%s | URL: %s",
                self.site_name,
                status,
                f" ({hint})" if hint else "",
                url,
            )
            return None
        except requests.ConnectionError as e:
            logger.warning("[%s] 연결 실패: %s | URL: %s", self.site_name, e, url)
            return None
        except requests.Timeout:
            logger.warning("[%s] 타임아웃 (%ds) | URL: %s", self.site_name, REQUEST_TIMEOUT, url)
            return None
        except requests.RequestException as e:
            logger.warning("[%s] 요청 실패: %s | URL: %s", self.site_name, e, url)
            return None

    @abstractmethod
    def scrape(self) -> List[Dict]:
        """
        채용 공고 목록을 반환한다.
        각 항목은 아래 키를 포함해야 한다:
          - title       : 공고 제목
          - company     : 회사명
          - location    : 근무지
          - experience  : 경력 조건
          - deadline    : 마감일
          - url         : 공고 URL
          - source      : 출처 사이트명
          - keyword     : 검색 키워드 (해당 시)
        """
        ...

    def _make_job(
        self,
        title: str = "",
        company: str = "",
        location: str = "",
        experience: str = "",
        deadline: str = "",
        url: str = "",
        keyword: str = "",
    ) -> Dict:
        return {
            "title":      title.strip(),
            "company":    company.strip(),
            "location":   location.strip(),
            "experience": experience.strip(),
            "deadline":   deadline.strip(),
            "url":        url.strip(),
            "source":     self.site_name,
            "keyword":    keyword.strip(),
        }
