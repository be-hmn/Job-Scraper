"""
IT/보안 채용 공고 대시보드
실행: python -m streamlit run dashboard/app.py
"""

import os
import sys
import pandas as pd
import streamlit as st
import plotly.express as px

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


# ── NaN 정규화 헬퍼 ──────────────────────────────────────────────
def _clean(val) -> str:
    import math
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


# ── 공고 카드 렌더링 ─────────────────────────────────────────────
def render_job_cards(df: pd.DataFrame, show_score: bool = False):
    if df.empty:
        st.info("조건에 맞는 공고가 없습니다. 필터를 완화해보세요.")
        return

    for _, row in df.iterrows():
        title    = _clean(row.get("공고제목", ""))
        company  = _clean(row.get("회사명", ""))
        source   = _clean(row.get("출처", ""))
        loc      = _clean(row.get("근무지", ""))
        exp      = _clean(row.get("경력", "")) or "미기재"
        deadline = _clean(row.get("마감일", ""))
        url      = _clean(row.get("공고URL", ""))

        # 기술 스택 배지 (파이프라인 처리 후)
        tech_list = row.get("tech_stack", [])
        if isinstance(tech_list, str):
            import ast
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

        card = (
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
            '</div>'
        )
        st.markdown(card, unsafe_allow_html=True)


# ── 데이터 로드 (캐시) ───────────────────────────────────────────
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    return load_csv(path)


@st.cache_resource
def get_engine(path: str, embedder_type: str) -> JobSearchEngine:
    df = load_data(path)
    return JobSearchEngine(df, embedder_type=embedder_type)


# ── 사이드바 ─────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔐 채용 대시보드")
    st.divider()

    # CSV 파일 선택
    csv_files = list_csv_files(os.path.join(ROOT, "output"))
    if not csv_files:
        st.error("output/ 폴더에 CSV 파일이 없습니다.\n먼저 `python main.py`를 실행하세요.")
        st.stop()

    selected_file = st.selectbox(
        "📂 데이터 파일",
        csv_files,
        format_func=lambda x: os.path.basename(x),
    )

    # 파이프라인 처리 여부 표시
    df_raw = load_data(selected_file)
    is_cleaned = "uid" in df_raw.columns
    if is_cleaned:
        st.success("✅ 파이프라인 처리 완료 (Fuzzy 중복제거 · 기술스택 추출)", icon="🧹")
    else:
        st.info("💡 `python pipeline.py` 실행 시 Fuzzy 중복제거 및 기술스택 추출이 적용됩니다.", icon="ℹ️")

    st.divider()

    # 검색 엔진 선택
    st.markdown("**🧠 검색 엔진**")
    embedder_type = st.radio(
        "임베딩 방식",
        ["tfidf", "local", "bedrock", "openai"],
        captions=[
            "빠름 · 설치 불필요 (기본)",
            "다국어 로컬 모델 (~120MB)",
            "AWS Bedrock Titan",
            "OpenAI text-embedding-3",
        ],
        label_visibility="collapsed",
    )
    if embedder_type in ("bedrock", "openai"):
        st.info("`.env`에 API 키를 설정하세요.", icon="ℹ️")

    st.divider()

    # 필터
    st.markdown("**🔍 필터**")

    sources = st.multiselect(
        "출처 사이트",
        sorted(df_raw["출처"].dropna().unique()),
        default=[],
    )

    locations_all = (
        df_raw["근무지"].fillna("")
        .str.split(r"[,\s]+")
        .explode()
        .str.strip()
        .loc[lambda s: s.str.len() > 0]
        .value_counts()
        .head(20)
        .index.tolist()
    )
    locations = st.multiselect("근무지", locations_all, default=[])

    experience = st.selectbox(
        "경력",
        ["전체", "신입", "1~3년", "3~5년", "5년 이상"],
    )

    # 기술 스택 필터 (파이프라인 처리 후에만 표시)
    tech_filter = []
    if is_cleaned and "tech_stack" in df_raw.columns:
        from collections import Counter
        import ast as _ast
        all_techs: Counter = Counter()
        df_raw["tech_stack"].dropna().apply(
            lambda x: all_techs.update(
                _ast.literal_eval(x) if isinstance(x, str) else x
            ) if x else None
        )
        top_techs = [t for t, _ in all_techs.most_common(30)]
        if top_techs:
            tech_filter = st.multiselect("🛠 기술 스택", top_techs, default=[])

    st.divider()
    top_k = st.slider("최대 결과 수", 5, 100, 20, 5)


