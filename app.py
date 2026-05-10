"""
app.py — 주식정보 웹앱 (Streamlit, v0.6)

4탭 UI:
  - 관심종목: 그룹별 종목 + ← → 그룹 네비게이션 + 즉시 재분석 + 그룹 이동
  - 주식뉴스: 종목별 뉴스 통합 피드 + 🔄 뉴스만 새로받기 + 사용자 입력
  - 새 정보: 유튜브/URL/텍스트 → Claude 분석 → 보관/삭제 결정
  - 보관: 종목 보관 + 분석 정보 보관 (두 섹션)

v0.6 변경사항:
  - 새 정보 분석 결과에 [📦 보관] / [🗑️ 삭제] 명시적 버튼
  - 주식뉴스 탭에 [🔄 뉴스만 새로받기] 버튼 + 마지막 갱신 시간 + 자동 X 안내
  - 보관 탭에 "💬 보관 정보" 섹션 추가

실행:
    python -m streamlit run app.py
또는
    2_웹앱_띄우기.bat 더블클릭
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
REPORT_DIR = DATA_DIR / "reports"
WATCHLIST_PATH = PROJECT_ROOT / "watchlist.csv"
ARCHIVE_PATH = DATA_DIR / "archive.json"
MEMO_PATH = DATA_DIR / "memos.json"

st.set_page_config(
    page_title="주식정보",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",  # 폰 화면 공간 확보 (사이드바 기본 숨김)
)

# ─────────────────────────────────────────────────────────────────────
# 비밀번호 게이트 (배포 시에만 동작, 로컬에서는 패스)
# ─────────────────────────────────────────────────────────────────────
def _check_password() -> bool:
    """Streamlit secrets에 password 가 설정되어 있으면 입력 받음. 없으면 패스 (로컬)."""
    import hmac
    try:
        expected = st.secrets.get("password", None)
    except Exception:
        expected = None

    if not expected:
        return True  # 비밀번호 미설정 → 패스 (로컬 개발 모드)

    if st.session_state.get("password_ok"):
        return True

    st.markdown("### 🔐 주식정보 앱 로그인")
    pw = st.text_input("비밀번호", type="password", key="pw_input")
    if st.button("로그인", type="primary"):
        if hmac.compare_digest(pw, str(expected)):
            st.session_state.password_ok = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다")
    return False


if not _check_password():
    st.stop()

# ─── 자동 정리 (앱 시작 시 1일 1회만) ───
def _auto_cleanup_trash():
    """30일 이상 된 휴지통 항목 자동 영구삭제. 1일 1회만."""
    try:
        flag = DATA_DIR / "_last_cleanup.txt"
        now = datetime.now()
        if flag.exists():
            try:
                last = datetime.fromisoformat(flag.read_text().strip())
                if (now - last).total_seconds() < 86400:  # 24시간
                    return
            except Exception:
                pass
        from archive_manager import empty_trash_older_than as _et
        n = _et(30)
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(now.isoformat())
        if n > 0:
            print(f"[auto-cleanup] {n} old trash items deleted")
    except Exception as e:
        print(f"[auto-cleanup] skipped: {e}")

_auto_cleanup_trash()

# 신문 스타일 CSS + 전체 행 수평 정렬 + 모바일 최적화
st.markdown("""
<style>
/* ───── 모바일 최적화 (폰 화면 768px 이하) ───── */
@media (max-width: 768px) {
    /* 메인 컨테이너 — 가로 패딩 줄여서 화면 폭 최대 활용 */
    .main .block-container {
        padding: 0.6rem 0.4rem !important;
        max-width: 100% !important;
    }

    /* 헤더 작게 */
    h1 { font-size: 1.4rem !important; margin: 0.3rem 0 !important; }
    h2 { font-size: 1.15rem !important; margin: 0.6rem 0 0.4rem !important; }
    h3 { font-size: 1.0rem !important; margin: 0.4rem 0 0.3rem !important; }

    /* 탭 — 가로 스크롤 가능하게 */
    [data-testid="stTabs"] [role="tablist"] {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        scrollbar-width: thin;
    }
    [data-testid="stTabs"] button[role="tab"] {
        font-size: 0.85rem !important;
        padding: 0.4rem 0.5rem !important;
        white-space: nowrap !important;
    }

    /* 버튼 터치 친화적 */
    .stButton > button {
        min-height: 38px !important;
        padding: 0.4rem 0.5rem !important;
        font-size: 0.88rem !important;
    }

    /* 셀렉트박스/입력 */
    [data-baseweb="select"] {
        font-size: 0.88rem !important;
    }
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea {
        font-size: 0.9rem !important;
    }

    /* 캡션 작게 */
    [data-testid="stCaptionContainer"] {
        font-size: 0.78rem !important;
    }

    /* 마크다운 텍스트 */
    [data-testid="stMarkdownContainer"] p {
        font-size: 0.9rem !important;
        line-height: 1.45 !important;
    }

    /* 한 줄 컬럼 행 — 가로 유지 (스택 방지) */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.2rem !important;
        flex-direction: row !important;
    }

    /* 컬럼이 너무 좁아도 줄어들 수 있게 */
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        min-width: 0 !important;
        flex-shrink: 1 !important;
    }

    /* 모바일 버튼 — 글자 더 작게, 패딩 더 좁게 */
    .stButton > button {
        min-height: 36px !important;
        padding: 0.3rem 0.35rem !important;
        font-size: 0.78rem !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 1.1 !important;
    }

    /* 셀렉트박스도 작게 */
    [data-baseweb="select"] {
        font-size: 0.78rem !important;
        min-height: 36px !important;
    }
    [data-baseweb="select"] > div {
        min-height: 36px !important;
        padding: 0.2rem 0.35rem !important;
    }

    /* 사이드바 너비 줄이기 (열렸을 때) */
    [data-testid="stSidebar"] {
        min-width: 240px !important;
        max-width: 80vw !important;
    }

    /* 헤더 영역 압축 */
    [data-testid="stHeader"] {
        height: 2rem !important;
    }

    /* 캡션 — 모바일에서 더 작게, 줄바꿈 허용 */
    [data-testid="stCaptionContainer"] {
        font-size: 0.72rem !important;
        line-height: 1.3 !important;
    }

    /* 인풋 박스 압축 */
    [data-testid="stTextInput"] input {
        min-height: 36px !important;
        padding: 0.3rem 0.4rem !important;
    }

    /* popover 버튼도 작게 */
    [data-testid="stPopover"] button {
        min-height: 36px !important;
        font-size: 0.78rem !important;
        padding: 0.3rem 0.4rem !important;
    }

    /* 라디오/체크박스 */
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label {
        font-size: 0.82rem !important;
    }
}

/* ───── 모든 가로 컬럼 행: 세로 가운데 정렬 ───── */
[data-testid="stHorizontalBlock"] {
    align-items: center !important;
}

