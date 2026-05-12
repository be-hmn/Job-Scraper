"""
크롤러 공통 설정
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── 서비스 식별 정보 ─────────────────────────────────────────────
# 크롤러 매너: User-Agent에 서비스명과 연락처를 명시합니다.
# 사이트 운영자가 문의할 수 있도록 실제 연락처로 변경하세요.
SERVICE_NAME    = os.getenv("SERVICE_NAME", "IT-Job-Scraper")
SERVICE_CONTACT = os.getenv("SERVICE_CONTACT", "your-email@example.com")
SERVICE_URL     = os.getenv("SERVICE_URL", "https://github.com/be-hmn/Job-Scraper")

# ── 사람인 Open API ──────────────────────────────────────────────
SARAMIN_API_KEY = os.getenv("SARAMIN_API_KEY", "")
SARAMIN_API_URL = "https://oapi.saramin.co.kr/job-search"

# IT/보안 관련 검색 키워드 (사람인 Open API용)
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
    # 인턴십
    "개발인턴",
    "보안인턴",
    "IT인턴",
]

# ── 크롤링 공통 설정 ─────────────────────────────────────────────
# CRAWL_DELAY_MIN/MAX: 요청 간 랜덤 대기 범위 (초)
# 기본값 3~7초. 차단이 잦으면 늘리세요.
CRAWL_DELAY_MIN = float(os.getenv("CRAWL_DELAY_MIN", "3"))
CRAWL_DELAY_MAX = float(os.getenv("CRAWL_DELAY_MAX", "7"))

MAX_PAGES       = 5   # 사이트별 최대 크롤링 페이지 수
REQUEST_TIMEOUT = 15  # HTTP 요청 타임아웃 (초)

# ── HTTP 헤더 ────────────────────────────────────────────────────
# curl_cffi impersonate='chrome120' 사용 시 User-Agent는 자동 설정되지만,
# 서비스 식별을 위해 X-Crawler-Info 헤더를 추가합니다.
HEADERS = {
    "User-Agent": (
        f"Mozilla/5.0 (compatible; {SERVICE_NAME}/1.0; "
        f"+{SERVICE_URL}; {SERVICE_CONTACT})"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "X-Crawler-Info": f"{SERVICE_NAME} ({SERVICE_CONTACT})",
}

# ── 출력 설정 ────────────────────────────────────────────────────
OUTPUT_DIR   = "output"
CSV_FILENAME = "it_security_jobs.csv"


# ── IT/보안 공고 필터 ────────────────────────────────────────────
# 수집 후 비IT 공고를 걸러내는 화이트리스트 키워드
# 공고 제목에 아래 키워드 중 하나라도 포함되면 IT 공고로 간주
IT_TITLE_WHITELIST = {
    # 개발
    "개발", "developer", "engineer", "엔지니어", "프로그래머", "programmer",
    "backend", "백엔드", "frontend", "프론트엔드", "fullstack", "풀스택",
    "software", "소프트웨어", "web", "웹", "app", "앱", "mobile", "모바일",
    "ios", "android", "flutter", "react", "vue", "spring", "django",
    # 인프라/DevOps
    "devops", "sre", "infra", "인프라", "cloud", "클라우드", "aws", "gcp", "azure",
    "kubernetes", "docker", "linux", "서버", "server",
    # 데이터/AI
    "data", "데이터", "ai", "ml", "머신러닝", "딥러닝", "분석", "analyst",
    "scientist", "mlops", "llm",
    # 보안 (IT 보안만)
    "정보보안", "보안엔지니어", "security engineer", "침해대응", "취약점",
    "siem", "soc", "devsecops", "모의해킹", "pentest", "forensic",
    "cybersecurity", "사이버보안", "보안관제", "iam", "waf",
    # 기타 IT
    "qa", "테스트", "architect", "아키텍트", "cto", "tech lead",
    "dba", "database", "데이터베이스",
}

# 비IT 공고 블랙리스트 (제목에 포함 시 제외)
NON_IT_BLACKLIST = {
    "경비", "시설보안", "보안요원", "경호", "청원경찰", "방범",
    "물리보안", "출동", "순찰", "경비원", "보안직",
}


def is_it_job(title: str) -> bool:
    """공고 제목이 IT/보안 직무인지 판별한다."""
    if not title:
        return False
    t = title.lower()

    # 블랙리스트 먼저 확인 (물리 보안 등 명확한 비IT)
    if any(kw in t for kw in NON_IT_BLACKLIST):
        return False

    # 화이트리스트 확인
    return any(kw in t for kw in IT_TITLE_WHITELIST)
