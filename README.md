# 🔐 IT/보안 채용 공고 대시보드

국내 주요 채용 사이트에서 IT·보안 관련 공고를 수집하고, 자연어 검색과 필터로 탐색할 수 있는 Streamlit 대시보드입니다.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://be-hmn-job-scraper.streamlit.app)

---

## 주요 기능

- **자연어 검색** — "정보보안 경험 쌓고 싶어" 같은 자유로운 입력을 Gemini가 확장 후 TF-IDF 벡터 검색
- **필터** — 출처 / 근무지 / 경력 / 기술 스택 / 인턴 전용
- **통계 탭** — 출처별·기술스택 TOP 15·경력 분포·근무지 차트
- **11개 사이트 수집** — 사람인, 잡코리아, 원티드, 점핏, 잡플래닛, 링크드인, 랠릿, 카카오, 네이버, 토스, 쿠팡

---

## 프로젝트 구조

```
Job-Scraper/
├── main.py                  # 수집 진입점 (CLI)
├── pipeline.py              # 데이터 정제 파이프라인
├── database.py              # SQLite DB 엔진 (upsert)
├── config.py                # 전역 설정 + is_it_job() 필터
├── utils.py                 # 공통 유틸리티
├── requirements.txt         # Streamlit Cloud 배포용
├── requirements-scraper.txt # 로컬 스크래핑 추가 패키지
├── packages.txt             # Streamlit Cloud apt 패키지
├── .env.example
│
├── scrapers/
│   ├── base.py              # curl_cffi 기반 BaseScraper
│   ├── selenium_base.py     # SeleniumBase UC Mode 베이스
│   ├── selenium_scrapers.py # Selenium 스크래퍼 5개 통합
│   │                          (JobKorea, Jobplanet, Kakao, Toss, Rallit)
│   ├── saramin.py           # 사람인 (HTML + Open API)
│   ├── wanted.py            # 원티드 (JSON API)
│   ├── jumpit.py            # 점핏 (JSON API)
│   ├── linkedin.py          # 링크드인 (HTML)
│   ├── naver.py             # 네이버 (HTML)
│   └── coupang.py           # 쿠팡 (Greenhouse API)
│
├── dashboard/
│   ├── app.py               # Streamlit UI
│   ├── search_engine.py     # TF-IDF 검색 엔진
│   ├── query_expander.py    # LLM 쿼리 확장 (Gemini/OpenAI/Bedrock)
│   └── embedder.py          # 임베딩 추상 레이어
│
└── output/
    ├── job_database.db      # SQLite DB (GitHub에 포함)
    └── pipeline_stats.json  # 파이프라인 통계
```

---

## 지원 사이트 (11개)

| 사이트 | 방식 | Chrome 필요 |
|--------|------|:-----------:|
| 사람인 | HTML / Open API | |
| 잡코리아 | Selenium UC Mode | ✅ |
| 원티드 | JSON API | |
| 점핏 | JSON API | |
| 잡플래닛 | Selenium UC Mode | ✅ |
| 링크드인 | HTML | |
| 랠릿 | Selenium UC Mode | ✅ |
| 카카오 | Selenium UC Mode | ✅ |
| 네이버 | HTML | |
| 토스 | Selenium UC Mode | ✅ |
| 쿠팡 | Greenhouse API | |

---

## 로컬 실행

### 1. 환경 설정

```bash
# 대시보드만 실행할 경우
pip install -r requirements.txt

# 스크래핑까지 실행할 경우
pip install -r requirements.txt -r requirements-scraper.txt
```

`.env.example`을 `.env`로 복사 후 API 키 입력:

```bash
copy .env.example .env
```

### 2. 공고 수집

```bash
# 전체 사이트 수집 → 정제 → DB 저장 (한 번에)
python main.py

# 특정 사이트만
python main.py --sites 원티드 점핏 사람인

# CSV 백업 모드
python main.py --csv

# 스케줄 모드 (매일 새벽 2시)
python main.py --schedule
```

### 3. 대시보드 실행

```bash
python -m streamlit run dashboard/app.py
```

→ http://localhost:8501

---

## Streamlit Cloud 배포

### 배포 설정 파일

| 파일 | 역할 |
|------|------|
| `requirements.txt` | pip 패키지 (대시보드 전용) |
| `packages.txt` | apt 패키지 |

### Secrets 설정

Streamlit Cloud → 앱 Settings → **Secrets** 에 아래 내용 입력:

```toml
GEMINI_API_KEY = "your_gemini_api_key"
GEMINI_MODEL   = "gemini-2.0-flash-lite"

# 선택 사항
# SARAMIN_API_KEY = "your_saramin_api_key"
# OPENAI_API_KEY  = "sk-..."
```

> Gemini API 키가 없으면 규칙 기반 폴백으로 자동 전환되어 검색은 동작합니다.

### DB 업데이트 방법

Streamlit Cloud는 스크래핑을 실행하지 않으므로, 로컬에서 수집 후 DB를 커밋해서 배포합니다:

```bash
python main.py                        # 로컬에서 수집
git add output/job_database.db
git commit -m "chore: DB 업데이트"
git push                              # Cloud가 자동으로 Reboot
```

---

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `GEMINI_API_KEY` | Gemini 쿼리 확장 LLM | — |
| `GEMINI_MODEL` | 사용할 Gemini 모델 | `gemini-2.0-flash-lite` |
| `SARAMIN_API_KEY` | 사람인 Open API (없으면 HTML 폴백) | — |
| `CHROME_BIN` | Chrome 실행파일 경로 (자동 감지 실패 시) | — |
| `CRAWL_DELAY_MIN` | 요청 간 최소 대기 (초) | `3` |
| `CRAWL_DELAY_MAX` | 요청 간 최대 대기 (초) | `7` |

---

## 기술 스택

| 영역 | 라이브러리 |
|------|-----------|
| HTTP 요청 | `curl_cffi` (TLS 지문 모사) |
| Selenium | `SeleniumBase` UC Mode |
| 중복 제거 | `rapidfuzz` (Fuzzy Matching 90%) |
| 검색 | `scikit-learn` TF-IDF (char n-gram) |
| LLM | `google-generativeai` (Gemini) |
| DB | SQLite (`database.py` upsert) |
| 대시보드 | `streamlit` + `plotly` |

---

## 주의사항

- 각 사이트의 이용약관을 준수하세요.
- `--workers` 기본값은 3입니다. Selenium 사이트는 1~2 권장.
- 로그는 `output/scraper.log`에 저장됩니다.
- `output/job_database.db`는 GitHub에 포함되어 있어 배포 즉시 데이터를 확인할 수 있습니다.
