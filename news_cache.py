"""
news_cache.py — 뉴스만 빠르게 새로 받아 캐싱

종목 풀 재분석 안 하고 (Claude 호출 X) 뉴스만 새로 받음.
주식뉴스 탭의 [🔄 뉴스 새로 받기] 버튼이 호출.

비용: 0원 (Naver만 호출)
시간: 50종목 약 1~2분
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
WATCHLIST_PATH = PROJECT_ROOT / "watchlist.csv"
NEWS_CACHE_PATH = DATA_DIR / "news_cache.json"


def refresh_all_news(progress_callback=None) -> dict:
    """모든 watchlist 종목 뉴스만 새로 받기. Claude 호출 X.
    progress_callback(current_idx, total, name) 으로 진행 표시 가능.
    """
    from analyze_stock import fetch_naver_news

    if not WATCHLIST_PATH.exists():
        return {"error": "watchlist.csv 없음"}

    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": ""})
    df["ticker"] = df["ticker"].str.zfill(6)
    df = df.drop_duplicates(subset=["ticker"])
    df = df[df["ticker"].str.strip() != ""]

    cache = {
        "updated_at": datetime.now().isoformat(),
        "count": 0,
        "by_ticker": {},
    }

    total = len(df)
    total_news = 0
    for i, (_, row) in enumerate(df.iterrows()):
        ticker = str(row["ticker"]).zfill(6)
        name = row["name"]
        if progress_callback:
            progress_callback(i, total, name)
        try:
            news = fetch_naver_news(name, count=8)
            print(f"[{i+1}/{total}] {name} ({ticker}): {len(news)}개 뉴스")
            total_news += len(news)
        except Exception as e:
            print(f"[{i+1}/{total}] {name} ({ticker}): 실패 — {e}")
            news = []
        cache["by_ticker"][ticker] = {
            "name": name,
            "group": row.get("group", ""),
            "news": news,
        }

    cache["count"] = total_news
    print(f"\n✅ 뉴스 갱신 완료. 총 {total_news}개 ({total}종목)")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return cache


def load_news_cache() -> dict | None:
    """뉴스 캐시 로드. 없으면 None."""
    if NEWS_CACHE_PATH.exists():
        try:
            return json.loads(NEWS_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def get_cache_age_minutes() -> int | None:
    """캐시가 몇 분 전에 갱신됐는지. None이면 캐시 없음."""
    cache = load_news_cache()
    if not cache or "updated_at" not in cache:
        return None
    try:
        updated = datetime.fromisoformat(cache["updated_at"])
        delta = datetime.now() - updated
        return int(delta.total_seconds() / 60)
    except Exception:
        return None
