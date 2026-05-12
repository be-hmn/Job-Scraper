"""
SQLite 데이터베이스 엔진
========================
파일: output/job_database.db

테이블: postings
  uid         TEXT PRIMARY KEY  — 회사명+제목+링크 SHA-256
  title       TEXT              — 공고 제목
  company     TEXT              — 회사명
  description TEXT              — 검색용 통합 텍스트 (_search_text)
  link        TEXT              — 공고 URL
  location    TEXT              — 근무지
  source      TEXT              — 출처 사이트
  keyword     TEXT              — 검색 키워드
  deadline    TEXT              — 마감일
  min_exp     INTEGER           — 최소 경력 (신입=0, 무관=-1, 미기재=NULL)
  max_exp     INTEGER           — 최대 경력
  tech_stack  TEXT              — 기술 스택 (JSON 배열)
  posted_date TEXT              — 수집 일시 (ISO 8601)
  updated_at  TEXT              — 마지막 업데이트 일시

Upsert 전략:
  - 동일 uid 유입 시 기존 데이터 유지 (INSERT OR IGNORE)
  - 마감일(deadline)만 최신값으로 갱신
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# __file__ 기반 절대 경로 — 어느 디렉터리에서 실행해도 동일하게 동작
# database.py는 프로젝트 루트에 위치하므로 dirname(__file__)이 곧 루트
_ROOT   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_ROOT, "output", "job_database.db")

# ── DDL ──────────────────────────────────────────────────────────
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS postings (
    uid         TEXT    PRIMARY KEY,
    title       TEXT    NOT NULL,
    company     TEXT,
    description TEXT,
    link        TEXT,
    location    TEXT,
    source      TEXT,
    keyword     TEXT,
    deadline    TEXT,
    min_exp     INTEGER,
    max_exp     INTEGER,
    tech_stack  TEXT,
    posted_date TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

_CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_source   ON postings(source);",
    "CREATE INDEX IF NOT EXISTS idx_location ON postings(location);",
    "CREATE INDEX IF NOT EXISTS idx_min_exp  ON postings(min_exp);",
    "CREATE INDEX IF NOT EXISTS idx_deadline ON postings(deadline);",
]


# ════════════════════════════════════════════════════════════════
# 연결 관리
# ════════════════════════════════════════════════════════════════

@contextmanager
def get_connection(db_path: str = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """SQLite 연결 컨텍스트 매니저"""
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 컬럼명으로 접근 가능
    conn.execute("PRAGMA journal_mode=WAL;")   # 동시 읽기 성능 향상
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════
# 초기화
# ════════════════════════════════════════════════════════════════

def init_db(db_path: str = DB_PATH) -> None:
    """DB 파일 및 테이블 초기화 (없으면 생성, 있으면 유지)"""
    with get_connection(db_path) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        for idx_sql in _CREATE_INDEX_SQL:
            conn.execute(idx_sql)
    logger.info("DB 초기화 완료: %s", db_path)


# ════════════════════════════════════════════════════════════════
# DataFrame → DB 변환 헬퍼
# ════════════════════════════════════════════════════════════════

def _row_to_record(row: pd.Series, now: str) -> dict:
    """DataFrame 행을 DB 레코드 dict로 변환"""
    # tech_stack: 리스트 → JSON 문자열
    tech = row.get("tech_stack", [])
    if isinstance(tech, list):
        tech_json = json.dumps(tech, ensure_ascii=False)
    elif isinstance(tech, str) and tech.startswith("["):
        tech_json = tech  # 이미 JSON 문자열
    else:
        tech_json = "[]"

    # min_exp / max_exp: pandas Int64 → Python int or None
    def _to_int(val) -> Optional[int]:
        try:
            return None if pd.isna(val) else int(val)
        except (TypeError, ValueError):
            return None

    return {
        "uid":         str(row.get("uid", "") or ""),
        "title":       str(row.get("공고제목", "") or ""),
        "company":     str(row.get("회사명", "") or ""),
        "description": str(row.get("_search_text", "") or ""),
        "link":        str(row.get("공고URL", "") or ""),
        "location":    str(row.get("근무지", "") or ""),
        "source":      str(row.get("출처", "") or ""),
        "keyword":     str(row.get("검색키워드", "") or ""),
        "deadline":    str(row.get("마감일", "") or ""),
        "min_exp":     _to_int(row.get("min_exp")),
        "max_exp":     _to_int(row.get("max_exp")),
        "tech_stack":  tech_json,
        "posted_date": now,
        "updated_at":  now,
    }


# ════════════════════════════════════════════════════════════════
# Upsert
# ════════════════════════════════════════════════════════════════

_INSERT_OR_IGNORE_SQL = """
INSERT OR IGNORE INTO postings
    (uid, title, company, description, link, location, source, keyword,
     deadline, min_exp, max_exp, tech_stack, posted_date, updated_at)
