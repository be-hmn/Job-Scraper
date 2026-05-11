# IT/보안 채용 공고 통합 스크래퍼

국내 주요 채용 사이트에서 IT·보안 관련 공고를 수집하고, 데이터 정제 파이프라인을 거쳐 Streamlit 대시보드로 시각화합니다.

---

## 프로젝트 구조

```
Job-Scraper/
├── main.py              # 수집 실행 진입점 (CLI)
├── pipeline.py          # 데이터 정제 파이프라인
├── config.py            # 전역 설정 (키워드, 딜레이 등)
├── utils.py             # 중복 제거, CSV 저장, 로깅
├── test_scrapers.py     # 동적 스크래퍼 테스트
├── requirements.txt
├── .env.example
│
├── scrapers/
│   ├── base.py          # BaseScraper 추상 클래스
│   ├── selenium_base.py # Selenium 기반 스크래퍼 공통 베이스
│   ├── saramin.py       # 사람인 (HTML)
│   ├── jobkorea.py      # 잡코리아 (Selenium)
│   ├── wanted.py        # 원티드 (JSON API)
│   ├── jumpit.py        # 점핏 (JSON API)
│   ├── jobplanet.py     # 잡플래닛 (Selenium)
│   ├── linkedin.py      # 링크드인 (HTML)
│   ├── rallit.py        # 랠릿 (Selenium)
│   ├── kakao.py         # 카카오 (Selenium)
│   ├── naver.py         # 네이버 (HTML)
│   ├── toss.py          # 토스 (Selenium)
│   └── coupang.py       # 쿠팡 (Greenhouse API)
│
├── dashboard/
│   ├── app.py           # Streamlit 대시보드
│   ├── search_engine.py # 필터/시맨틱/하이브리드 검색
│   └── embedder.py      # 임베딩 추상 레이어 (TF-IDF/Local/Bedrock/OpenAI)
│
└── output/              # 수집 결과 CSV (gitignore)
    ├── it_security_jobs_YYYYMMDD_HHMMSS.csv  # 원본 수집 결과
    └── cleaned_job_postings.csv              # 파이프라인 처리 결과
```

---

## 지원 사이트 (11개)

| 사이트 | 방식 | Chrome 필요 |
|--------|------|:-----------:|
| 사람인 | HTML 크롤링 / Open API | |
| 잡코리아 | Selenium | ✅ |
| 원티드 | 내부 JSON API | |
| 점핏 | 내부 JSON API | |
| 잡플래닛 | Selenium | ✅ |
| 링크드인 | HTML 크롤링 | |
| 랠릿 | Selenium | ✅ |
| 카카오 | Selenium | ✅ |
| 네이버 | HTML 크롤링 | |
| 토스 | Selenium | ✅ |
| 쿠팡 | Greenhouse 공개 API | |

---

## 설치

```bash
pip install -r requirements.txt
```

Selenium 사이트 수집을 위해 **Chrome 브라우저**가 필요합니다.
- 설치: https://www.google.com/chrome/
- 또는 `.env`에 `CHROME_BIN=C:\path\to\chrome.exe` 설정

---

## 사용법

### 1단계: 수집

```bash
# 전체 사이트 수집 (기본)
python main.py

# 특정 사이트만
python main.py --sites 사람인 원티드 점핏

# 동시 실행 수 조정 (기본 3, Selenium 사이트는 1~2 권장)
python main.py --workers 2
```

### 2단계: 데이터 정제 파이프라인

```bash
python pipeline.py
```

파이프라인이 수행하는 작업:
- **Fuzzy 중복 제거**: RapidFuzz 유사도 90% 이상 → 최신 공고 유지
- **경력 수치화**: `min_exp` / `max_exp` 컬럼 생성 (예: "3~5년" → 3, 5)
- **기술 스택 추출**: 50개 키워드 패턴 매칭 → `tech_stack` 리스트 컬럼
- **SHA-256 uid**: 증분 저장 (재실행 시 신규 공고만 추가)
- **검색 텍스트 전처리**: `_search_text` 컬럼 생성

### 3단계: 대시보드

```bash
python -m streamlit run dashboard/app.py
```

브라우저에서 http://localhost:8501 접속

---

## 대시보드 기능

| 탭 | 기능 |
|----|------|
| 🤖 자연어 검색 | 자유 텍스트 입력 → TF-IDF 코사인 유사도 랭킹 |
| 🔎 필터 검색 | 출처 / 근무지 / 경력 / 기술 스택 조합 필터 |
| 📊 통계 | 출처별·키워드별·기술스택별·경력분포 차트 |

**임베딩 방식 선택** (사이드바):
- `tfidf` — 기본, 설치 불필요
- `local` — 다국어 sentence-transformers (~120MB 자동 다운로드)
- `bedrock` — AWS Bedrock Titan (`.env`에 AWS 자격증명 필요)
- `openai` — OpenAI text-embedding-3 (`.env`에 `OPENAI_API_KEY` 필요)

---

## 환경 변수 설정 (선택)

`.env.example`을 `.env`로 복사 후 필요한 값 입력:

```bash
copy .env.example .env
```

| 변수 | 설명 |
|------|------|
| `SARAMIN_API_KEY` | 사람인 Open API 키 (없으면 HTML 크롤링으로 폴백) |
| `CHROME_BIN` | Chrome 실행파일 경로 (자동 감지 실패 시) |
| `OPENAI_API_KEY` | OpenAI 임베딩 사용 시 |
| `AWS_REGION` | Bedrock 임베딩 사용 시 (기본: us-east-1) |

---

## 스크래퍼 테스트

```bash
# 전체 테스트 (MAX_PAGES=1로 빠르게)
python test_scrapers.py

# 특정 사이트만
python test_scrapers.py --sites 원티드 점핏 쿠팡
```

---

## 주의사항

- 각 사이트의 이용약관을 준수하세요.
- `--workers` 값을 낮게 유지하세요 (기본 3). Selenium 사이트는 1~2 권장.
- 사이트 구조 변경 시 셀렉터 수정이 필요할 수 있습니다.
- 로그는 `output/scraper.log`에 저장됩니다.
