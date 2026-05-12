# Job-Scraper 프로젝트 컨텍스트

> 이 문서는 프로젝트의 전체 개발 히스토리와 현재 상태를 요약합니다.
> 새 채팅에서 이 파일을 참조하면 이전 맥락을 이어받을 수 있습니다.

---

## 프로젝트 개요

국내 주요 채용 사이트에서 IT/보안 관련 공고를 수집하고, 데이터 정제 파이프라인을 거쳐 Streamlit 대시보드로 시각화하는 통합 스크래퍼입니다.

**GitHub**: https://github.com/be-hmn/Job-Scraper  
**운영 환경**: Windows, Python 3.13, PowerShell

---

## 전체 실행 흐름

```
python main.py          → 수집 → 정제(pipeline) → DB 저장
python -m streamlit run dashboard/app.py → http://localhost:8501
```

---

## 프로젝트 구조

```
Job-Scraper/
├── main.py                  # 수집 진입점 (CLI)
├── pipeline.py              # 데이터 정제 파이프라인
├── database.py              # SQLite DB 엔진
├── config.py                # 전역 설정 + is_it_job() 필터
├── utils.py                 # 공통 유틸리티
├── test_scrapers.py         # 동적 스크래퍼 테스트
├── requirements.txt
├── .env / .env.example
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
│   ├── search_engine.py     # 검색 엔진 (TF-IDF + 필터)
│   ├── query_expander.py    # LLM 쿼리 확장 (Gemini/OpenAI/Bedrock)
│   └── embedder.py          # 임베딩 추상 레이어
│
└── output/
    ├── job_database.db      # SQLite DB (주 저장소)
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

## 핵심 기술 스택

- **HTTP 요청**: `curl_cffi` (impersonate='chrome120') — TLS 지문 모사, 봇 탐지 우회
- **Selenium**: `SeleniumBase` UC Mode — headless Chrome, Cloudflare 우회
- **딜레이**: `random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX)` (기본 3~7초)
- **중복 제거**: RapidFuzz Fuzzy Matching (유사도 90% 임계값)
- **검색**: TF-IDF (char n-gram, 한국어 최적화)
- **LLM 쿼리 확장**: Google Gemini (gemini-2.5-flash-lite 기본값)
- **DB**: SQLite (`output/job_database.db`)

---

## 데이터 파이프라인 (`pipeline.py`)

```
CSV 로드 → uid 생성(SHA-256) → 원본 통계 스냅샷
→ Fuzzy 중복 제거 → 경력 수치화(min_exp/max_exp)
→ 기술 스택 추출(tech_stack) → 검색 텍스트 전처리
→ SQLite DB 저장 (upsert)
```

**Upsert 전략**: 동일 uid → 마감일만 갱신, 신규 → INSERT

---

## 검색 엔진 구조 (`dashboard/search_engine.py`)

```
자연어 입력
    ↓ Gemini (query_expander.py)
확장된 search_query
    ↓ TF-IDF 벡터화
코사인 유사도 계산 (전체 공고 대상)
    ↓ UI 필터 적용 (출처/근무지/경력/기술스택/인턴)
    ↓ min_score=10.0 임계값 필터
결과 반환 (유사도 순)
```

**LLM 우선순위**: Gemini → OpenAI → Bedrock → 규칙 기반 폴백

---

## 환경변수 설정 (`.env`)

```bash
# Gemini (쿼리 확장 LLM)
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.5-flash-lite   # free tier 최소 토큰 모델

# 사람인 Open API (선택)
SARAMIN_API_KEY=your_key

# Chrome 경로 (자동 감지 실패 시)
CHROME_BIN=C:\Program Files\Google\Chrome\Application\chrome.exe

# 크롤링 딜레이 (초)
CRAWL_DELAY_MIN=3
CRAWL_DELAY_MAX=7

