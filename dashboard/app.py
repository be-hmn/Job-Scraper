"""
IT/보안 채용 공고 대시보드
실행: python -m streamlit run dashboard/app.py
"""

import ast
import os
import sys
from collections import Counter
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dashboard.search_engine import JobSearchEngine, load_csv, list_csv_files

# ── 페이지 설정 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="IT/보안 채용 대시보드",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────
st.markdown("""
<style>
.job-card {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 12px;
}
.job-title   { font-size: 1.05rem; font-weight: 700; color: #cdd6f4; }
.job-company { color: #89b4fa; font-size: 0.9rem; margin-top: 4px; }
.job-meta    { color: #a6adc8; font-size: 0.82rem; margin-top: 6px; }
.badge {
    display: inline-block; padding: 2px 8px;
    border-radius: 12px; font-size: 0.75rem; margin-right: 4px;
}
.badge-source { background:#313244; color:#cba6f7; }
.badge-exp    { background:#313244; color:#a6e3a1; }
.badge-loc    { background:#313244; color:#fab387; }
.badge-score  { background:#1e3a5f; color:#89dceb; }
.badge-tech   { background:#2a2a3e; color:#f9e2af; }
.score-bar  { height:4px; border-radius:2px; background:#313244; margin-top:8px; }
.score-fill { height:4px; border-radius:2px;
              background:linear-gradient(90deg,#89b4fa,#cba6f7); }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ════════════════════════════════════════════════════════════════

def _clean(val) -> str:
    import math
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _load_from_db() -> Optional[pd.DataFrame]:
    db_path = os.path.join(ROOT, "output", "job_database.db")
    if not os.path.exists(db_path):
        return None
    try:
        from database import query_jobs
        df = query_jobs(db_path=db_path)
        df = df.rename(columns={
            "title":    "공고제목",
            "company":  "회사명",
            "location": "근무지",
            "deadline": "마감일",
            "link":     "공고URL",
            "source":   "출처",
            "keyword":  "검색키워드",
        })
        if "경력" not in df.columns:
            df["경력"] = ""
        return df
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("DB 로드 실패: %s", e)
        return None


def render_job_cards(df: pd.DataFrame, show_score: bool = False):
    if df.empty:
        st.info("조건에 맞는 공고가 없습니다. 필터를 조정해보세요.")
        return

    for _, row in df.iterrows():
        title    = _clean(row.get("공고제목", ""))
        company  = _clean(row.get("회사명", ""))
        source   = _clean(row.get("출처", ""))
        loc      = _clean(row.get("근무지", ""))
        exp      = _clean(row.get("경력", "")) or "미기재"
        deadline = _clean(row.get("마감일", ""))
        url      = _clean(row.get("공고URL", ""))

        tech_list = row.get("tech_stack", [])
        if isinstance(tech_list, str):
            try:
                tech_list = ast.literal_eval(tech_list)
            except Exception:
                tech_list = []
        tech_badges = "".join(
            f'<span class="badge badge-tech">{t}</span>'
            for t in (tech_list[:5] if isinstance(tech_list, list) else [])
        )

        deadline_part = f'&nbsp;📅 {deadline}' if deadline else ""
        link_part = (
            f'<a href="{url}" target="_blank" '
            f'style="color:#89b4fa;font-size:0.82rem;">🔗 공고 보기</a>'
        ) if url else ""

        score_part = ""
        if show_score and "유사도" in row.index:
            score = float(row["유사도"])
            width = min(score, 100)
            score_part = (
                f'<span class="badge badge-score">유사도 {score:.1f}%</span>'
                f'<div class="score-bar">'
                f'<div class="score-fill" style="width:{width:.1f}%"></div>'
                f'</div>'
            )

        st.markdown(
            '<div class="job-card">'
            f'<div class="job-title">{title}</div>'
            f'<div class="job-company">🏢 {company}</div>'
            '<div class="job-meta">'
            f'<span class="badge badge-source">{source}</span>'
            f'<span class="badge badge-loc">📍 {loc}</span>'
            f'<span class="badge badge-exp">💼 {exp}</span>'
            f'{deadline_part}'
            '</div>'
            f'{tech_badges}'
            f'{score_part}'
            f'<div style="margin-top:8px">{link_part}</div>'
            '</div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════
# 데이터 로드 (캐시)
# ════════════════════════════════════════════════════════════════

@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    return load_csv(path)


@st.cache_resource
def get_engine(path: str, embedder_type: str, _df: Optional[pd.DataFrame] = None) -> JobSearchEngine:
    df = _df if path == "__db__" and _df is not None else load_data(path)
    return JobSearchEngine(df, embedder_type=embedder_type)


# ════════════════════════════════════════════════════════════════
# 사이드바 — 데이터 소스 + 임베딩 방식만
# ════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("🔐 채용 대시보드")
    st.divider()

    # 데이터 소스
    db_df  = _load_from_db()
    has_db = db_df is not None and not db_df.empty

    if has_db:
        df_raw        = db_df
        selected_file = "__db__"
        st.success(f"🗄️ DB: {len(df_raw):,}건")
        is_cleaned = True
    else:
        st.warning("DB 없음. `python main.py` 실행 필요", icon="⚠️")
        csv_files = list_csv_files(os.path.join(ROOT, "output"))
        if not csv_files:
            st.error("데이터가 없습니다.")
            st.stop()
        selected_file = st.selectbox(
            "📂 CSV 파일",
            csv_files,
            format_func=lambda x: os.path.basename(x),
        )
        df_raw     = load_data(selected_file)
        is_cleaned = "uid" in df_raw.columns

    st.divider()

    # 임베딩 방식
    st.markdown("**🧠 임베딩 방식**")
    embedder_type = st.radio(
        "임베딩",
        ["tfidf", "local", "bedrock", "openai"],
        captions=["빠름 · 기본", "다국어 로컬", "AWS Bedrock", "OpenAI"],
        label_visibility="collapsed",
    )
    if embedder_type == "local":
        st.info("`pip install sentence-transformers`", icon="ℹ️")
    elif embedder_type == "bedrock":
        st.info("AWS 자격증명 필요", icon="ℹ️")
    elif embedder_type == "openai":
        st.info("`OPENAI_API_KEY` 필요", icon="ℹ️")

    st.divider()

    # LLM 상태 표시
    st.markdown("**🤖 쿼리 확장 LLM**")
    if os.getenv("GEMINI_API_KEY"):
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        st.success(f"Gemini ({model})", icon="✅")
    elif os.getenv("OPENAI_API_KEY"):
        st.success("OpenAI GPT", icon="✅")
    elif os.getenv("AWS_ACCESS_KEY_ID"):
        st.success("AWS Bedrock", icon="✅")
    else:
        st.warning("규칙 기반 폴백\n`.env`에 `GEMINI_API_KEY` 설정 권장", icon="⚠️")


# ════════════════════════════════════════════════════════════════
# 엔진 초기화
# ════════════════════════════════════════════════════════════════

if selected_file == "__db__":
    engine = get_engine("__db__", embedder_type, _df=df_raw)
else:
    engine = get_engine(selected_file, embedder_type)

stats = engine.stats()

# 필터 옵션 사전 계산
_sources_all = sorted(df_raw["출처"].dropna().unique())
_locations_all = (
    df_raw["근무지"].fillna("")
    .str.split(r"[,\s]+")
    .explode()
    .str.strip()
    .loc[lambda s: s.str.len() > 0]
    .value_counts()
    .head(20)
    .index.tolist()
)
_top_techs = []
if is_cleaned and "tech_stack" in df_raw.columns:
    _all_techs: Counter = Counter()
    df_raw["tech_stack"].dropna().apply(
        lambda x: _all_techs.update(
            ast.literal_eval(x) if isinstance(x, str) else x
        ) if x else None
    )
    _top_techs = [t for t, _ in _all_techs.most_common(30)]


# ════════════════════════════════════════════════════════════════
# 탭
# ════════════════════════════════════════════════════════════════

tab_search, tab_stats = st.tabs(["🔍 검색", "📊 통계"])


# ════════════════════════════════════════════════════════════════
# 탭 1: 검색 (자연어 + 필터 한 화면)
# ════════════════════════════════════════════════════════════════

with tab_search:

    # ── 검색창 ──────────────────────────────────────────────────
    st.markdown("### 원하는 포지션을 자유롭게 입력하세요")

    EXAMPLES = [
        "정보보안 관련 최신 문제를 해결해보는 경험을 해보고 싶어",
        "클라우드 인프라를 직접 설계하고 운영해보고 싶어",
        "AI 모델을 실제 서비스에 배포하는 일을 하고 싶어",
        "신입으로 백엔드 개발을 시작하고 싶어",
        "모의해킹이나 취약점 분석 업무를 해보고 싶어",
    ]

    ex_cols = st.columns(len(EXAMPLES))
    if "query_text" not in st.session_state:
        st.session_state.query_text = ""

    for i, ex in enumerate(EXAMPLES):
        if ex_cols[i].button(ex[:14] + "…", key=f"ex_{i}", use_container_width=True):
            st.session_state.query_text = ex
            st.rerun()

    query = st.text_area(
        "검색 쿼리",
        value=st.session_state.query_text,
        height=80,
        placeholder="예: 정보보안 관련 경험을 쌓고 싶어 / 신입 백엔드 개발자로 시작하고 싶어",
        label_visibility="collapsed",
    )

    # ── 필터 (메인 화면) ─────────────────────────────────────────
    with st.expander("🔍 필터 설정", expanded=False):
        fc1, fc2, fc3 = st.columns(3)

        with fc1:
            sources = st.multiselect(
                "출처 사이트",
                _sources_all,
                default=[],
                key="f_sources",
            )
            experience = st.selectbox(
                "경력",
                ["전체", "신입 (경력무관 포함)", "1~3년", "3~5년", "5년 이상"],
                key="f_exp",
            )
            intern_only = st.checkbox("인턴 공고만 보기", key="f_intern")

        with fc2:
            locations = st.multiselect(
                "근무지",
                _locations_all,
                default=[],
                key="f_loc",
            )

        with fc3:
            tech_filter = []
            if _top_techs:
                tech_filter = st.multiselect(
                    "🛠 기술 스택",
                    _top_techs,
                    default=[],
                    key="f_tech",
                )

    # 경력 필터 값 정규화 (UI 표시명 → 내부 값)
    _exp_map = {
        "전체": "전체",
        "신입 (경력무관 포함)": "신입",
        "1~3년": "1~3년",
        "3~5년": "3~5년",
        "5년 이상": "5년 이상",
    }
    experience_val = _exp_map.get(experience, "전체")

    # ── 검색 버튼 ────────────────────────────────────────────────
    if st.button("🔍 검색", type="primary", use_container_width=True, key="search_btn"):
        if not query.strip():
            st.warning("검색어를 입력해주세요.")
        else:
            with st.spinner("검색 중..."):
                results, params = engine.expanded_search(
                    query=query,
                    sources=sources if sources else None,
                    locations=locations if locations else None,
                    experience=experience_val,
                    tech_stack=tech_filter if tech_filter else None,
                    intern_only=intern_only,
                )

            # LLM 확장 정보 표시
            provider = params.get("provider", "rules")
            summary  = params.get("summary", "")
            with st.expander(f"🤖 검색 의도 분석 — {summary}", expanded=False):
                st.markdown(f"**확장 쿼리:** `{params.get('search_query', '')[:120]}`")
                st.caption(f"제공: {provider}")

            st.success(f"**{len(results)}개** 공고를 찾았습니다.")
            render_job_cards(results, show_score=True)


# ════════════════════════════════════════════════════════════════
# 탭 2: 통계
# ════════════════════════════════════════════════════════════════

with tab_stats:
    st.markdown("### 📊 수집 데이터 통계")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 공고 수",       f"{stats['total']:,}건")
    m2.metric("수집 사이트",      f"{len(stats['by_source'])}개")
    m3.metric("마감일 있는 공고", f"{stats['deadline_soon']}건")
    m4.metric("근무지 종류",      f"{len(stats['by_location'])}개")

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**출처별 공고 수**")
        src_df = pd.DataFrame(
            stats["by_source"].items(), columns=["출처", "건수"]
        ).sort_values("건수", ascending=True)
        fig1 = px.bar(
            src_df, x="건수", y="출처", orientation="h",
            color="건수", color_continuous_scale="Blues",
            template="plotly_dark",
        )
        fig1.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig1, use_container_width=True)

        direct_sources = {"카카오", "네이버", "토스", "쿠팡"}
        raw = stats.get("by_source_raw", {})
        direct_detail = {k: v for k, v in raw.items() if k in direct_sources}
        if direct_detail:
            with st.expander("개별 공고 세부 내역"):
                detail_df = pd.DataFrame(
                    direct_detail.items(), columns=["기업", "건수"]
                ).sort_values("건수", ascending=False)
                st.dataframe(detail_df, hide_index=True, use_container_width=True)

    with col2:
        st.markdown("**검색 키워드별 공고 수**")
        kw_df = pd.DataFrame(
            stats["by_keyword"].items(), columns=["키워드", "건수"]
        ).sort_values("건수", ascending=True)
        fig2 = px.bar(
            kw_df, x="건수", y="키워드", orientation="h",
            color="건수", color_continuous_scale="Purples",
            template="plotly_dark",
        )
        fig2.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig2, use_container_width=True)

    if "top_tech" in stats and stats["top_tech"]:
        st.markdown("**🛠 기술 스택 TOP 15**")
        tech_df = pd.DataFrame(
            stats["top_tech"].items(), columns=["기술", "건수"]
        ).sort_values("건수", ascending=True)
        fig_tech = px.bar(
            tech_df, x="건수", y="기술", orientation="h",
            color="건수", color_continuous_scale="Greens",
            template="plotly_dark",
        )
        fig_tech.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_tech, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**근무지 TOP 10**")
        loc_df = pd.DataFrame(
            stats["by_location"].items(), columns=["근무지", "건수"]
        )
        fig3 = px.pie(
            loc_df, names="근무지", values="건수",
            template="plotly_dark", hole=0.4,
        )
        fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        if "exp_dist" in stats and stats["exp_dist"]:
            st.markdown("**💼 경력 분포**")
            exp_df = pd.DataFrame(
                [(str(k) + "년", v) for k, v in sorted(stats["exp_dist"].items())
                 if k is not None and k >= 0],
                columns=["경력", "건수"],
            )
            if not exp_df.empty:
                fig4 = px.bar(
                    exp_df, x="경력", y="건수",
                    color="건수", color_continuous_scale="Oranges",
                    template="plotly_dark",
                )
                fig4.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig4, use_container_width=True)

    st.divider()
    st.markdown("**전체 데이터 테이블**")
    display_cols = [c for c in df_raw.columns if c not in ("_search_text", "uid")]
    st.dataframe(
        df_raw[display_cols],
        use_container_width=True,
        column_config={"공고URL": st.column_config.LinkColumn("공고URL")},
        hide_index=True,
    )
