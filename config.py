"""
크롤러 공통 설정
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── 사람인 Open API ──────────────────────────────────────────────
SARAMIN_API_KEY = os.getenv("SARAMIN_API_KEY", "")
SARAMIN_API_URL = "https://oapi.saramin.co.kr/job-search"

# IT/보안 관련 검색 키워드
IT_SECURITY_KEYWORDS = [
    "보안",
    "정보보안",
    "네트워크보안",
    "클라우드보안",
    "보안엔지니어",
    "침해대응",
    "취약점분석",
    "보안관제",
    "DevSecOps",
    "SIEM",
    "SOC",
    "사이버보안",
    "백엔드",
    "프론트엔드",
    "풀스택",
    "데이터엔지니어",
    "클라우드",
    "DevOps",
    "SRE",
    "AI엔지니어",
]

# ── 크롤링 공통 설정 ─────────────────────────────────────────────
REQUEST_DELAY = 1.5          # 요청 간 대기 시간 (초)
MAX_PAGES     = 5            # 사이트별 최대 크롤링 페이지 수
REQUEST_TIMEOUT = 15         # HTTP 요청 타임아웃 (초)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── 출력 설정 ────────────────────────────────────────────────────
OUTPUT_DIR = "output"
CSV_FILENAME = "it_security_jobs.csv"