/* 컬럼 자체도 가운데 정렬 */
[data-testid="column"] {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

/* 체크박스 라벨 / 위쪽 패딩 제거 */
[data-testid="stCheckbox"] {
    margin-top: 0 !important;
    padding-top: 0 !important;
    display: flex;
    align-items: center;
}
[data-testid="stCheckbox"] > label {
    margin: 0 !important;
    padding: 0 !important;
}

/* 행 내 마크다운(텍스트)도 가운데 */
[data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p {
    margin-bottom: 0 !important;
    line-height: 1.5;
}

/* 버튼 안의 라벨도 정중앙 */
[data-testid="stHorizontalBlock"] button {
    margin: 0 !important;
}

/* 셀렉트박스도 다른 위젯과 일직선 */
[data-testid="stHorizontalBlock"] [data-testid="stSelectbox"] {
    margin-top: 0 !important;
    padding-top: 0 !important;
}

/* ───── 뉴스 한 줄 신문 스타일 ───── */
.news-row {
    font-family: 'Nanum Myeongjo', 'Noto Serif KR', 'Times New Roman', serif;
    font-size: 15px;
    line-height: 1.4;
    padding: 4px 0;
    border-bottom: 1px solid rgba(150,150,150,0.18);
}
.news-row a {
    color: #4a90e2;
    text-decoration: none;
    font-weight: 600;
}
.news-row a:hover { text-decoration: underline; }
.news-meta {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 12px;
    color: #888;
    margin-left: 8px;
}
.news-source {
    color: #666;
    font-size: 12px;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────
# 데이터 로드 / 저장
# ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_watchlist() -> pd.DataFrame:
    if not WATCHLIST_PATH.exists():
        return pd.DataFrame(columns=["group", "name", "ticker", "market", "is_etf", "note"])
    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": "", "is_etf": False, "note": ""})
    return df


def save_watchlist(df: pd.DataFrame):
    df.to_csv(WATCHLIST_PATH, index=False)
    st.cache_data.clear()


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_latest_report(ticker: str, name: str) -> Optional[Path]:
    if not REPORT_DIR.exists():
        return None
    candidates = sorted(REPORT_DIR.glob(f"{ticker}_{name}_*.md"), reverse=True)
    return candidates[0] if candidates else None


def strip_first_h1(text: str) -> str:
    """리포트 마크다운의 첫 H1 (종목명) 제거 — UI 헤더와 중복 제거용."""
    # 첫 # 헤더 + 그 다음 빈 줄까지 제거
    return re.sub(r"^#\s+[^\n]+\n+", "", text, count=1)


def clean_news_in_markdown(text: str) -> str:
    """리포트 마크다운에서 광고/스팸 뉴스 항목 필터링.
    'Keep에 저장' 같은 비-영향 뉴스는 표시 안 함.
    """
    try:
        from analyze_stock import _is_impactful_news
    except Exception:
        return text

    lines = text.split("\n")
    cleaned = []
    in_news = False
    counter = 1
    for line in lines:
        # 뉴스 섹션 시작 감지
        if "## 📰 최근 뉴스" in line or line.strip() == "## 최근 뉴스":
            in_news = True
            counter = 1
            cleaned.append(line)
            continue
        # 다음 섹션이나 구분선 → 뉴스 섹션 끝
        if in_news and (line.startswith("##") or line.startswith("---")):
            in_news = False

        if in_news:
            m = re.match(r"^(\s*)(\d+)\.\s+(.+)$", line)
            if m:
                rest = m.group(3)
                # 제목 추출: [제목](링크) 또는 그냥 제목
                title_match = re.match(r"\[([^\]]+)\]", rest)
                title = title_match.group(1) if title_match else rest.split("·")[0].split("—")[0].strip()
                if not _is_impactful_news(title):
                    continue
                # 번호 재매김
                line = f"{m.group(1)}{counter}. {rest}"
                counter += 1
        cleaned.append(line)
    return "\n".join(cleaned)


def extract_news_from_report(report_path: Path) -> list[dict]:
    if not report_path.exists():
        return []
    text = report_path.read_text(encoding="utf-8")
    m = re.search(r"## 📰 최근 뉴스\s*\n(.+?)(?=\n---|\n## |\Z)", text, re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    try:
        from analyze_stock import _is_impactful_news
    except Exception:
        _is_impactful_news = lambda t: True
    news = []
    for line in section.split("\n"):
        line = line.strip()
        m_link = re.match(r"^\d+\.\s*\[([^\]]+)\]\(([^)]+)\)", line)
        if m_link:
            title = m_link.group(1)
            if _is_impactful_news(title):
                news.append({"title": title, "link": m_link.group(2)})
            continue
        m_plain = re.match(r"^\d+\.\s+(.+)", line)
        if m_plain:
            title = m_plain.group(1)
            if _is_impactful_news(title):
                news.append({"title": title, "link": ""})
    return news


def extract_summary_from_report(report_path: Path) -> dict:
    if not report_path.exists():
        return {}
    text = report_path.read_text(encoding="utf-8")
    summary = {}
    m_price = re.search(r"\*\*([\d,]+)원\*\*\s*([▲▼])([\d,]+)원\s*\(([+-]?\d+\.\d+)%\)", text)
    if m_price:
        summary["price"] = m_price.group(1)
        summary["arrow"] = m_price.group(2)
        summary["change"] = m_price.group(3)
        summary["change_pct"] = float(m_price.group(4))
    for label, key in [(r"시가총액", "market_cap"), (r"PER \(실적\)", "per"),
                        (r"PBR", "pbr"), (r"배당수익률", "div")]:
        m = re.search(rf"\| {label} \| ([^\|]+) \|", text)
        if m:
            summary[key] = m.group(1).strip()
    return summary


# ─────────────────────────────────────────────────────────────────────
# Watchlist 변경
# ─────────────────────────────────────────────────────────────────────
def get_groups_for_ticker(df: pd.DataFrame, ticker: str) -> list[str]:
    rows = df[df["ticker"].astype(str).str.zfill(6) == ticker]
    return sorted(set(rows["group"].dropna().tolist()))


def add_to_group(ticker: str, name: str, target_group: str, market: str = "", is_etf: bool = False):
    df = load_watchlist()
    existing = df[(df["ticker"] == ticker) & (df["group"] == target_group)]
    if not existing.empty:
        return False
    new_row = pd.DataFrame([{
        "group": target_group,
        "name": name,
        "ticker": ticker,
        "market": market,
        "is_etf": is_etf,
        "note": "",
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_watchlist(df)
    return True


def remove_from_group(ticker: str, group: str):
    df = load_watchlist()
    df = df[~((df["ticker"] == ticker) & (df["group"] == group))]
    save_watchlist(df)


def move_to_group(ticker: str, name: str, source_group: str, target_group: str,
                  market: str = "", is_etf: bool = False):
    if source_group == target_group:
        return
    add_to_group(ticker, name, target_group, market, is_etf)
    remove_from_group(ticker, source_group)


# ─────────────────────────────────────────────────────────────────────
# 즉시 재분석
# ─────────────────────────────────────────────────────────────────────
def trigger_reanalysis(ticker: str, name: str, market: str):
    try:
        from analyze_stock import analyze_one
        with st.spinner(f"🤖 {name} 재분석 중... (30~60초)"):
            output_path = analyze_one(ticker, name, market, with_claude=True, verbose=False)
            return output_path is not None
    except Exception as e:
        st.error(f"분석 실패: {e}")
        return False


def trigger_news_refresh():
    """뉴스만 새로 받기 — Claude 호출 X, 비용 0원."""
    try:
        from news_cache import refresh_all_news
        progress_bar = st.progress(0.0, text="뉴스 수집 시작...")

        def _cb(idx, total, name):
            progress_bar.progress((idx + 1) / total, text=f"[{idx + 1}/{total}] {name} 뉴스 수집 중...")

        cache = refresh_all_news(progress_callback=_cb)
        progress_bar.empty()
        if "error" in cache:
            st.error(cache["error"])
            return False
        return True
    except Exception as e:
        st.error(f"뉴스 갱신 실패: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────
# 세션 상태
# ─────────────────────────────────────────────────────────────────────
if "archive" not in st.session_state:
    st.session_state.archive = load_json(ARCHIVE_PATH, [])
if "memos" not in st.session_state:
    st.session_state.memos = load_json(MEMO_PATH, {})
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = ""
if "selected_name" not in st.session_state:
    st.session_state.selected_name = ""
if "current_group_idx" not in st.session_state:
    st.session_state.current_group_idx = 0
if "last_analysis_result" not in st.session_state:
    st.session_state.last_analysis_result = None


def add_to_archive(ticker: str, name: str):
    if not any(a["ticker"] == ticker for a in st.session_state.archive):
        st.session_state.archive.append({
            "ticker": ticker,
            "name": name,
            "added_at": datetime.now().isoformat(),
        })
        save_json(ARCHIVE_PATH, st.session_state.archive)


def remove_from_archive(ticker: str):
    st.session_state.archive = [a for a in st.session_state.archive if a["ticker"] != ticker]
    save_json(ARCHIVE_PATH, st.session_state.archive)


def save_memo(ticker: str, text: str):
    st.session_state.memos[ticker] = {
        "text": text,
        "updated_at": datetime.now().isoformat(),
    }
    save_json(MEMO_PATH, st.session_state.memos)


# ─────────────────────────────────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────────────────────────────────
# ─── 메인 상단 헤더 (폰에서도 항상 보임) ───
header_cols = st.columns([4, 1, 1])
with header_cols[0]:
    st.markdown(
        f"## 📈 주식정보  <span style='color:#888;font-size:14px;font-weight:normal'>"
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}</span>",
        unsafe_allow_html=True,
    )
with header_cols[1]:
    if st.button("🔄 새로고침", use_container_width=True, help="데이터 다시 읽기"):
        st.cache_data.clear()
        st.rerun()
with header_cols[2]:
    with st.popover("ℹ️ 도움말", use_container_width=True):
        st.markdown("""
**탭 안내**
- 🏆 섹터: 섹터별 종목 자동 분류
- 📊 관심종목: 그룹별 종목 분석 (← →)
- 📰 주식뉴스: 자동 수집 (🔄 새로받기)
- 📥 새 정보: 유튜브/URL → Claude 분석
- 📦 보관: 종목·뉴스·정보 보관

**bat 파일 (cmd 자동 실행)**
- `1_분석_50종목.bat` = 시세+재무+뉴스+분석 풀 갱신
- `2_웹앱_띄우기.bat` = 이 화면
- `3_이벤트_체크.bat` = 급등락 알림
""")

# ─── 사이드바 — 기본 숨김, 필요 시 (모바일도) 메뉴로 열기 가능 ───
st.sidebar.title("📈 주식정보")
st.sidebar.caption(f"오늘: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
if st.sidebar.button("🔄 화면 새로고침", use_container_width=True, key="sidebar_refresh"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("폰에서는 좌상단 ▶ 버튼으로 이 사이드바 열고 닫을 수 있어요.")


# ─────────────────────────────────────────────────────────────────────
# 탭
# ─────────────────────────────────────────────────────────────────────
tab_sector, tab1, tab2, tab3, tab4 = st.tabs(
    ["🏆 섹터", "📊 관심종목", "📰 주식뉴스", "📥 새 정보", "📦 보관함"]
)

watchlist = load_watchlist()
# "섹터대표" 그룹은 관심종목 탭의 그룹 셀렉트박스에서 제외 (섹터 탭에서 활용)
all_groups = sorted(watchlist["group"].dropna().unique().tolist())
groups = [g for g in all_groups if g != "섹터대표"]

# ─────────────────────────────────────────────────────────────────────
# 탭 0: 🏆 섹터 (2단계: 섹터 목록 → 클릭 → 종목)
# ─────────────────────────────────────────────────────────────────────
with tab_sector:
    if "selected_sector" not in st.session_state:
        st.session_state.selected_sector = None

    try:
        from sector_view import build_sector_view, SECTOR_ORDER
        sector_data = build_sector_view()
    except Exception as e:
        st.error(f"섹터 데이터 로드 실패: {e}")
        sector_data = {}

    if not sector_data:
        st.header("🏆 섹터")
        st.info("아직 종목이 없어요. 관심종목 탭에서 종목을 추가하세요.")

    elif st.session_state.selected_sector and st.session_state.selected_sector in sector_data:
        # ─── 2단계: 단일 섹터 안의 종목 ───
        sec_name = st.session_state.selected_sector
        items = sector_data[sec_name]

        back_cols = st.columns([1, 5])
        with back_cols[0]:
            if st.button("← 섹터 목록", use_container_width=True, key="sec_back"):
                st.session_state.selected_sector = None
                st.rerun()
        with back_cols[1]:
            st.header(f"🏆 {sec_name}  ·  {len(items)}종목")

        st.markdown("---")

        for info in items:
            ticker = info["ticker"]
            name = info["name"]
            groups_list = info["groups"]
            is_leader = info["is_leader"]
            is_etf = info["is_etf"]

            tags = []
            if is_leader:
                tags.append("🏆 대표")
            if is_etf:
                tags.append("📦 ETF")
            for g in groups_list:
                tags.append(f"`{g}`")
            tag_str = " ".join(tags) if tags else ""

            report_path = find_latest_report(ticker, name)
            price_str = ""
            if report_path:
                summary = extract_summary_from_report(report_path)
                if summary and "price" in summary:
                    change_pct = summary.get("change_pct", 0)
                    arrow = "🔴" if change_pct > 0 else "🔵" if change_pct < 0 else "⚪"
                    price_str = f"{arrow} {summary['price']}원 ({change_pct:+.2f}%)"

            row_cols = st.columns([6, 1, 1])
            with row_cols[0]:
                line = f"**{name}** ({ticker})"
                if price_str:
                    line += f"  ·  {price_str}"
                if tag_str:
                    line += f"  ·  {tag_str}"
                st.markdown(line)
            with row_cols[1]:
                # Naver 모바일 주식 차트 페이지 (월봉 기본)
                naver_url = f"https://m.stock.naver.com/domestic/stock/{ticker}/chart"
                st.link_button("🔍 네이버", naver_url, use_container_width=True,
                               help="네이버 주식 차트 (새 탭)")
            with row_cols[2]:
                user_groups = [g for g in groups_list if g != "섹터대표"]
                if user_groups:
                    st.caption("✓ 관심중")
                else:
                    default_grp = groups[0] if groups else None
                    if default_grp and st.button("➕", key=f"sec_add_{sec_name}_{ticker}",
                                                   use_container_width=True,
                                                   help=f"'{default_grp}'에 추가"):
                        mkt = info.get("market", "KOSPI")
                        if add_to_group(ticker, name, default_grp, mkt, is_etf):
                            st.success(f"{default_grp}에 추가")
                            st.rerun()

        # 섹터 분석 버튼은 네이버 주식 페이지로 직접 이동 (인라인 뷰어 제거)

    else:
        # ─── 1단계: 섹터 목록 (카드형, 클릭 시 들어감) ───
        st.header("🏆 섹터")
        total_count = sum(len(items) for items in sector_data.values())
        st.caption(
            f"총 **{len(sector_data)}개 섹터, {total_count}종목** · 섹터를 클릭하면 안의 종목이 나옵니다. "
            f"관심종목에 추가하면 자동 반영, 관심에서 삭제해도 섹터에서는 유지됨."
        )
        st.markdown("---")

        # 섹터 카드 (한 줄에 2개씩)
        sec_items = list(sector_data.items())
        for i in range(0, len(sec_items), 2):
            row = st.columns(2, gap="medium")
            for j, col in enumerate(row):
                if i + j >= len(sec_items):
                    break
                sec_name, items = sec_items[i + j]
                with col:
                    with st.container(border=True):
                        # 상위 3개 종목 미리보기
                        top_names = [info["name"] for info in items[:3]]
                        extra = f" 외 {len(items)-3}개" if len(items) > 3 else ""
                        preview = ", ".join(top_names) + extra

                        c1, c2 = st.columns([5, 1])
                        with c1:
                            st.markdown(f"### 🏆 {sec_name}")
                            st.caption(f"**{len(items)}종목** · {preview}")
                        with c2:
                            if st.button("열기 ▶", key=f"sec_open_{sec_name}",
                                         use_container_width=True, type="primary"):
                                st.session_state.selected_sector = sec_name
                                st.rerun()

# ─────────────────────────────────────────────────────────────────────
# 탭 1: 관심종목
# ─────────────────────────────────────────────────────────────────────
with tab1:
    st.header("📊 관심종목")

    if not groups:
        st.warning("watchlist.csv 에 등록된 종목이 없습니다.")
    else:
        # 그룹 idx 안전 범위 보정 (그룹이 추가/삭제됐을 때 대비)
        if st.session_state.current_group_idx >= len(groups):
            st.session_state.current_group_idx = 0

        # ─── 한 줄: 이전 / 그룹 / 다음 / ⚙️ 관리 (popover) ───
        nav_cols = st.columns([1, 3, 1, 1.3])
        with nav_cols[0]:
            if st.button("◀", use_container_width=True,
                         disabled=st.session_state.current_group_idx == 0,
                         key="group_prev_btn", help="이전 그룹"):
                st.session_state.current_group_idx = max(0, st.session_state.current_group_idx - 1)
                st.rerun()
        with nav_cols[1]:
            new_idx = st.selectbox(
                "그룹",
                range(len(groups)),
                format_func=lambda i: groups[i],
                index=st.session_state.current_group_idx,
                label_visibility="collapsed",
            )
            if new_idx != st.session_state.current_group_idx:
                st.session_state.current_group_idx = new_idx
                st.rerun()
        with nav_cols[2]:
            if st.button("▶", use_container_width=True,
                         disabled=st.session_state.current_group_idx >= len(groups) - 1,
                         key="group_next_btn", help="다음 그룹"):
                st.session_state.current_group_idx = min(len(groups) - 1, st.session_state.current_group_idx + 1)
                st.rerun()
        with nav_cols[3]:
            with st.popover("⚙️ 관리", use_container_width=True):
                # ─── 새 관심 그룹 만들기 ───
                st.markdown("**➕ 새 관심 그룹**")
                ng_cols = st.columns([3, 1])
                with ng_cols[0]:
                    new_grp_name_pop = st.text_input(
                        "새 관심 그룹 이름",
                        placeholder="예: 관심6, 매수후보, 2026년",
                        key="new_watch_group_pop",
                        label_visibility="collapsed",
                    )
                with ng_cols[1]:
                    if st.button("➕ 만들기", use_container_width=True, key="add_watch_group_pop"):
                        nm = new_grp_name_pop.strip()
                        if nm:
                            df_now = load_watchlist()
                            if nm in df_now["group"].astype(str).unique():
                                st.warning(f"'{nm}' 이미 있음")
                            else:
                                new_row = pd.DataFrame([{
                                    "group": nm, "name": "", "ticker": "",
                                    "market": "", "is_etf": False, "note": "",
                                }])
                                df_now = pd.concat([df_now, new_row], ignore_index=True)
                                save_watchlist(df_now)
                                new_groups_list = sorted(df_now["group"].dropna().unique().tolist())
                                new_groups_list = [g for g in new_groups_list if g != "섹터대표"]
                                if nm in new_groups_list:
                                    st.session_state.current_group_idx = new_groups_list.index(nm)
                                st.success(f"'{nm}' 생성")
                                st.rerun()

                st.markdown("---")
                # ─── 그룹 삭제 ───
                st.markdown("**🗑️ 그룹 삭제**")
                dg_cols = st.columns([3, 1])
                with dg_cols[0]:
                    del_grp_pop = st.selectbox(
                        "삭제할 그룹",
                        ["(선택)"] + groups,
                        key="del_watch_group_pop",
                        label_visibility="collapsed",
                    )
                with dg_cols[1]:
                    if st.button("🗑️ 삭제", use_container_width=True,
                                 disabled=(del_grp_pop == "(선택)"),
                                 help="그룹 안 종목들도 사라짐",
                                 key="del_watch_group_btn_pop"):
                        if del_grp_pop != "(선택)":
                            df_now = load_watchlist()
                            df_now = df_now[df_now["group"] != del_grp_pop]
                            save_watchlist(df_now)
                            if st.session_state.current_group_idx >= len(groups) - 1:
                                st.session_state.current_group_idx = 0
                            st.success(f"'{del_grp_pop}' 삭제")
                            st.rerun()

                st.markdown("---")
                # ─── 현재 그룹에 종목 추가 ───
                st.markdown(f"**➕ '{groups[st.session_state.current_group_idx]}'에 종목 추가**")
                from analyze_stock import detect_market as _det_mkt_pop

                @st.cache_data(ttl=3600, show_spinner=False)
                def _korea_idx_pop() -> dict:
                    from pykrx import stock as _pkx
                    mp = {}
                    try:
                        for mkt in ["KOSPI", "KOSDAQ"]:
                            for t in _pkx.get_market_ticker_list(market=mkt):
                                try:
                                    nm = _pkx.get_market_ticker_name(t)
                                    mp[t] = (nm, mkt)
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    return mp

                add_cols = st.columns([3, 1])
                with add_cols[0]:
                    new_input_pop = st.text_input(
                        "종목명 또는 6자리 코드",
                        placeholder="예: 삼성전자 또는 005930",
                        key="add_input_pop",
                        label_visibility="collapsed",
                    )
                with add_cols[1]:
                    do_add_pop = st.button("➕ 추가", use_container_width=True, key="add_btn_pop")

                if do_add_pop and new_input_pop.strip():
                    import requests as _rq_pop
                    q = new_input_pop.strip()
                    cur_grp = groups[st.session_state.current_group_idx]
                    added_stock = None

                    def _via_naver_api_pop(tk: str):
                        try:
                            url = f"https://m.stock.naver.com/api/stock/{tk}/integration"
                            r = _rq_pop.get(url, headers={
                                "User-Agent": "Mozilla/5.0",
                                "Referer": "https://m.stock.naver.com/",
                            }, timeout=10)
                            if r.status_code == 200:
                                data = r.json()
                                nm = data.get("stockName", "")
                                mkt_obj = data.get("stockExchangeType", {}) or {}
                                mkt_code = mkt_obj.get("code", "") if isinstance(mkt_obj, dict) else ""
                                mkt = "KOSPI" if "KOSPI" in mkt_code.upper() else ("KOSDAQ" if "KOSDAQ" in mkt_code.upper() else "KOSPI")
                                if nm:
                                    return (tk, nm, mkt)
                        except Exception:
                            pass
                        return None

                    if q.isdigit() and len(q) == 6:
                        from pykrx import stock as _pkx_pop
                        try:
                            nm = _pkx_pop.get_market_ticker_name(q)
                            if nm:
                                mkt = _det_mkt_pop(q) or "KOSPI"
                                added_stock = (q, nm, mkt)
                        except Exception:
                            pass
                        if not added_stock:
                            added_stock = _via_naver_api_pop(q)

                    if not added_stock and not q.isdigit():
                        with st.spinner("검색 중..."):
                            idx = _korea_idx_pop()
                        matches = [(t, nm, mkt) for t, (nm, mkt) in idx.items() if q in nm]
                        if len(matches) == 1:
                            added_stock = matches[0]
                        elif len(matches) > 1:
                            exact = [m for m in matches if m[1] == q]
                            if exact:
                                added_stock = exact[0]
                            else:
                                st.warning(f"여러 종목 발견. 코드로 입력하세요:\n" +
                                           "\n".join(f"- {nm} ({t})" for t, nm, _ in matches[:5]))

                    if added_stock:
                        t, nm, mkt = added_stock
                        if add_to_group(t, nm, cur_grp, mkt):
                            st.success(f"✅ {nm} 추가됨")
                            st.rerun()
                        else:
                            st.info("이미 그 그룹에 있어요")
                    elif do_add_pop:
                        st.error(f"'{q}' 못 찾음")

        selected_group = groups[st.session_state.current_group_idx]
        group_df = watchlist[watchlist["group"] == selected_group].reset_index(drop=True)

        st.caption(f"**{selected_group}** ({st.session_state.current_group_idx + 1}/{len(groups)} 그룹) · {len(group_df)}개 종목")

        st.markdown("---")

        # 종목 선택됐으면 풀너비 상세, 아니면 풀너비 리스트
        _sel_t = st.session_state.get("selected_ticker", "")
        _sel_n = st.session_state.get("selected_name", "")

        if _sel_t and _sel_n:
            # 우측 상세만 풀너비로 (col_left 숨김)
            col_right = st.container()
            col_left = None
        else:
            col_right = None
            col_left = st.container()

        if col_left is not None:
          with col_left:
            st.subheader("종목")
            for i, row in group_df.iterrows():
                ticker = str(row["ticker"]).zfill(6) if row["ticker"] else ""
                name = row["name"]
                is_etf = str(row.get("is_etf", "False")).lower() == "true"

                if not ticker:
                    st.caption(f"⚠️ {name} (티커 없음)")
                    continue

                latest_report = find_latest_report(ticker, name)
                summary = extract_summary_from_report(latest_report) if latest_report else {}
                price = summary.get("price", "—")
                change_pct = summary.get("change_pct")

                btn_label = f"**{name}** ({ticker})"
                if is_etf:
                    btn_label = f"📦 {btn_label}"
                if price != "—" and change_pct is not None:
                    color_emoji = "🔴" if change_pct > 0 else "🔵" if change_pct < 0 else "⚪"
                    btn_label += f"\n\n{color_emoji} {price}원 ({change_pct:+.2f}%)"
                else:
                    btn_label += "\n\n_분석 안 됨_"

                if st.button(btn_label, key=f"stock_{ticker}_{i}", use_container_width=True):
                    st.session_state.selected_ticker = ticker
                    st.session_state.selected_name = name

        if col_right is not None:
          with col_right:
            ticker = st.session_state.get("selected_ticker", "")
            name = st.session_state.get("selected_name", "")

            if ticker and name:
                current_groups = get_groups_for_ticker(watchlist, ticker)
                grps_str = ", ".join(current_groups) if current_groups else "없음"

                # 한 줄: [종목명][← 리스트][🔄 재분석][📦 보관][⚙️ 그룹]
                row1 = st.columns([3, 1, 1, 1, 1])
                with row1[0]:
                    st.subheader(f"{name} ({ticker})")
                    st.caption(f"📁 속한 그룹: **{grps_str}**  · 시장: KOSPI")
                with row1[1]:
                    if st.button("← 리스트", use_container_width=True, key=f"close_detail_{ticker}",
                                 help="리스트로 돌아가기"):
                        st.session_state.selected_ticker = ""
                        st.session_state.selected_name = ""
                        st.rerun()
                with row1[2]:
                    if st.button("🔄 재분석", use_container_width=True, key=f"reanalyze_{ticker}"):
                        market_row = watchlist[watchlist["ticker"].astype(str).str.zfill(6) == ticker]
                        market = str(market_row.iloc[0]["market"]) if not market_row.empty else "KOSPI"
                        if trigger_reanalysis(ticker, name, market):
                            st.success("✅ 재분석 완료")
                            st.cache_data.clear()
                            st.rerun()
                with row1[3]:
                    if st.button("📦 보관", use_container_width=True, key=f"archive_{ticker}"):
                        try:
                            from stock_archive import add_stock as _stk_arc_add
                            _stk_arc_add(ticker, name, "기본")
                        except Exception:
                            add_to_archive(ticker, name)
                        st.success("보관함 추가")
                with row1[4]:
                    with st.popover("⚙️ 그룹", use_container_width=True, help="그룹 관리"):
                        st.markdown(f"**📁 속한 그룹**: {grps_str}")
                        st.markdown("---")
                        st.markdown("**그룹으로 추가**")
                        gp_cols = st.columns([3, 1])
                        with gp_cols[0]:
                            target_group = st.selectbox(
                                "그룹",
                                groups,
                                key=f"move_target_{ticker}",
                                label_visibility="collapsed",
                            )
                        with gp_cols[1]:
                            if st.button("➕", key=f"add_group_{ticker}", use_container_width=True):
                                market_row = watchlist[watchlist["ticker"].astype(str).str.zfill(6) == ticker]
                                market = str(market_row.iloc[0]["market"]) if not market_row.empty else ""
                                if add_to_group(ticker, name, target_group, market):
                                    st.success(f"{target_group}에 추가")
                                    st.rerun()
                                else:
                                    st.info("이미 있음")
                        st.markdown("---")
                        if st.button(f"❌ '{selected_group}'에서 빼기",
                                     key=f"remove_cur_{ticker}", use_container_width=True):
                            remove_from_group(ticker, selected_group)
                            st.session_state.selected_ticker = ""
                            st.session_state.selected_name = ""
                            st.rerun()

                report_path = find_latest_report(ticker, name)
                if report_path:
                    text = report_path.read_text(encoding="utf-8")
                    text_no_memo = re.sub(r"## 내 메모.*?(?=\n---|\Z)", "", text, flags=re.DOTALL)
                    text_no_memo = strip_first_h1(text_no_memo)
                    text_no_memo = clean_news_in_markdown(text_no_memo)
                    st.markdown(text_no_memo)

                    st.markdown("---")
                    st.markdown("### ✏️ 내 메모")
                    current_memo = st.session_state.memos.get(ticker, {}).get("text", "")
                    new_memo = st.text_area(
                        "메모",
                        value=current_memo,
                        height=150,
                        key=f"memo_{ticker}",
                        label_visibility="collapsed",
                    )
                    if st.button("💾 메모 저장", key=f"save_memo_{ticker}"):
                        save_memo(ticker, new_memo)
                        st.success("메모 저장됨")

                    if ticker in st.session_state.memos:
                        updated = st.session_state.memos[ticker].get("updated_at", "")
                        if updated:
                            st.caption(f"마지막 수정: {updated[:19]}")
                else:
                    st.info(f"분석 리포트가 아직 없습니다.")
                    if st.button("🤖 지금 분석하기", key=f"analyze_now_{ticker}"):
                        market_row = watchlist[watchlist["ticker"].astype(str).str.zfill(6) == ticker]
                        market = str(market_row.iloc[0]["market"]) if not market_row.empty else "KOSPI"
                        if trigger_reanalysis(ticker, name, market):
                            st.success("✅ 분석 완료")
                            st.cache_data.clear()
                            st.rerun()
            else:
                st.info("← 왼쪽에서 종목을 선택하세요")

# ─────────────────────────────────────────────────────────────────────
# 탭 2: 주식뉴스 (한 줄 + 체크박스 + 일괄 처리)
# ─────────────────────────────────────────────────────────────────────
with tab2:
    import hashlib

    def _nid(title: str, ticker: str = "") -> str:
        return hashlib.md5(f"{title}|{ticker}".encode("utf-8")).hexdigest()[:12]

    try:
        from news_cache import load_news_cache, get_cache_age_minutes
        cache = load_news_cache()
        age = get_cache_age_minutes()
    except Exception:
        cache = None
        age = None

    try:
        from archive_manager import (
            get_folders as get_news_folders,
            add_news as archive_news,
            trash_news as trash_news_item,
            get_seen_titles,
        )
        news_folders_available = get_news_folders()
        seen_archived_titles = get_seen_titles()
    except Exception:
        news_folders_available = ["기본"]
        seen_archived_titles = set()
        archive_news = None
        trash_news_item = None

    try:
        from user_input import get_pending_inputs, archive_user_input, trash_user_input
        pending_inputs = get_pending_inputs()
    except Exception:
        pending_inputs = []

    # ─── 컴팩트 도구모음 — 한 줄에 5개 ───
    # 순서: [뉴스받기] [전체] [삭제] | [폴더▼] [이동]
    bar_cols = st.columns([1.2, 0.9, 0.9, 1.5, 0.9])
    with bar_cols[0]:
        if st.button("🔄 뉴스받기", use_container_width=True, type="primary"):
            if trigger_news_refresh():
                st.success("✅ 갱신 완료")
                st.rerun()
    with bar_cols[1]:
        select_all_clicked = st.button("☑ 전체", use_container_width=True, key="news_sel_all")
        unselect_all_clicked = False  # 호환용
    with bar_cols[2]:
        sel_delete = st.button("🗑️ 삭제", use_container_width=True, key="news_sel_del")
    with bar_cols[3]:
        bulk_folder = st.selectbox(
            "폴더",
            news_folders_available,
            key="bulk_folder",
            label_visibility="collapsed",
        )
    with bar_cols[4]:
        sel_archive = st.button("🚚 이동", use_container_width=True, key="news_sel_mv",
                                 help=f"선택한 뉴스를 '{bulk_folder}' 폴더로 보관")

    # 갱신 시간 표시 (한 줄)
    if cache and age is not None:
        if age < 60: age_str = f"{age}분 전"
        elif age < 1440: age_str = f"{age // 60}시간 전"
        else: age_str = f"{age // 1440}일 전"
        st.caption(f"마지막 갱신: {age_str} · 자동 X")
    else:
        st.caption("캐시 없음. 뉴스받기 클릭")

    if "news_selected_ids" not in st.session_state:
        st.session_state.news_selected_ids = {}  # nid → news dict

    # ─── 김진호님 입력 (한 줄 형식) ───
    if pending_inputs:
        st.markdown("#### 💬 김진호님이 공유한 정보")
        for entry in pending_inputs[:10]:
            entry_id = entry.get("id", "")
            src = entry.get("source", "입력")[:90]
            ts = entry.get("timestamp", "")[:16]
            related = entry.get("related_tickers", [])

            row_cols = st.columns([6, 1, 1])
            with row_cols[0]:
                st.markdown(
                    f'<div class="news-row">📥 <strong>{src}</strong> '
                    f'<span class="news-meta">· {ts}'
                    + (f' · 관련: {", ".join(related)}' if related else '')
                    + '</span></div>',
                    unsafe_allow_html=True,
                )
                with st.expander("분석 결과 보기"):
                    st.markdown(entry.get("analysis", ""))
            with row_cols[1]:
                if st.button("📦", key=f"arc_input_{entry_id}", use_container_width=True, help="정보 보관"):
                    archive_user_input(entry_id)
                    st.rerun()
            with row_cols[2]:
                if st.button("🗑️", key=f"trash_input_{entry_id}", use_container_width=True, help="삭제 (휴지통)"):
                    trash_user_input(entry_id)
                    st.rerun()
        st.markdown("---")

    # ─── 종목 자동 수집 뉴스 — 한 줄씩 ───
    all_news = []
    if cache and "by_ticker" in cache:
        for ticker, info in cache["by_ticker"].items():
            for n in info.get("news", []):
                n["ticker"] = ticker
                n["stock_name"] = info.get("name", "")
                all_news.append(n)

    # 중복 제거 + 이미 처리된(보관/휴지통) 뉴스 제외
    seen_titles = set()
    unique_news = []
    skipped_seen = 0
    for n in all_news:
        title = n.get("title", "")
        if not title or title in seen_titles:
            continue
        if title in seen_archived_titles:
            skipped_seen += 1
            continue
        seen_titles.add(title)
        unique_news.append(n)

    # 선택 액션 처리
    if sel_archive and archive_news:
        count = 0
        for nid, news in list(st.session_state.news_selected_ids.items()):
            archive_news(
                title=news.get("title", ""),
                link=news.get("link", ""),
                summary=news.get("summary", ""),
                ticker=news.get("ticker", ""),
                stock_name=news.get("stock_name", ""),
                folder=bulk_folder,
            )
            count += 1
        st.session_state.news_selected_ids = {}
        if count:
            st.success(f"✅ {count}개 '{bulk_folder}'에 보관")
            st.rerun()
        else:
            st.warning("선택된 뉴스 없음")

    if sel_delete and trash_news_item:
        count = 0
        for nid, news in list(st.session_state.news_selected_ids.items()):
            trash_news_item({
                "title": news.get("title", ""),
                "link": news.get("link", ""),
                "summary": news.get("summary", ""),
                "ticker": news.get("ticker", ""),
                "stock_name": news.get("stock_name", ""),
            })
            count += 1
        st.session_state.news_selected_ids = {}
        if count:
            st.success(f"🗑️ {count}개 휴지통으로 (보관 탭 → 삭제함에서 복원 가능)")
            st.rerun()
        else:
            st.warning("선택된 뉴스 없음")

    cap = f"📡 자동 수집 뉴스 · 총 **{len(unique_news)}개**"
    if skipped_seen:
        cap += f" · 이미 보관/삭제된 {skipped_seen}개 제외"
    st.markdown(cap)

    if not unique_news:
        st.info("표시할 뉴스가 없습니다. [🔄 새로받기] 누르거나 `1_분석_50종목.bat` 실행해보세요.")
    else:
        # ★★★ 전체선택/해제 처리 — 체크박스 렌더 전에 session_state 미리 세팅 ★★★
        # (Streamlit 체크박스가 key 가지면 value 파라미터 무시하므로 필수)
        if select_all_clicked:
            for n in unique_news[:100]:
                nid = _nid(n.get("title", ""), n.get("ticker", ""))
                st.session_state[f"chk_{nid}"] = True
                st.session_state.news_selected_ids[nid] = n
        if unselect_all_clicked:
            for n in unique_news[:100]:
                nid = _nid(n.get("title", ""), n.get("ticker", ""))
                st.session_state[f"chk_{nid}"] = False
            st.session_state.news_selected_ids = {}

        for n_idx, n in enumerate(unique_news[:100]):
            ticker = n.get("ticker", "")
            stock_name = n.get("stock_name", "")
            title = n.get("title", "")
            link = n.get("link", "")
            summary = n.get("summary", "")
            nid = _nid(title, ticker)

            # 한 줄: [체크] [제목 · 종목] [🗑️]
            row_cols = st.columns([0.4, 9, 0.7])

            with row_cols[0]:
                checked = st.checkbox(
                    "선택",
                    key=f"chk_{nid}",
                    label_visibility="collapsed",
                )
                if checked:
                    st.session_state.news_selected_ids[nid] = n
                else:
                    st.session_state.news_selected_ids.pop(nid, None)

            with row_cols[1]:
                escaped_title = (
                    title.replace("\\", "\\\\")
                         .replace("[", "\\[")
                         .replace("]", "\\]")
                )
                stock_text = f"{stock_name}({ticker})" if stock_name else ""
                if link:
                    line_md = f"📰 **[{escaped_title}]({link})**"
                else:
                    fallback = f"https://www.google.com/search?q={quote(title)}"
                    line_md = f"📰 **[{escaped_title}]({fallback})** _(검색)_"
                if stock_text:
                    line_md += f"  ·  {stock_text}"
                st.markdown(line_md)

            with row_cols[2]:
                if st.button("🗑️", key=f"news_del_{nid}", use_container_width=True, help="삭제 (휴지통)"):
                    try:
                        trash_news_item({
                            "title": title, "link": link, "summary": summary,
                            "ticker": ticker, "stock_name": stock_name,
                        })
                        st.success("휴지통으로")
                        st.rerun()
                    except Exception as e:
                        st.error(f"삭제 실패: {e}")


# ─────────────────────────────────────────────────────────────────────
# 탭 3: 새 정보
# ─────────────────────────────────────────────────────────────────────
with tab3:
    st.header("📥 새 정보 분석")
    st.markdown("""
유튜브 영상, 뉴스 URL, 또는 직접 작성한 텍스트를 입력하면 Claude가 분석해서 관련 종목·시사점을 정리해드립니다.

분석 결과는 일단 **주식뉴스** 탭의 "💬 김진호님이 공유한 정보" 섹션에 표시됩니다.
거기서 **[📦 보관]** 또는 **[🗑️ 삭제]** 결정하시면 됩니다. 보관하면 보관함 탭으로 이동.
""")

    input_type = st.radio(
        "정보 종류",
        ["자동 감지", "유튜브", "URL", "직접 텍스트"],
        horizontal=True,
        key="input_type_radio",
    )

    type_map = {
        "자동 감지": "auto",
        "유튜브": "youtube",
        "URL": "url",
        "직접 텍스트": "text",
    }
    selected_type = type_map[input_type]

    if selected_type == "text":
        input_text = st.text_area(
            "내용 입력",
            height=200,
            placeholder="예) 어제 OO기업이 대규모 미국 투자 발표했어. 어떻게 생각해?",
            key="user_input_text",
        )
    else:
        input_text = st.text_input(
            "링크 입력",
            placeholder=(
                "https://www.youtube.com/watch?v=..." if selected_type == "youtube"
                else "https://news.naver.com/..." if selected_type == "url"
                else "유튜브 링크나 뉴스 URL 또는 텍스트 모두 가능"
            ),
            key="user_input_link",
        )

    col_submit, col_info = st.columns([1, 4])
    with col_submit:
        submit = st.button("🤖 분석 요청", type="primary", use_container_width=True)
    with col_info:
        st.caption("⏱️ 분석 시간: 30~60초. 유튜브는 자막 추출까지 추가 5~10초.")

    if submit and input_text.strip():
        with st.spinner("Claude가 분석 중..."):
            try:
                from user_input import process_input
                result = process_input(input_text, input_type=selected_type)
                if "error" in result:
                    st.error(f"❌ {result['error']}")
                    st.session_state.last_analysis_result = None
                else:
                    st.session_state.last_analysis_result = result
            except Exception as e:
                st.error(f"❌ 처리 중 오류: {e}")
                st.session_state.last_analysis_result = None

    # 마지막 분석 결과 표시 + 보관/삭제 버튼
    if st.session_state.last_analysis_result:
        result = st.session_state.last_analysis_result
        result_id = result.get("id", "")
        st.success("✅ 분석 완료")
        st.markdown("---")
        st.markdown(result.get("analysis", ""))
        related = result.get("related_tickers", [])
        if related:
            st.info(f"📌 추출된 관련 티커: {', '.join(related)}")

        st.markdown("---")
        st.markdown("**이 분석을 어떻게 처리할까요?**")
        decide_cols = st.columns([1, 1, 3])
        with decide_cols[0]:
            if st.button("📦 보관함으로", use_container_width=True, key=f"keep_result_{result_id}"):
                from user_input import archive_user_input
                archive_user_input(result_id)
                st.session_state.last_analysis_result = None
                st.success("보관함으로 이동")
                st.rerun()
        with decide_cols[1]:
            if st.button("🗑️ 휴지통", use_container_width=True, key=f"del_result_{result_id}", help="휴지통으로 (복원 가능)"):
                from user_input import trash_user_input
                trash_user_input(result_id)
                st.session_state.last_analysis_result = None
                st.success("휴지통으로 이동")
                st.rerun()
        with decide_cols[2]:
            st.caption("결정 안 하면 일단 주식뉴스 탭에 임시 표시됩니다.")

    # 최근 입력 이력 (pending만)
    st.markdown("---")
    st.markdown("### 📜 최근 입력 이력 (대기 중)")
    try:
        from user_input import get_pending_inputs
        entries = get_pending_inputs()
        if entries:
            st.caption(f"보관/삭제 결정 대기 중: {len(entries)}개")
            for entry in entries[:5]:
                ts = entry.get("timestamp", "")[:16]
                src = entry.get("source", "")[:60]
                with st.expander(f"[{ts}] {src}"):
                    st.markdown(entry.get("analysis", ""))
        else:
            st.caption("(대기 중인 입력 없음)")
    except Exception:
        st.caption("(이력 로드 실패)")

# ─────────────────────────────────────────────────────────────────────
# 탭 4: 보관
# ─────────────────────────────────────────────────────────────────────
with tab4:
    # ─── 보관함 상단: [⚙️ 폴더 관리] popover (모든 종목/뉴스/정보 폴더 통합 관리) ───
    try:
        from folder_system import (
            get_folders as fs_get_folders,
            add_folder as fs_add_folder,
            remove_folder as fs_remove_folder,
            sync_all as fs_sync_all,
            count_total as fs_count_total,
        )
        fs_sync_all()  # 양 모듈에 폴더 동기화
        global_folders = fs_get_folders()
    except Exception as e:
        st.error(f"폴더 시스템 로드 실패: {e}")
        global_folders = ["기본"]
        fs_add_folder = lambda *a, **k: (False, "모듈 없음")
        fs_remove_folder = lambda *a, **k: (False, "모듈 없음")
        fs_count_total = lambda f: (0, 0, 0)

    fmgr_cols = st.columns([3, 1])
    with fmgr_cols[0]:
        st.caption("📦 보관함 — 종목·뉴스·정보를 폴더별로 정리. 폴더는 모두 공유됨.")
    with fmgr_cols[1]:
        with st.popover("⚙️ 폴더 관리", use_container_width=True, help="폴더 추가/삭제 (전체 공유)"):
            st.markdown("**📁 현재 폴더 목록**")
            for f in global_folders:
                n_stk, n_news, n_inf = fs_count_total(f)
                st.caption(f"📁 **{f}** · 종목 {n_stk} / 뉴스 {n_news} / 정보 {n_inf}")
            st.markdown("---")
            st.markdown("**➕ 새 폴더 추가**")
            new_cols = st.columns([3, 1])
            with new_cols[0]:
                new_folder_name_global = st.text_input(
                    "이름",
                    placeholder="예: 장기투자, 매수후보, 흥미로운 뉴스",
                    key="new_folder_global",
                    label_visibility="collapsed",
                )
            with new_cols[1]:
                if st.button("➕", use_container_width=True, key="add_folder_global_btn"):
                    if new_folder_name_global.strip():
                        ok, msg = fs_add_folder(new_folder_name_global.strip())
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)

            st.markdown("---")
            st.markdown("**🗑️ 폴더 삭제** _(안의 항목들은 '기본'으로 이동)_")
            del_cols = st.columns([3, 1])
            with del_cols[0]:
                del_folder_global = st.selectbox(
                    "삭제할 폴더",
                    ["(선택)"] + [f for f in global_folders if f != "기본"],
                    key="del_folder_global_pick",
                    label_visibility="collapsed",
                )
            with del_cols[1]:
                if st.button("🗑️", use_container_width=True,
                             disabled=(del_folder_global == "(선택)"),
                             key="del_folder_global_btn"):
                    if del_folder_global != "(선택)":
                        ok, msg = fs_remove_folder(del_folder_global)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)

    sub1, sub2, sub3, sub4 = st.tabs(["📊 종목 보관", "📰 뉴스 보관", "💬 정보 보관", "🗑️ 삭제함"])

    # ─── 종목 보관 (폴더 + 한 줄 + 일괄 처리) ───
    with sub1:
        try:
            from stock_archive import (
                get_folders as get_stk_folders,
                add_folder as add_stk_folder,
                remove_folder as remove_stk_folder,
                count_in_folder as count_stk_in_folder,
                add_stock as stk_add,
                move_stock as stk_move,
                remove_stock as stk_remove,
                get_stocks_in_folder,
                get_all_stocks,
            )
            stk_folders = get_stk_folders()
            stk_all = get_all_stocks()
        except Exception as e:
            st.error(f"종목 보관 모듈 로드 실패: {e}")
            stk_folders = ["기본"]
            stk_all = list(st.session_state.archive)

        # 기존 archive.json (list 형식) 자동 마이그레이션 — session_state 도 업데이트
        if not stk_all and st.session_state.archive:
            for it in st.session_state.archive:
                stk_add(it["ticker"], it["name"], "기본")
            stk_all = get_all_stocks()
            st.session_state.archive = stk_all

        if not stk_all:
            st.info("보관된 종목이 없습니다.\n\n주식뉴스나 종목 상세에서 [📦 보관] 버튼으로 추가할 수 있어요.")

        if "stk_arc_selected" not in st.session_state:
            st.session_state.stk_arc_selected = {}

        # ─── 초간단 한 줄: [폴더▼] [☑전체] [→폴더▼] [🚚이동] [🗑️해제] ───
        # 폴더 관리는 보관함 상단 ⚙️ 폴더 관리에서
        bar_cols = st.columns([1.6, 0.7, 1.4, 0.8, 0.9])
        with bar_cols[0]:
            selected_stk_folder = st.selectbox(
                "📁 폴더 보기",
                global_folders,
                format_func=lambda f: f"📁 {f} ({count_stk_in_folder(f)}개)",
                key="stk_view_folder",
                label_visibility="collapsed",
            )
        with bar_cols[1]:
            stk_select_all = st.button("☑ 전체", use_container_width=True, key="stk_arc_sel_all")
            stk_unselect = False  # 해제는 전체선택 다시 누르거나 개별 클릭으로
        with bar_cols[2]:
            stk_bulk_target = st.selectbox(
                "→ 이동",
                global_folders,
                key="stk_arc_bulk_target",
                label_visibility="collapsed",
            )
        with bar_cols[3]:
            stk_bulk_move = st.button("🚚 이동", use_container_width=True, key="stk_arc_bulk_move")
        with bar_cols[4]:
            stk_bulk_remove = st.button("🗑️ 해제", use_container_width=True, key="stk_arc_bulk_rm",
                                         help="선택 종목 보관 해제 (영구)")

        st.caption(f"📁 {selected_stk_folder} · {count_stk_in_folder(selected_stk_folder)}개 (전체 {len(stk_all)}개)")

        items_in_folder = get_stocks_in_folder(selected_stk_folder)
        # 폴백: 폴더 필터링이 실패하면 stk_all 사용
        if not items_in_folder and stk_all:
            # 선택된 폴더에 속한다고 표시된 항목들 직접 필터
            items_in_folder = [
                it for it in stk_all
                if it.get("folder", "기본") == selected_stk_folder
            ]
            # 그래도 없으면 전체 표시 (기본 폴더일 때만)
            if not items_in_folder and selected_stk_folder == "기본":
                items_in_folder = stk_all

        # 일괄 선택/해제
        if stk_select_all:
            for itm in items_in_folder:
                tk = itm["ticker"]
                st.session_state[f"stk_arc_chk_{tk}"] = True
                st.session_state.stk_arc_selected[tk] = itm
        if stk_unselect:
            for itm in items_in_folder:
                tk = itm["ticker"]
                st.session_state[f"stk_arc_chk_{tk}"] = False
            st.session_state.stk_arc_selected = {}

        # 일괄 폴더 이동
        if stk_bulk_move:
            moved = 0
            for tk, itm in list(st.session_state.stk_arc_selected.items()):
                stk_move(tk, stk_bulk_target)
                moved += 1
            if moved:
                st.success(f"✅ {moved}개 → '{stk_bulk_target}' 폴더로")
                st.session_state.stk_arc_selected = {}
                st.rerun()
            else:
                st.warning("선택된 종목 없음")

        # 일괄 보관해제
        if stk_bulk_remove:
            removed = 0
            for tk in list(st.session_state.stk_arc_selected.keys()):
                stk_remove(tk)
                removed += 1
            st.session_state.stk_arc_selected = {}
            if removed:
                st.success(f"✅ {removed}개 보관 해제")
                st.rerun()
            else:
                st.warning("선택된 종목 없음")

        st.markdown("---")

        # 한 줄씩 표시
        if not items_in_folder:
            st.caption(f"'{selected_stk_folder}' 폴더가 비어있어요")
        else:
            for item in items_in_folder:
                ticker = item["ticker"]
                name = item["name"]
                added_at = item.get("added_at", "")[:16]

                row_cols = st.columns([0.4, 8, 0.7, 0.7])
                with row_cols[0]:
                    chk = st.checkbox(
                        "선택",
                        key=f"stk_arc_chk_{ticker}",
                        label_visibility="collapsed",
                    )
                    if chk:
                        st.session_state.stk_arc_selected[ticker] = item
                    else:
                        st.session_state.stk_arc_selected.pop(ticker, None)
                with row_cols[1]:
                    info_parts = [f"**{name}** ({ticker})"]
                    report_path = find_latest_report(ticker, name)
                    if report_path:
                        summary = extract_summary_from_report(report_path)
                        if summary:
                            if "price" in summary:
                                change_pct = summary.get('change_pct', 0)
                                arrow = "🔴" if change_pct > 0 else "🔵" if change_pct < 0 else "⚪"
                                info_parts.append(f"{arrow} {summary['price']}원 ({change_pct:+.2f}%)")
                            if "market_cap" in summary:
                                info_parts.append(summary['market_cap'])
                    info_parts.append(f"_{added_at}_")
                    st.markdown(" · ".join(info_parts))
                with row_cols[2]:
                    if st.button("🔍", key=f"stk_view_{ticker}", use_container_width=True, help="이 자리에서 분석 보기"):
                        st.session_state["stk_arc_show_analysis"] = (ticker, name)
                        st.rerun()
                with row_cols[3]:
                    if st.button("🗑️", key=f"unarc_stk_{ticker}", use_container_width=True, help="보관 해제"):
                        stk_remove(ticker)
                        st.rerun()

        # ─── 인라인 분석 뷰어 (🔍 클릭 시 여기에 표시) ───
        if st.session_state.get("stk_arc_show_analysis"):
            sel_ticker, sel_name = st.session_state["stk_arc_show_analysis"]
            st.markdown("---")
            head_cols = st.columns([5, 1, 1])
            with head_cols[0]:
                st.markdown(f"### 🔍 {sel_name} ({sel_ticker}) — 분석 리포트")
            with head_cols[1]:
                if st.button("🔄 재분석", key=f"stk_arc_reanalyze_{sel_ticker}", use_container_width=True):
                    market_row = watchlist[watchlist["ticker"].astype(str).str.zfill(6) == sel_ticker]
                    market = str(market_row.iloc[0]["market"]) if not market_row.empty else "KOSPI"
                    if trigger_reanalysis(sel_ticker, sel_name, market):
                        st.cache_data.clear()
                        st.rerun()
            with head_cols[2]:
                if st.button("✖ 닫기", key=f"stk_arc_close_analysis", use_container_width=True):
                    st.session_state["stk_arc_show_analysis"] = None
                    st.rerun()

            sel_report = find_latest_report(sel_ticker, sel_name)
            if sel_report:
                text = sel_report.read_text(encoding="utf-8")
                text_clean = re.sub(r"## 내 메모.*?(?=\n---|\Z)", "", text, flags=re.DOTALL)
                text_clean = strip_first_h1(text_clean)
                text_clean = clean_news_in_markdown(text_clean)
                st.markdown(text_clean)
            else:
                st.info(f"분석 리포트가 아직 없습니다. 위 [🔄 재분석] 클릭하면 만들 수 있어요.")

    # ─── 뉴스 보관 (사용자 정의 폴더) ───
    with sub2:
        try:
            from archive_manager import (
                get_folders as get_news_folders,
                add_folder as add_news_folder,
                remove_folder as remove_news_folder,
                rename_folder as rename_news_folder,
                get_news_in_folder,
                trash_news as trash_news_in_archive,
                move_news,
                count_in_folder,
            )
        except Exception as e:
            st.error(f"보관함 모듈 로드 실패: {e}")
            get_news_folders = lambda: ["기본"]
            get_news_in_folder = lambda f: []
            count_in_folder = lambda f: 0
            add_news_folder = lambda *a, **k: (False, "모듈 없음")
            remove_news_folder = lambda *a, **k: (False, "모듈 없음")
            rename_news_folder = lambda *a, **k: (False, "모듈 없음")
            trash_news_in_archive = lambda *a, **k: None
            move_news = lambda *a, **k: False

        all_folders = get_news_folders()

        # 글로벌 폴더 사용 (보관함 상단 ⚙️ 폴더 관리에서 추가/삭제)
        all_folders = global_folders

        # 폴더 선택 (한 줄에 작은 광고 정리 버튼 포함)
        folder_cols = st.columns([4, 1])
        with folder_cols[0]:
            selected_folder = st.selectbox(
                "폴더 선택",
                all_folders,
                format_func=lambda f: f"📁 {f} ({count_in_folder(f)}개)",
                key="news_view_folder",
                label_visibility="collapsed",
            )
        with folder_cols[1]:
            if st.button("🧹 광고", use_container_width=True, help="'Keep에 저장' 등 광고 정리"):
                try:
                    from analyze_stock import _is_impactful_news
                    trashed = 0
                    for f in all_folders:
                        items = get_news_in_folder(f)
                        for nitem in items:
                            if not _is_impactful_news(nitem.get("title", "")):
                                trash_news_in_archive(nitem["id"])
                                trashed += 1
                    if trashed:
                        st.success(f"🧹 {trashed}개 정리됨")
                        st.rerun()
                    else:
                        st.info("정리할 거 없음")
                except Exception as e:
                    st.error(f"실패: {e}")

        items_in_folder = get_news_in_folder(selected_folder)
        if not items_in_folder:
            st.info(f"'{selected_folder}' 폴더가 비어있어요. 주식뉴스 탭에서 [📰 뉴스보관] 눌러 저장하세요.")
        else:
            if "news_arc_selected" not in st.session_state:
                st.session_state.news_arc_selected = {}

            # 상단 도구모음
            with st.container(border=True):
                tcols = st.columns([2, 1, 1, 1.4, 1])
                with tcols[0]:
                    st.markdown(f"**📰 {selected_folder} · {len(items_in_folder)}개**")
                with tcols[1]:
                    n_select_all = st.button("☑ 전체선택", use_container_width=True, key="news_arc_sel_all")
                with tcols[2]:
                    n_unselect = st.button("☐ 해제", use_container_width=True, key="news_arc_unsel")
                with tcols[3]:
                    bulk_target_folder = st.selectbox(
                        "→ 폴더",
                        ["(이동 안 함)"] + [f for f in all_folders if f != selected_folder],
                        key="news_arc_bulk_folder",
                        label_visibility="collapsed",
                    )
                    bulk_move_news = st.button("🚚 선택이동", use_container_width=True, key="news_arc_bulk_mv")
                with tcols[4]:
                    bulk_trash_news = st.button("🗑️ 선택휴지통", use_container_width=True, key="news_arc_bulk_trash")

            # 일괄 선택/해제
            if n_select_all:
                for nitem in items_in_folder:
                    iid = nitem.get("id", "")
                    st.session_state[f"news_arc_chk_{iid}"] = True
                    st.session_state.news_arc_selected[iid] = nitem
            if n_unselect:
                for nitem in items_in_folder:
                    iid = nitem.get("id", "")
                    st.session_state[f"news_arc_chk_{iid}"] = False
                st.session_state.news_arc_selected = {}

            # 일괄 폴더 이동
            if bulk_move_news and bulk_target_folder != "(이동 안 함)":
                moved = 0
                for iid in list(st.session_state.news_arc_selected.keys()):
                    if move_news(iid, bulk_target_folder):
                        moved += 1
                st.session_state.news_arc_selected = {}
                if moved:
                    st.success(f"✅ {moved}개 → '{bulk_target_folder}' 이동")
                    st.rerun()
                else:
                    st.warning("선택된 뉴스 없음")

            # 일괄 휴지통
            if bulk_trash_news:
                count = 0
                for iid in list(st.session_state.news_arc_selected.keys()):
                    trash_news_in_archive(iid)
                    count += 1
                st.session_state.news_arc_selected = {}
                if count:
                    st.success(f"🗑️ {count}개 휴지통으로")
                    st.rerun()
                else:
                    st.warning("선택된 뉴스 없음")

            # 한 줄씩 표시
            for nitem in items_in_folder:
                title = nitem.get("title", "")
                link = nitem.get("link", "")
                stock_name = nitem.get("stock_name", "")
                ticker = nitem.get("ticker", "")
                archived_at = nitem.get("archived_at", "")[:16]
                iid = nitem.get("id", "")

                row_cols = st.columns([0.4, 7, 1.2, 0.7])
                with row_cols[0]:
                    chk = st.checkbox(
                        "선택",
                        key=f"news_arc_chk_{iid}",
                        label_visibility="collapsed",
                    )
                    if chk:
                        st.session_state.news_arc_selected[iid] = nitem
                    else:
                        st.session_state.news_arc_selected.pop(iid, None)
                with row_cols[1]:
                    escaped_title = title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
                    if link:
                        line_md = f"📰 **[{escaped_title}]({link})**"
                    else:
                        fallback = f"https://www.google.com/search?q={quote(title)}"
                        line_md = f"📰 **[{escaped_title}]({fallback})** _(검색)_"
                    if stock_name:
                        line_md += f"  ·  {stock_name}({ticker})"
                    line_md += f"  ·  _보관: {archived_at}_"
                    st.markdown(line_md)
                with row_cols[2]:
                    other_folders = [f for f in all_folders if f != selected_folder]
                    if other_folders:
                        target_folder = st.selectbox(
                            "→ 폴더",
                            ["(이동)"] + other_folders,
                            key=f"move_news_{iid}",
                            label_visibility="collapsed",
                        )
                        if target_folder != "(이동)":
                            move_news(iid, target_folder)
                            st.success(f"→ {target_folder}")
                            st.rerun()
                    else:
                        st.caption("폴더 추가 필요")
                with row_cols[3]:
                    if st.button("🗑️", key=f"del_news_{iid}", use_container_width=True, help="휴지통으로"):
                        trash_news_in_archive(iid)
                        st.rerun()

    # ─── 정보 보관 (한 줄 + 일괄 처리) ───
    with sub3:
        try:
            from user_input import get_archived_inputs, unarchive_user_input, trash_user_input as _trash_input
            archived_infos = get_archived_inputs()
        except Exception:
            archived_infos = []

        if not archived_infos:
            st.info("보관된 분석 정보가 없습니다.\n\n새 정보 탭에서 분석 후 [📦 보관함으로] 누르면 여기에 쌓여요.")
        else:
            if "info_arc_selected" not in st.session_state:
                st.session_state.info_arc_selected = {}

            # 컴팩트 도구모음
            ibar = st.columns([1, 1, 1, 1])
            with ibar[0]:
                st.caption(f"💬 **{len(archived_infos)}개**")
            with ibar[1]:
                info_sel_all = st.button("☑ 전체", use_container_width=True, key="info_arc_sel_all")
            with ibar[2]:
                info_bulk_restore = st.button("↩️ 주식뉴스로", use_container_width=True, key="info_arc_restore")
            with ibar[3]:
                info_bulk_trash = st.button("🗑️ 휴지통", use_container_width=True, key="info_arc_trash")

            # 일괄 선택
            if info_sel_all:
                for entry in archived_infos:
                    eid = entry.get("id", "")
                    st.session_state[f"info_arc_chk_{eid}"] = True
                    st.session_state.info_arc_selected[eid] = True

            # 일괄 복원
            if info_bulk_restore:
                count = 0
                for eid in list(st.session_state.info_arc_selected.keys()):
                    unarchive_user_input(eid)
                    count += 1
                st.session_state.info_arc_selected = {}
                if count:
                    st.success(f"✅ {count}개 주식뉴스로 복귀")
                    st.rerun()
                else:
                    st.warning("선택된 항목 없음")

            # 일괄 휴지통
            if info_bulk_trash:
                count = 0
                for eid in list(st.session_state.info_arc_selected.keys()):
                    _trash_input(eid)
                    count += 1
                st.session_state.info_arc_selected = {}
                if count:
                    st.success(f"🗑️ {count}개 휴지통으로")
                    st.rerun()
                else:
                    st.warning("선택된 항목 없음")

            # 한 줄씩 표시
            for entry in archived_infos:
                eid = entry.get("id", "")
                src = entry.get("source", "")[:90]
                archived_at = entry.get("archived_at", entry.get("timestamp", ""))[:16]
                related = entry.get("related_tickers", [])

                row_cols = st.columns([0.4, 8, 0.7, 0.7])
                with row_cols[0]:
                    chk = st.checkbox(
                        "선택",
                        key=f"info_arc_chk_{eid}",
                        label_visibility="collapsed",
                    )
                    if chk:
                        st.session_state.info_arc_selected[eid] = True
                    else:
                        st.session_state.info_arc_selected.pop(eid, None)
                with row_cols[1]:
                    line = f"📥 **{src}**  ·  _{archived_at}_"
                    if related:
                        line += f"  ·  관련: {', '.join(related[:5])}"
                    st.markdown(line)
                    with st.expander("분석 보기"):
                        st.markdown(entry.get("analysis", ""))
                with row_cols[2]:
                    if st.button("↩️", key=f"unarc_inf_{eid}", use_container_width=True, help="주식뉴스로 복귀"):
                        unarchive_user_input(eid)
                        st.rerun()
                with row_cols[3]:
                    if st.button("🗑️", key=f"del_arc_inf_{eid}", use_container_width=True, help="휴지통"):
                        _trash_input(eid)
                        st.rerun()

    # ─── 휴지통 ───
    with sub4:
        try:
            from archive_manager import (
                get_trashed_news,
                restore_news as _restore_news,
                permanent_delete as _perma_news,
                empty_trash_older_than,
                count_trashed,
                restore_all_trashed_news,
                empty_trash_all,
            )
        except Exception as e:
            st.error(f"휴지통 모듈 로드 실패: {e}")
            get_trashed_news = lambda: []
            _restore_news = lambda *a, **k: None
            _perma_news = lambda *a, **k: None
            empty_trash_older_than = lambda days: 0
            count_trashed = lambda: 0
            restore_all_trashed_news = lambda: 0
            empty_trash_all = lambda: 0

        try:
            from user_input import (
                get_trashed_inputs,
                restore_user_input,
                delete_user_input as _perma_input,
                restore_all_trashed_inputs,
                empty_inputs_trash,
            )
        except Exception:
            get_trashed_inputs = lambda: []
            restore_user_input = lambda *a, **k: None
            _perma_input = lambda *a, **k: None
            restore_all_trashed_inputs = lambda: 0
            empty_inputs_trash = lambda: 0

        trashed_news = get_trashed_news()
        trashed_inputs = get_trashed_inputs()
        total_trash = len(trashed_news) + len(trashed_inputs)

        st.caption(
            f"🗑️ 휴지통 · 뉴스 {len(trashed_news)}개 · 정보 {len(trashed_inputs)}개 · "
            f"기본적으로 30일 후 자동 영구삭제. 그 전엔 모두 복원 가능."
        )

        # 세션 상태 — 휴지통 체크박스
        if "trash_news_selected" not in st.session_state:
            st.session_state.trash_news_selected = {}
        if "trash_input_selected" not in st.session_state:
            st.session_state.trash_input_selected = {}

        # ─── 상단 도구모음 ───
        with st.container(border=True):
            tcols = st.columns([2, 1, 1, 1, 1])
            with tcols[0]:
                st.markdown("**휴지통 일괄 작업**")
            with tcols[1]:
                trash_select_all = st.button("☑ 전체선택", use_container_width=True, key="trash_sel_all")
            with tcols[2]:
                trash_unselect = st.button("☐ 해제", use_container_width=True, key="trash_unsel")
            with tcols[3]:
                bulk_restore = st.button("↩️ 선택복원", use_container_width=True, key="bulk_restore_trash", type="secondary")
            with tcols[4]:
                bulk_perma = st.button("❌ 선택영구삭제", use_container_width=True, key="bulk_perma_trash")

            # 위험한 일괄 작업 (확인 필요)
            danger_cols = st.columns([1, 1, 3])
            with danger_cols[0]:
                if st.button("↩️ 모두 복원", use_container_width=True, help="휴지통 전체를 한 번에 복원"):
                    n_count = restore_all_trashed_news()
                    i_count = restore_all_trashed_inputs()
                    st.session_state.trash_news_selected = {}
                    st.session_state.trash_input_selected = {}
                    st.success(f"✅ 복원: 뉴스 {n_count}개 + 정보 {i_count}개")
                    st.rerun()
            with danger_cols[1]:
                # 두 단계 영구삭제 (한 번 더 확인)
                if "confirm_empty_trash" not in st.session_state:
                    st.session_state.confirm_empty_trash = False
                if not st.session_state.confirm_empty_trash:
                    if st.button("🔥 휴지통 비우기", use_container_width=True, help="휴지통 전체 영구삭제 (복구 불가)"):
                        st.session_state.confirm_empty_trash = True
                        st.rerun()
                else:
                    if st.button("⚠️ 정말? 한번 더 누르면 영구삭제", use_container_width=True, type="primary"):
                        n_del = empty_trash_all()
                        i_del = empty_inputs_trash()
                        st.session_state.confirm_empty_trash = False
                        st.success(f"🔥 영구삭제: 뉴스 {n_del}개 + 정보 {i_del}개")
                        st.rerun()
                    if st.button("취소", use_container_width=True):
                        st.session_state.confirm_empty_trash = False
                        st.rerun()

        # 자동 정리 설정
        with st.expander("⚙️ 자동 정리 (보너스)", expanded=False):
            ac_cols = st.columns([3, 1])
            with ac_cols[0]:
                cleanup_days = st.number_input(
                    "N일 이상 된 항목 영구 삭제",
                    min_value=1, max_value=365, value=30, step=1,
                )
                st.caption("앱 시작 시 자동으로 한 번 정리됩니다.")
            with ac_cols[1]:
                if st.button("🧹 지금 정리", use_container_width=True):
                    deleted = empty_trash_older_than(cleanup_days)
                    st.success(f"{deleted}개 영구 삭제됨")
                    st.rerun()

        if total_trash == 0:
            st.info("휴지통이 비어있어요.")
        else:
            # ─── 일괄 선택/해제 처리 ───
            if trash_select_all:
                for nitem in trashed_news[:200]:
                    nid = nitem.get("id", "")
                    st.session_state[f"trash_chk_news_{nid}"] = True
                    st.session_state.trash_news_selected[nid] = True
                for entry in trashed_inputs[:200]:
                    eid = entry.get("id", "")
                    st.session_state[f"trash_chk_inp_{eid}"] = True
                    st.session_state.trash_input_selected[eid] = True
            if trash_unselect:
                for nitem in trashed_news[:200]:
                    nid = nitem.get("id", "")
                    st.session_state[f"trash_chk_news_{nid}"] = False
                for entry in trashed_inputs[:200]:
                    eid = entry.get("id", "")
                    st.session_state[f"trash_chk_inp_{eid}"] = False
                st.session_state.trash_news_selected = {}
                st.session_state.trash_input_selected = {}

            # ─── 일괄 복원 처리 ───
            if bulk_restore:
                n_restored = 0
                for nid in list(st.session_state.trash_news_selected.keys()):
                    _restore_news(nid)
                    n_restored += 1
                i_restored = 0
                for eid in list(st.session_state.trash_input_selected.keys()):
                    restore_user_input(eid)
                    i_restored += 1
                st.session_state.trash_news_selected = {}
                st.session_state.trash_input_selected = {}
                if n_restored or i_restored:
                    st.success(f"✅ 복원: 뉴스 {n_restored}개 + 정보 {i_restored}개")
                    st.rerun()
                else:
                    st.warning("선택된 항목 없음")

            # ─── 일괄 영구삭제 처리 ───
            if bulk_perma:
                n_del = 0
                for nid in list(st.session_state.trash_news_selected.keys()):
                    _perma_news(nid)
                    n_del += 1
                i_del = 0
                for eid in list(st.session_state.trash_input_selected.keys()):
                    _perma_input(eid)
                    i_del += 1
                st.session_state.trash_news_selected = {}
                st.session_state.trash_input_selected = {}
                if n_del or i_del:
                    st.success(f"🔥 영구삭제: 뉴스 {n_del}개 + 정보 {i_del}개")
                    st.rerun()
                else:
                    st.warning("선택된 항목 없음")

            # ─── 뉴스 휴지통 — 한 줄씩 ───
            if trashed_news:
                st.markdown(f"### 📰 뉴스 휴지통 ({len(trashed_news)}개)")
                for nitem in trashed_news[:200]:
                    title = nitem.get("title", "")
                    link = nitem.get("link", "")
                    stock_name = nitem.get("stock_name", "")
                    ticker = nitem.get("ticker", "")
                    trashed_at = nitem.get("trashed_at", "")[:16]
                    nid = nitem.get("id", "")

                    row_cols = st.columns([0.4, 7, 0.7, 0.7])
                    with row_cols[0]:
                        chk = st.checkbox(
                            "선택",
                            key=f"trash_chk_news_{nid}",
                            label_visibility="collapsed",
                        )
                        if chk:
                            st.session_state.trash_news_selected[nid] = True
                        else:
                            st.session_state.trash_news_selected.pop(nid, None)
                    with row_cols[1]:
                        escaped_title = title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
                        if link:
                            line_md = f"📰 **[{escaped_title}]({link})**"
                        else:
                            fallback = f"https://www.google.com/search?q={quote(title)}"
                            line_md = f"📰 **[{escaped_title}]({fallback})** _(검색)_"
                        if stock_name:
                            line_md += f"  ·  {stock_name}({ticker})"
                        line_md += f"  ·  _삭제: {trashed_at}_"
                        st.markdown(line_md)
                    with row_cols[2]:
                        if st.button("↩️", key=f"restore_news_{nid}", use_container_width=True, help="이거만 복원"):
                            _restore_news(nid)
                            st.rerun()
                    with row_cols[3]:
                        if st.button("❌", key=f"perma_news_{nid}", use_container_width=True, help="이거만 영구삭제"):
                            _perma_news(nid)
                            st.rerun()

            # ─── 정보 휴지통 — 한 줄씩 ───
            if trashed_inputs:
                st.markdown(f"### 💬 정보 휴지통 ({len(trashed_inputs)}개)")
                for entry in trashed_inputs[:100]:
                    eid = entry.get("id", "")
                    src = entry.get("source", "")[:80]
                    trashed_at = entry.get("trashed_at", "")[:16]
                    row_cols = st.columns([0.4, 7, 0.7, 0.7])
                    with row_cols[0]:
                        chk = st.checkbox(
                            "선택",
                            key=f"trash_chk_inp_{eid}",
                            label_visibility="collapsed",
                        )
                        if chk:
                            st.session_state.trash_input_selected[eid] = True
                        else:
                            st.session_state.trash_input_selected.pop(eid, None)
                    with row_cols[1]:
                        st.markdown(f"📥 **{src}**  ·  _삭제: {trashed_at}_")
                        with st.expander("분석 결과 보기"):
                            st.markdown(entry.get("analysis", ""))
                    with row_cols[2]:
                        if st.button("↩️", key=f"restore_inp_{eid}", use_container_width=True, help="이거만 복원"):
                            restore_user_input(eid)
                            st.rerun()
                    with row_cols[3]:
                        if st.button("❌", key=f"perma_inp_{eid}", use_container_width=True, help="이거만 영구삭제"):
                            _perma_input(eid)
                            st.rerun()