VALUES
    (:uid, :title, :company, :description, :link, :location, :source, :keyword,
     :deadline, :min_exp, :max_exp, :tech_stack, :posted_date, :updated_at);
"""

_UPDATE_DEADLINE_SQL = """
UPDATE postings
SET    deadline   = :deadline,
       updated_at = :updated_at
WHERE  uid = :uid
  AND  (deadline IS NULL OR deadline = '' OR deadline < :deadline);
"""


def upsert_jobs(df: pd.DataFrame, db_path: str = DB_PATH) -> tuple[int, int]:
    """
    DataFrame의 공고를 DB에 Upsert한다.

    전략:
    - 신규 uid → INSERT (posted_date 기록)
    - 기존 uid → 마감일이 더 최신이면 deadline + updated_at만 갱신

    반환값: (inserted_count, updated_count)
    """
    if df.empty:
        return 0, 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = [_row_to_record(row, now) for _, row in df.iterrows()]

    # uid 없는 레코드 제외
    records = [r for r in records if r["uid"]]

    inserted = updated = skipped = 0

    with get_connection(db_path) as conn:
        for rec in records:
            cursor = conn.execute(_INSERT_OR_IGNORE_SQL, rec)
            if cursor.rowcount > 0:
                inserted += 1
            else:
                # 기존 레코드 — 마감일만 갱신 시도
                cursor2 = conn.execute(_UPDATE_DEADLINE_SQL, rec)
                if cursor2.rowcount > 0:
                    updated += 1
                else:
                    skipped += 1

    logger.info(
        "DB Upsert 완료 [%s]: 신규 %d건 / 마감일 갱신 %d건 / 변경없음 %d건 (총 처리 %d건)",
        os.path.basename(db_path), inserted, updated, skipped, len(records),
    )
    return inserted, updated


# ════════════════════════════════════════════════════════════════
# 조회
# ════════════════════════════════════════════════════════════════

def query_jobs(
    db_path: str = DB_PATH,
    sources: Optional[List[str]] = None,
    location: Optional[str] = None,
    min_exp: Optional[int] = None,
    max_exp: Optional[int] = None,
    keyword: Optional[str] = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """
    SQL 필터로 공고를 조회하여 DataFrame으로 반환한다.
    search_engine.py의 하이브리드 검색에서 1차 필터링에 사용.
    """
    conditions: List[str] = []
    params: List = []

    if sources:
        placeholders = ",".join("?" * len(sources))
        conditions.append(f"source IN ({placeholders})")
        params.extend(sources)

    if location:
        conditions.append("location LIKE ?")
        params.append(f"%{location}%")

    if min_exp is not None:
        conditions.append("(min_exp IS NULL OR min_exp <= ?)")
        params.append(min_exp)

    if max_exp is not None:
        conditions.append("(max_exp IS NULL OR max_exp >= ?)")
        params.append(max_exp)

    if keyword:
        conditions.append("(title LIKE ? OR description LIKE ? OR company LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql   = f"SELECT * FROM postings {where} ORDER BY posted_date DESC LIMIT ?"
    params.append(limit)

    with get_connection(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    # tech_stack JSON → 리스트 복원
    if "tech_stack" in df.columns:
        df["tech_stack"] = df["tech_stack"].apply(_parse_tech_stack_json)

    return df


def _parse_tech_stack_json(val: str) -> list:
    """DB에서 읽은 tech_stack JSON 문자열을 리스트로 변환"""
    if not isinstance(val, str) or not val.strip():
        return []
    try:
        result = json.loads(val)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def count_jobs(db_path: str = DB_PATH) -> int:
    """DB 전체 공고 수 반환"""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM postings").fetchone()
        return row[0] if row else 0


def get_sources(db_path: str = DB_PATH) -> List[str]:
    """DB에 저장된 출처 목록 반환"""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT source FROM postings ORDER BY source"
        ).fetchall()
        return [r[0] for r in rows if r[0]]


def get_db_stats(db_path: str = DB_PATH) -> dict:
    """DB 통계 반환 (대시보드 통계 탭용)"""
    with get_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
        by_source = dict(conn.execute(
            "SELECT source, COUNT(*) FROM postings GROUP BY source ORDER BY COUNT(*) DESC"
        ).fetchall())
        intern_count = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE title LIKE '%인턴%' OR title LIKE '%intern%'"
        ).fetchone()[0]
        has_deadline = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE deadline IS NOT NULL AND deadline != ''"
        ).fetchone()[0]

    return {
        "total":        total,
        "by_source":    by_source,
        "intern_count": intern_count,
        "has_deadline": has_deadline,
    }
