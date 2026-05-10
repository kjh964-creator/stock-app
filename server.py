"""
server.py — FastAPI 백엔드 서버 (v0.5)

모바일 앱(또는 다른 클라이언트)이 호출할 REST API.

엔드포인트:
  GET  /                               헬스체크
  GET  /watchlist                      관심종목 전체 (그룹 포함)
  GET  /watchlist/groups               그룹 목록만
  GET  /watchlist/{group}              특정 그룹 종목들
  GET  /stock/{ticker}                 종목 상세 분석 (마크다운 + 메타)
  GET  /stock/{ticker}/raw             원본 데이터 (시세·재무, JSON)
  GET  /news                           모든 종목 뉴스 통합
  GET  /memo/{ticker}                  메모 조회
  POST /memo/{ticker}                  메모 저장 (body: {"text": "..."})
  GET  /archive                        보관함 목록
  POST /archive                        보관 추가 (body: {"ticker", "name"})
  DELETE /archive/{ticker}             보관 해제

실행:
    uvicorn server:app --reload --port 8000

브라우저에서 http://localhost:8000/docs 접속 → 인터랙티브 API 문서

향후 클라우드 배포(Railway/Fly.io) 후 → Flutter 앱이 이 서버에 호출
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# analyze_stock 에서 함수·경로 재사용
from analyze_stock import (
    PROJECT_ROOT,
    REPORT_DIR,
    WATCHLIST_PATH,
    fetch_price_data,
    fetch_naver_news,
    detect_market,
    resolve_ticker,
    analyze_one,
)

DATA_DIR = PROJECT_ROOT / "data"
ARCHIVE_PATH = DATA_DIR / "archive.json"
MEMO_PATH = DATA_DIR / "memos.json"

# ─────────────────────────────────────────────────────────────────────
# 앱 초기화
# ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="주식정보 백엔드 API",
    description="Claude 기반 한국 주식 자동 분석 API",
    version="0.5.0",
)

# CORS — 모바일 앱·웹앱 어디서든 호출 가능하게
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────
# Pydantic 모델
# ─────────────────────────────────────────────────────────────────────
class MemoIn(BaseModel):
    text: str


class ArchiveIn(BaseModel):
    ticker: str
    name: str


class StockSummary(BaseModel):
    ticker: str
    name: str
    market: str
    is_etf: bool
    groups: list[str]


# ─────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────
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


def extract_summary_from_report(report_path: Path) -> dict:
    if not report_path.exists():
        return {}
    text = report_path.read_text(encoding="utf-8")
    summary = {}
    m_price = re.search(r"\*\*([\d,]+)원\*\*\s*([▲▼])([\d,]+)원\s*\(([+-]?\d+\.\d+)%\)", text)
    if m_price:
        summary["price"] = int(m_price.group(1).replace(",", ""))
        summary["arrow"] = m_price.group(2)
        summary["change"] = int(m_price.group(3).replace(",", ""))
        summary["change_pct"] = float(m_price.group(4))
    return summary


def extract_news_from_report(report_path: Path) -> list[dict]:
    if not report_path.exists():
        return []
    text = report_path.read_text(encoding="utf-8")
    m = re.search(r"## 📰 최근 뉴스\s*\n(.+?)(?=\n---|\n## |\Z)", text, re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    news = []
    for line in section.split("\n"):
        line = line.strip()
        m_link = re.match(r"^\d+\.\s*\[([^\]]+)\]\(([^)]+)\)", line)
        if m_link:
            news.append({"title": m_link.group(1), "link": m_link.group(2)})
            continue
        m_plain = re.match(r"^\d+\.\s+(.+)", line)
        if m_plain:
            news.append({"title": m_plain.group(1), "link": ""})
    return news


# ─────────────────────────────────────────────────────────────────────
# 헬스체크
# ─────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "name": "주식정보 백엔드",
        "version": "0.5.0",
        "time": datetime.now().isoformat(),
        "docs": "/docs",
    }


# ─────────────────────────────────────────────────────────────────────
# 관심종목
# ─────────────────────────────────────────────────────────────────────
@app.get("/watchlist")
def get_watchlist():
    """전체 관심종목 (그룹 정보 포함)."""
    if not WATCHLIST_PATH.exists():
        raise HTTPException(404, "watchlist.csv 없음")
    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": "", "is_etf": False, "note": ""})

    items = []
    for _, row in df.iterrows():
        ticker = str(row["ticker"]).zfill(6) if row["ticker"] else ""
        items.append({
            "group": row["group"],
            "name": row["name"],
            "ticker": ticker,
            "market": row.get("market", ""),
            "is_etf": str(row.get("is_etf", "False")).lower() == "true",
            "note": row.get("note", ""),
        })
    return {"count": len(items), "items": items}


@app.get("/watchlist/groups")
def get_watchlist_groups():
    df = pd.read_csv(WATCHLIST_PATH)
    groups = sorted(df["group"].dropna().unique().tolist())
    return {"groups": groups}


@app.get("/watchlist/{group}")
def get_watchlist_by_group(group: str):
    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df[df["group"] == group].fillna({"ticker": "", "is_etf": False, "note": ""})
    if df.empty:
        raise HTTPException(404, f"그룹 '{group}' 없음")

    items = []
    for _, row in df.iterrows():
        ticker = str(row["ticker"]).zfill(6) if row["ticker"] else ""
        latest = find_latest_report(ticker, row["name"]) if ticker else None
        summary = extract_summary_from_report(latest) if latest else {}
        items.append({
            "name": row["name"],
            "ticker": ticker,
            "market": row.get("market", ""),
            "is_etf": str(row.get("is_etf", "False")).lower() == "true",
            "summary": summary,
            "has_report": latest is not None,
        })
    return {"group": group, "count": len(items), "items": items}


# ─────────────────────────────────────────────────────────────────────
# 종목 상세
# ─────────────────────────────────────────────────────────────────────
@app.get("/stock/{ticker}")
def get_stock_detail(ticker: str, refresh: bool = False):
    """종목 상세 분석. refresh=true 면 즉시 재분석."""
    resolved = resolve_ticker(ticker)
    if not resolved:
        raise HTTPException(404, f"종목 '{ticker}' 찾을 수 없음")
    ticker, name, market = resolved

    if refresh:
        analyze_one(ticker, name, market, with_claude=True, verbose=False)

    report_path = find_latest_report(ticker, name)
    if not report_path:
        raise HTTPException(404, f"리포트 없음. /stock/{ticker}?refresh=true 로 생성 가능")

    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "report_md": report_path.read_text(encoding="utf-8"),
        "report_file": report_path.name,
        "summary": extract_summary_from_report(report_path),
        "news": extract_news_from_report(report_path),
    }


@app.get("/stock/{ticker}/raw")
def get_stock_raw(ticker: str):
    """원본 시세·재무 데이터 (Claude 분석 없음, 빠름)."""
    resolved = resolve_ticker(ticker)
    if not resolved:
        raise HTTPException(404, f"종목 '{ticker}' 찾을 수 없음")
    ticker, name, market = resolved

    price_data = fetch_price_data(ticker)
    if not price_data:
        raise HTTPException(503, "시세 데이터 수집 실패")

    # price_history 는 무거우니 끝 30일치만
    if "price_history" in price_data:
        price_data["price_history"] = price_data["price_history"][-30:]

    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "data": price_data,
    }


# ─────────────────────────────────────────────────────────────────────
# 뉴스
# ─────────────────────────────────────────────────────────────────────
@app.get("/news")
def get_all_news(limit: int = 50):
    """모든 종목 뉴스 통합 피드."""
    if not WATCHLIST_PATH.exists():
        return {"news": []}
    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": ""})

    seen_titles = set()
    all_news = []
    for _, row in df.iterrows():
        ticker = str(row["ticker"]).zfill(6) if row["ticker"] else ""
        if not ticker:
            continue
        report_path = find_latest_report(ticker, row["name"])
        if not report_path:
            continue
        for n in extract_news_from_report(report_path):
            if n["title"] in seen_titles:
                continue
            seen_titles.add(n["title"])
            n["ticker"] = ticker
            n["stock_name"] = row["name"]
            all_news.append(n)
            if len(all_news) >= limit:
                break
        if len(all_news) >= limit:
            break

    return {"count": len(all_news), "news": all_news}


@app.get("/news/{ticker}")
def get_news_for_ticker(ticker: str, refresh: bool = False):
    """특정 종목 최신 뉴스. refresh=true 면 Naver에서 즉시 가져옴."""
    resolved = resolve_ticker(ticker)
    if not resolved:
        raise HTTPException(404, "종목 없음")
    ticker, name, _ = resolved

    if refresh:
        news = fetch_naver_news(name, count=10)
    else:
        report_path = find_latest_report(ticker, name)
        news = extract_news_from_report(report_path) if report_path else []

    return {"ticker": ticker, "name": name, "count": len(news), "news": news}


# ─────────────────────────────────────────────────────────────────────
# 메모
# ─────────────────────────────────────────────────────────────────────
@app.get("/memo/{ticker}")
def get_memo(ticker: str):
    memos = load_json(MEMO_PATH, {})
    return memos.get(ticker, {"text": "", "updated_at": ""})


@app.post("/memo/{ticker}")
def save_memo(ticker: str, memo: MemoIn):
    memos = load_json(MEMO_PATH, {})
    memos[ticker] = {
        "text": memo.text,
        "updated_at": datetime.now().isoformat(),
    }
    save_json(MEMO_PATH, memos)
    return {"ok": True, "ticker": ticker}


# ─────────────────────────────────────────────────────────────────────
# 보관함
# ─────────────────────────────────────────────────────────────────────
@app.get("/archive")
def get_archive():
    items = load_json(ARCHIVE_PATH, [])
    # 각 종목의 가격 정보도 같이
    enriched = []
    for item in items:
        ticker = item["ticker"]
        name = item["name"]
        latest = find_latest_report(ticker, name)
        item["summary"] = extract_summary_from_report(latest) if latest else {}
        item["has_report"] = latest is not None
        enriched.append(item)
    return {"count": len(enriched), "items": enriched}


@app.post("/archive")
def add_archive(item: ArchiveIn):
    items = load_json(ARCHIVE_PATH, [])
    if any(a["ticker"] == item.ticker for a in items):
        return {"ok": False, "reason": "이미 보관됨"}
    items.append({
        "ticker": item.ticker,
        "name": item.name,
        "added_at": datetime.now().isoformat(),
    })
    save_json(ARCHIVE_PATH, items)
    return {"ok": True}


@app.delete("/archive/{ticker}")
def remove_archive(ticker: str):
    items = load_json(ARCHIVE_PATH, [])
    new_items = [a for a in items if a["ticker"] != ticker]
    save_json(ARCHIVE_PATH, new_items)
    return {"ok": True, "removed": len(items) - len(new_items)}


# ─────────────────────────────────────────────────────────────────────
# 분석 트리거
# ─────────────────────────────────────────────────────────────────────
@app.post("/analyze/{ticker}")
def trigger_analyze(ticker: str):
    """종목 즉시 분석 트리거. Claude 호출하므로 30~60초 걸림."""
    resolved = resolve_ticker(ticker)
    if not resolved:
        raise HTTPException(404, "종목 없음")
    ticker, name, market = resolved
    output_path = analyze_one(ticker, name, market, with_claude=True, verbose=False)
    if not output_path:
        raise HTTPException(503, "분석 실패")
    return {"ok": True, "report_file": output_path.name}
