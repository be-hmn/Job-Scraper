"""
모든 스크래퍼의 기반 클래스

HTTP 요청: curl_cffi (impersonate='chrome120')
  - TLS 지문, HTTP/2, 헤더 순서까지 실제 Chrome 120과 동일하게 모사
  - requests 대비 봇 탐지 우회율이 높음

딜레이: random.uniform(3, 7) 초 — 인간다운 체류 시간 부여
"""

import random
import time
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from curl_cffi import requests as cffi_requests
from config import HEADERS, REQUEST_TIMEOUT, CRAWL_DELAY_MIN, CRAWL_DELAY_MAX

logger = logging.getLogger(__name__)

# HTTP 상태 코드별 힌트
_STATUS_HINTS = {
    401: "인증 필요 (로그인/API 키 확인)",
    403: "접근 차단 (IP 차단 또는 봇 감지)",
    404: "엔드포인트 없음 (API 구조 변경 가능성)",
    429: "요청 과다 (레이트 리밋 — CRAWL_DELAY_MAX 값을 늘리세요)",
    503: "서버 일시 불가 (잠시 후 재시도)",
}


class BaseScraper(ABC):
    """채용 공고 스크래퍼 추상 기반 클래스"""

    site_name: str = "Unknown"

    def __init__(self):
        # curl_cffi Session — Chrome 120 TLS/HTTP2 지문 모사
        self.session = cffi_requests.Session(impersonate="chrome120")
        self.session.headers.update(HEADERS)

    def get(
        self,
        url: str,
        params: dict = None,
        **kwargs,
    ) -> Optional[cffi_requests.Response]:
        """
        GET 요청 + 봇 탐지 우회 + 인간다운 딜레이.

        curl_cffi impersonate='chrome120':
          - TLS ClientHello 지문이 실제 Chrome 120과 동일
          - HTTP/2 헤더 순서, pseudo-header 순서까지 모사
          - requests/httpx 대비 Cloudflare, Akamai 우회율 대폭 향상
        """
        # 인간다운 체류 시간 (config에서 설정 가능, 기본 3~7초)
        delay = random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX)
        time.sleep(delay)

        try:
            resp = self.session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            resp.raise_for_status()
            return resp

        except cffi_requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            hint   = _STATUS_HINTS.get(status, "")
            logger.warning(
                "[%s] HTTP %s%s | URL: %s",
                self.site_name, status,
                f" ({hint})" if hint else "",
                url,
            )
            return None
        except cffi_requests.ConnectionError as e:
            logger.warning("[%s] 연결 실패: %s | URL: %s", self.site_name, e, url)
            return None
        except cffi_requests.Timeout:
            logger.warning("[%s] 타임아웃 (%ds) | URL: %s", self.site_name, REQUEST_TIMEOUT, url)
            return None
        except Exception as e:
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