# ── 엔진 & 통계 ──────────────────────────────────────────────────
engine = get_engine(selected_file, embedder_type)
stats  = engine.stats()


# ── 탭 ───────────────────────────────────────────────────────────
tab_search, tab_filter, tab_stats = st.tabs(
    ["🤖 자연어 검색", "🔎 필터 검색", "📊 통계"]
)


# ════════════════════════════════════════════════════════════════
# 탭 1: 자연어 검색
# ════════════════════════════════════════════════════════════════
with tab_search:
    st.markdown("### 🤖 자연어로 채용 공고 찾기")
    st.caption(
        "원하는 경험이나 관심사를 자유롭게 입력하세요.  "
        "예: *정보보안 관련 최신 문제를 해결해보는 경험을 해보고 싶어*"
    )

    EXAMPLES = [
        "정보보안 관련 최신 문제를 해결해보는 경험을 해보고 싶어",
        "클라우드 인프라를 직접 설계하고 운영해보고 싶어",
        "AI 모델을 실제 서비스에 배포하는 일을 하고 싶어",
        "신입으로 백엔드 개발을 시작하고 싶어",
        "모의해킹이나 취약점 분석 업무를 해보고 싶어",
    ]

    st.markdown("**💡 예시 쿼리**")
    ex_cols = st.columns(len(EXAMPLES))

    if "query_text" not in st.session_state:
        st.session_state.query_text = ""

    for i, ex in enumerate(EXAMPLES):
        if ex_cols[i].button(ex[:16] + "…", key=f"ex_{i}", use_container_width=True):
            st.session_state.query_text = ex
            st.rerun()

    query = st.text_area(
        "검색 쿼리",
        value=st.session_state.query_text,
        height=80,
        placeholder="원하는 업무 경험, 기술 스택, 관심 분야를 자유롭게 입력하세요...",
        label_visibility="collapsed",
    )

    use_filter = st.checkbox(
        "사이드바 필터와 함께 사용 (하이브리드 검색)", value=True
    )

    if st.button("🔍 검색", type="primary", use_container_width=True, key="semantic_btn"):
        if not query.strip():
            st.warning("검색어를 입력해주세요.")
        else:
            with st.spinner("유사한 공고를 찾는 중..."):
                if use_filter:
                    results = engine.hybrid_search(
                        query=query,
                        sources=sources if sources else None,
                        locations=locations if locations else None,
                        experience=experience,
                        tech_stack=tech_filter if tech_filter else None,
                        top_k=top_k,
                    )
                else:
                    results = engine.semantic_search(query, top_k=top_k)

            st.success(f"**{len(results)}개** 공고를 찾았습니다.")
            render_job_cards(results, show_score=True)


# ════════════════════════════════════════════════════════════════
# 탭 2: 필터 검색
# ════════════════════════════════════════════════════════════════
with tab_filter:
    st.markdown("### 🔎 조건으로 공고 찾기")

    kw = st.text_input(
        "키워드 검색",
        placeholder="예: 보안, DevOps, 토스, 서울...",
        key="filter_kw",
    )

    if st.button("검색", type="primary", key="filter_btn", use_container_width=True):
        results_f = engine.filter_search(
            keyword=kw,
            sources=sources if sources else None,
            locations=locations if locations else None,
            experience=experience,
            tech_stack=tech_filter if tech_filter else None,
        )
        st.success(f"**{len(results_f)}개** 공고를 찾았습니다.")
        render_job_cards(results_f.head(top_k), show_score=False)
    else:
        default_f = engine.filter_search(
            keyword=kw,
            sources=sources if sources else None,
            locations=locations if locations else None,
            experience=experience,
            tech_stack=tech_filter if tech_filter else None,
        )
        st.caption(f"전체 {len(default_f)}개 공고 (최대 {top_k}개 표시)")
        render_job_cards(default_f.head(top_k), show_score=False)


# ════════════════════════════════════════════════════════════════
# 탭 3: 통계
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

    # 기술 스택 TOP 15 (파이프라인 처리 후)
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

    # 경력 분포 (파이프라인 처리 후)
    with col4:
        if "exp_dist" in stats and stats["exp_dist"]:
            st.markdown("**💼 경력 분포 (min_exp 기준)**")
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
    display_df = df_raw[display_cols]
    st.dataframe(
        display_df,
        use_container_width=True,
        column_config={
            "공고URL": st.column_config.LinkColumn("공고URL"),
        },
        hide_index=True,
    )