# 서비스 식별 (크롤러 매너)
SERVICE_NAME=IT-Job-Scraper
SERVICE_CONTACT=your-email@example.com
```

---

## 주요 설계 결정 및 히스토리

### 1. 저장 방식: CSV → SQLite
- 초기: CSV 파일 기반
- 변경: SQLite DB 직통 (`main.py` → `pipeline.py` → `job_database.db`)
- 이유: 증분 저장, uid 기반 중복 방지, SQL 필터링 가능

### 2. HTTP 라이브러리: requests → curl_cffi
- 이유: TLS 지문 모사로 Cloudflare 등 봇 탐지 우회율 향상

### 3. Selenium: webdriver → SeleniumBase UC Mode
- 이유: `navigator.webdriver=false` 패치, headless에서도 봇 탐지 우회

### 4. 검색 방식
- 하이브리드 검색(필터+벡터) 제거
- LLM 쿼리 확장 → TF-IDF 벡터 검색으로 단순화
- 이유: SQL 선필터가 TF-IDF 기회를 차단하는 문제 방지

### 5. 비IT 공고 필터링
- 문제: 사람인 카테고리 86(보안·경호), 잡코리아 "보안" 키워드에 물리 보안 공고 유입
- 해결: `config.py`의 `is_it_job()` 함수 — 화이트리스트/블랙리스트 기반

### 6. Selenium 스크래퍼 통합
- 5개 개별 파일 → `selenium_scrapers.py` 하나로 통합
- 개별 파일은 shim으로 유지 (하위 호환)

---

## 알려진 이슈 및 제약

| 항목 | 내용 |
|------|------|
| Gemini 429 오류 | 월간 지출 한도 초과 시 규칙 기반 폴백으로 자동 전환 |
| Selenium 속도 | 사이트당 3~7초 딜레이 × 키워드 수 × 페이지 수 |
| 잡코리아 근무지 | 카드 파싱 실패 시 일부 nan 발생 |
| 원티드/토스 경력 | API가 경력 정보 미제공 |
| 쿠팡/랠릿 근무지 | API 응답에 미포함 |

---

## 대시보드 기능

### 검색 탭
- 자연어 입력 → Gemini 쿼리 확장 → TF-IDF 검색
- 필터: 출처 / 근무지 / 경력(신입=경력무관 포함) / 기술스택 / 인턴 전용
- 유사도 10% 이상 공고만 표시

### 통계 탭
- 출처별 공고 수 (기업 직접 채용은 "개별 공고"로 합산)
- 기술 스택 TOP 15
- 경력 분포
- 근무지 TOP 10

---

## 주요 파일별 핵심 로직

### `config.py`
```python
is_it_job(title: str) -> bool
# IT 화이트리스트 + 물리보안 블랙리스트로 비IT 공고 필터링
```

### `pipeline.py`
```python
run_pipeline_from_jobs(jobs: List[Dict])  # main.py에서 직접 호출
run_pipeline_from_csv(input_path: str)    # CLI에서 CSV 입력
```

### `database.py`
```python
upsert_jobs(df, db_path)   # INSERT OR IGNORE + 마감일 갱신
query_jobs(db_path, ...)   # SQL 필터 조회
```

### `dashboard/query_expander.py`
```python
expand_query(query: str) -> dict
# 반환: {"search_query": str, "summary": str, "provider": str}
# LLM 우선순위: Gemini → OpenAI → Bedrock → 규칙 기반
```

### `dashboard/search_engine.py`
```python
expanded_search(query, sources, locations, experience,
                tech_stack, intern_only, min_score=10.0)
# → (results_df, params_dict)
```

---

## 실행 명령어 요약

```bash
# 수집 + 정제 + DB 저장 (한 번에)
python main.py

# 특정 사이트만
python main.py --sites 원티드 점핏 사람인

# CSV 백업 모드
python main.py --csv

# 스케줄 모드 (매일 새벽 2시)
python main.py --schedule

# 파이프라인만 (기존 CSV → DB)
python pipeline.py

# 대시보드
python -m streamlit run dashboard/app.py

# 스크래퍼 테스트
python test_scrapers.py --sites 원티드 점핏
```

---

## 의존성 (`requirements.txt`)

```
requests, beautifulsoup4, selenium, seleniumbase
pandas, lxml, python-dotenv
rapidfuzz, curl_cffi
google-genai
```

---

*최종 업데이트: 2026-05-12*
