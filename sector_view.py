"""
sector_view.py — 섹터 뷰 데이터 생성

전체 watchlist (관심1~5 + 섹터대표) 의 종목을 섹터별로 자동 분류.
종목마다 출처(어느 그룹에 속하는지) 정보 추가.

명칭 정리:
- "섹터": 글로벌 표준 (반도체 섹터, 금융 섹터 등) — 일반인에게 친숙
- 한국 거래소 공식 용어로는 "업종"
- 더 좁은 의미는 "테마"지만 시장 트렌드 의미
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from sector_leaders import SECTOR_LEADERS, SECTOR_GROUP_NAME

PROJECT_ROOT = Path(__file__).parent
WATCHLIST_PATH = PROJECT_ROOT / "watchlist.csv"

# 빠른 룩업용: ticker → sector
_TICKER_TO_SECTOR: dict[str, str] = {}
for sector, stocks in SECTOR_LEADERS.items():
    for ticker, _name, _market in stocks:
        _TICKER_TO_SECTOR[ticker.zfill(6)] = sector

# 섹터 표시 순서 (시장 영향도 큰 순)
SECTOR_ORDER = [
    "반도체",
    "2차전지·배터리",
    "자동차",
    "바이오·제약",
    "인터넷·게임",
    "금융·은행",
    "통신·미디어",
    "조선·방산",
    "화학·정유",
    "철강·금속",
    "식음료·유통",
    "ETF",
    "기타",
]


def classify_ticker(ticker: str, name: str = "", note: str = "") -> str:
    """ticker → sector. 매핑에 없으면 note 활용 → 그래도 없으면 '기타'."""
    t = (ticker or "").zfill(6)
    if t in _TICKER_TO_SECTOR:
        return _TICKER_TO_SECTOR[t]
    # CSV 의 note 열에 섹터명이 있을 수 있음 (섹터대표 그룹 행에 적힌 것)
    if note and note.strip() in SECTOR_ORDER:
        return note.strip()
    return "기타"


def build_sector_view() -> dict[str, list[dict]]:
    """전체 watchlist 를 섹터별로 분류.
    Returns: {sector_name: [{ticker, name, market, is_etf, groups: [...], is_leader: bool}]}
    """
    if not WATCHLIST_PATH.exists():
        return {}

    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": "", "is_etf": False, "note": "", "market": ""})
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    # ticker → 통합 정보
    by_ticker: dict[str, dict] = {}
    for _, row in df.iterrows():
        t = row["ticker"]
        if not t.strip():
            continue
        nm = row["name"]
        mkt = row.get("market", "") or "KOSPI"
        is_etf = str(row.get("is_etf", "False")).lower() == "true"
        grp = row.get("group", "")
        note = row.get("note", "")

        if t not in by_ticker:
            by_ticker[t] = {
                "ticker": t,
                "name": nm,
                "market": mkt,
                "is_etf": is_etf,
                "groups": set(),
                "is_leader": False,
                "note": note,
            }

        if grp == SECTOR_GROUP_NAME:
            by_ticker[t]["is_leader"] = True
            # note 에 적힌 섹터를 신뢰 (섹터대표 행의 note)
            if note and not by_ticker[t].get("note"):
                by_ticker[t]["note"] = note
        else:
            by_ticker[t]["groups"].add(grp)

    # 섹터별로 분류
    sectors: dict[str, list[dict]] = {s: [] for s in SECTOR_ORDER}
    for t, info in by_ticker.items():
        if info["is_etf"]:
            sec = "ETF"
        else:
            sec = classify_ticker(t, info["name"], info.get("note", ""))
        if sec not in sectors:
            sectors[sec] = []
        info["groups"] = sorted(info["groups"])
        sectors[sec].append(info)

    # 정렬: 섹터대표 먼저, 그 다음 ticker 순
    for sec in sectors:
        sectors[sec].sort(key=lambda x: (not x["is_leader"], x["ticker"]))

    # 빈 섹터 제거
    return {s: items for s, items in sectors.items() if items}


def count_sectors() -> dict[str, int]:
    """섹터별 종목 개수."""
    view = build_sector_view()
    return {s: len(items) for s, items in view.items()}
