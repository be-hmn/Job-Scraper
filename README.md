# IT/보안 채용 공고 통합 스크래퍼

국내 주요 채용 사이트에서 IT·보안 관련 공고를 수집해 CSV로 저장합니다.

## 지원 사이트

| 사이트 | 방식 | 비고 |
|--------|------|------|
| 사람인 | Open API / HTML 크롤링 | API 키 있으면 API 우선 사용 |
| 잡코리아 | HTML 크롤링 | IT개발·보안 카테고리 |
| 원티드 | 내부 JSON API | 개발·보안 직군 |
| 점핏 | 내부 JSON API | 사람인 계열 IT 특화 |
| 프로그래머스 | 내부 JSON API | 개발자 특화 |
| 로켓펀치 | 내부 JSON API | 스타트업 특화 |
| 인크루트 | HTML 크롤링 | 키워드 검색 |
| 잡플래닛 | 내부 JSON API | 기업 리뷰 연동 |

## 설치

```bash
cd Job_Scraper
pip install -r requirements.txt
```

## 사용법

### 전체 사이트 수집 (기본)
```bash
python main.py
```

### 특정 사이트만 수집
```bash
python main.py --sites 사람인 원티드 점핏
```

### 출력 파일명 지정
```bash
python main.py --output my_jobs.csv
```

### 중복 제거 없이 저장
```bash
python main.py --no-dedup
```

### 동시 실행 수 조정 (기본 3)
```bash
python main.py --workers 2
```

## 사람인 Open API 키 설정 (선택)

API 키가 있으면 더 많은 데이터를 안정적으로 수집할 수 있습니다.

1. https://oapi.saramin.co.kr 에서 API 키 발급
2. `.env.example`을 `.env`로 복사
3. `SARAMIN_API_KEY=발급받은키` 입력

```bash
copy .env.example .env
# .env 파일을 열어 API 키 입력
```

## 출력 파일

`output/` 폴더에 CSV 파일이 생성됩니다.

| 컬럼 | 설명 |
|------|------|
| 공고제목 | 채용 공고 제목 |
| 회사명 | 채용 기업명 |
| 근무지 | 근무 위치 |
| 경력 | 경력 조건 |
| 마감일 | 지원 마감일 |
| 공고URL | 원본 공고 링크 |
| 출처 | 수집 사이트명 |
| 검색키워드 | 사용된 검색어/카테고리 |

## 주의사항

- 각 사이트의 이용약관을 준수하세요.
- 과도한 요청은 IP 차단으로 이어질 수 있습니다. `--workers` 값을 낮게 유지하세요.
- 사이트 HTML 구조가 변경되면 셀렉터 수정이 필요할 수 있습니다.
- 일부 사이트(잡코리아, 인크루트)는 로그인 없이 접근 가능한 공고만 수집됩니다.
