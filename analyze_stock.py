"""
analyze_stock.py — 단일 종목 분석 스크립트 (v0.2)

사용법:
    python analyze_stock.py 005930          # 티커로 분석
    python analyze_stock.py 삼성전자          # 종목명으로 분석 (CSV에 등록되어 있어야 함)

결과:
    data/reports/{ticker}_{name}_{날짜}.md 파일로 분석 리포트 저장

요구사항:
    - .env 파일에 ANTHROPIC_API_KEY 설정
    - pip install -r requirements.txt

v0.2 변경사항:
    - Naver 뉴스 자동 수집 (5~10개)
    - 추정 PER / 추정 EPS 표시
    - 한국 단위 포맷 개선 (1,569.7조원 / 6,564원 / 40.9배)
    - analyze_one() 함수로 분리 (analyze_all.py 에서 재사용)
"""

from __future__ import annotations

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pykrx import stock
import anthropic

# ─────────────────────────────────────────────────────────────────────
# 0. 환경 설정
# ─────────────────────────────────────────────────────────────────────
load_dotenv()

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
REPORT_DIR = DATA_DIR / "reports"
DEBUG_DIR = DATA_DIR / "debug"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

WATCHLIST_PATH = PROJECT_ROOT / "watchlist.csv"

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

if not ANTHROPIC_KEY:
    print("❌ ANTHROPIC_API_KEY가 .env 파일에 없습니다.")
    print("   1) .env.example 을 .env 로 복사")
    print("   2) https://console.anthropic.com/ 에서 키 발급 후 입력")
    sys.exit(1)

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# ─────────────────────────────────────────────────────────────────────
# 1. 종목명 ↔ 티커 변환
# ─────────────────────────────────────────────────────────────────────
def resolve_ticker(query: str) -> Optional[tuple[str, str, str]]:
    """입력값(티커 6자리 or 종목명) → (ticker, name, market)."""
    query = query.strip()

    if query.isdigit() and len(query) == 6:
        try:
            name = stock.get_market_ticker_name(query)
            market = detect_market(query)
            return (query, name, market)
        except Exception:
            return None

    if not WATCHLIST_PATH.exists():
        print(f"⚠️  {WATCHLIST_PATH} 파일이 없습니다.")
        return None

    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    matches = df[df["name"].astype(str).str.contains(query, na=False)]

    if matches.empty:
        return None

    row = matches.iloc[0]
    ticker = str(row["ticker"]).zfill(6) if pd.notna(row["ticker"]) else None
    name = row["name"]
    market = str(row.get("market", "Unknown"))

    if not ticker or ticker == "nan":
        print(f"⚠️  '{name}' 의 티커가 등록되어 있지 않습니다. CSV 확인 필요.")
        return None

    return (ticker, name, market)


_market_ticker_cache: dict[str, str] = {}


def detect_market(ticker: str) -> str:
    """KOSPI/KOSDAQ 판별. watchlist.csv 우선."""
    if WATCHLIST_PATH.exists():
        try:
            df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
            if df["ticker"].notna().any():
                df["ticker"] = df["ticker"].fillna("").str.zfill(6)
            row = df[df["ticker"] == ticker]
            if not row.empty:
                m = str(row.iloc[0].get("market", ""))
                if m in ("KOSPI", "KOSDAQ"):
                    return m
        except Exception:
            pass

    if not _market_ticker_cache:
        try:
            for t in stock.get_market_ticker_list(market="KOSPI"):
                _market_ticker_cache[t] = "KOSPI"
            for t in stock.get_market_ticker_list(market="KOSDAQ"):
                _market_ticker_cache[t] = "KOSDAQ"
        except Exception:
            return "Unknown"
    return _market_ticker_cache.get(ticker, "Unknown")


# ─────────────────────────────────────────────────────────────────────
# 2. 데이터 수집 — 시세·재무·뉴스
# ─────────────────────────────────────────────────────────────────────
def _parse_number(s: str) -> Optional[float]:
    """문자열에서 숫자만 추출."""
    if not s:
        return None
    s = str(s).strip().replace(",", "").replace("\xa0", "")
    if s in ("", "N/A", "-", "—"):
        return None
    m = re.search(r"-?\d+\.?\d*", s)
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None


def parse_korean_money(text: str) -> int:
    """한국 단위 표기(조/억) → 원 단위.
    "1,569조 7,258억" → 1.5697e15
    "1,569,140억"     → 1.569e14
    "5,000"           → 5e11 (단위 없으면 억)
    """
    if not text:
        return 0
    total = 0
    text = str(text)

    cho_match = re.search(r"([\d,]+(?:\.\d+)?)\s*조", text)
    if cho_match:
        try:
            val = float(cho_match.group(1).replace(",", ""))
            total += int(val * 1_000_000_000_000)
        except ValueError:
            pass
        rest = text[cho_match.end():]
        eok_match = re.search(r"([\d,]+(?:\.\d+)?)\s*억", rest)
        if eok_match:
            try:
                val = float(eok_match.group(1).replace(",", ""))
                total += int(val * 100_000_000)
            except ValueError:
                pass
    else:
        eok_match = re.search(r"([\d,]+(?:\.\d+)?)\s*억", text)
        if eok_match:
            try:
                val = float(eok_match.group(1).replace(",", ""))
                total = int(val * 100_000_000)
            except ValueError:
                pass
        else:
            num = _parse_number(text)
            if num:
                total = int(num * 100_000_000)
    return total


def format_market_cap(won: int) -> str:
    """원 단위 시가총액 → 사람이 읽기 좋은 형식.
    1.5697e15 → "1,569.7조원"
    1.569e11  → "1,569억원"
    """
    if won >= 1_000_000_000_000:  # 1조 이상
        cho = won / 1_000_000_000_000
        return f"{cho:,.1f}조원"
    elif won >= 100_000_000:
        eok = won / 100_000_000
        return f"{eok:,.0f}억원"
    elif won > 0:
        return f"{won:,.0f}원"
    return "N/A"


def fetch_from_naver_api(ticker: str) -> dict:
    """네이버 주식 통합 API (JSON)."""
    result = {
        "market_cap_won": 0,
        "per": None,
        "pbr": None,
        "eps": None,
        "bps": None,
        "div_yield": None,
        "cns_per": None,   # 추정 PER (forward)
        "cns_eps": None,   # 추정 EPS (forward)
        "dividend": None,  # 주당 배당금
        "foreign_rate": None,  # 외국인 보유율
    }

    url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
    headers = {**NAVER_HEADERS, "Referer": "https://m.stock.naver.com/"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        debug_path = DEBUG_DIR / f"naver_api_{ticker}.json"
        debug_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        code_map = {
            "per": "per",
            "pbr": "pbr",
            "eps": "eps",
            "bps": "bps",
            "dividendYieldRatio": "div_yield",
            "cnsPer": "cns_per",
            "cnsEps": "cns_eps",
            "dividend": "dividend",
            "foreignRate": "foreign_rate",
        }

        for info in data.get("totalInfos", []) or []:
            code = info.get("code") or ""
            value = info.get("value") or ""

            if code == "marketValue":
                result["market_cap_won"] = parse_korean_money(value)
            elif code in code_map:
                target_key = code_map[code]
                val = _parse_number(str(value))
                if val is not None:
                    result[target_key] = val

    except Exception as e:
        print(f"   ⚠️ Naver API 조회 실패: {e}")

    return result


# 주가 영향 없는 광고·잡다한 뉴스 제외용 필터
_SPAM_KEYWORDS = [
    # 채용·취업
    "채용", "구인", "모집공고", "공채", "직원모집", "신입사원",
    "일자리", "취업박람회", "직무 설명회",
    # 이벤트·광고
    "이벤트", "추첨", "경품", "할인", "특가", "쿠폰", "프로모션",
    "[광고]", "[AD]", "(광고)", "[프로모션]",
    # 네이버/포털 시스템 메시지
    "Keep에 저장", "Keep에 바로가기", "Keep으로",
    "스크랩", "북마크",
    "관련 검색어",
    # 사진·포토 게시판
    "포토", "[사진]", "[화보]", "[포토뉴스]",
    # 운세·생활
    "오늘의 운세", "토정비결", "별자리 운세",
    # 광고성 헤드라인
    "1위 차지", "최고의 ", "베스트 ",
    "콘서트", "공연 안내", "팬미팅",
    # 일반 동영상/방송
    "[영상]", "[VOD]",
]

_SPAM_SUBSTRINGS = [
    "Keep",  # "Keep에 저장", "Keep으로 보내기" 등 모든 변형
]


def _is_impactful_news(title: str) -> bool:
    """주가 영향 있을만한 뉴스인지 휴리스틱 판단. 광고·채용·잡담 제외."""
    if not title:
        return False
    if len(title) < 8:
        return False
    for kw in _SPAM_KEYWORDS:
        if kw in title:
            return False
    # 부분 일치 (Keep 같은 거)
    for sub in _SPAM_SUBSTRINGS:
        if sub in title and ("저장" in title or "바로가기" in title or "스크랩" in title):
            return False
    # 너무 일반적인 시황 헤드라인
    generic_starts = ("주간 ", "오늘의 ", "[주간]", "[일일]", "주말 ")
    if title.startswith(generic_starts):
        return False
    return True


def fetch_naver_news(stock_name: str, count: int = 8) -> list[dict]:
    """뉴스 가져오기. 우선순위: Naver 공식 API → Naver 스크래핑 → Google News RSS.
    광고·채용 같은 비-영향 뉴스는 자동 필터.
    Returns: [{title, link, summary, date}, ...]
    """
    # 더 많이 가져와서 필터 후 count 만큼 반환
    raw_count = count * 3

    # 1순위: Naver 공식 API
    if NAVER_CLIENT_ID and NAVER_CLIENT_SECRET:
        results = _fetch_news_via_api(stock_name, raw_count)
        if results:
            return [r for r in results if _is_impactful_news(r.get("title", ""))][:count]

    # 2순위: Naver 스크래핑
    results = _fetch_news_via_search(stock_name, raw_count)
    if results:
        return [r for r in results if _is_impactful_news(r.get("title", ""))][:count]

    # 3순위: Google News RSS
    results = _fetch_news_via_google(stock_name, raw_count)
    return [r for r in results if _is_impactful_news(r.get("title", ""))][:count]


def _fetch_news_via_google(stock_name: str, count: int) -> list[dict]:
    """Google News RSS — 한국어 검색. Python 표준 XML 모듈로 안정적 파싱."""
    from xml.etree import ElementTree as ET

    url = (
        f"https://news.google.com/rss/search?q={quote(stock_name)}"
        f"&hl=ko&gl=KR&ceid=KR:ko"
    )
    try:
        r = requests.get(url, headers=NAVER_HEADERS, timeout=15)
        r.raise_for_status()

        # 표준 XML 파서로 파싱 (BeautifulSoup html.parser는 <link> 처리 못함)
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            # XML 파싱 실패 → 정규식 폴백
            return _fetch_news_via_google_regex(r.text, count)

        results = []
        # RSS 2.0 구조: rss > channel > item
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            date = (item.findtext("pubDate") or "").strip()

            if not title:
                continue

            # description 의 HTML 태그 제거
            desc_clean = _clean_html(desc)

            results.append({
                "title": title,
                "summary": desc_clean[:200],
                "link": link,
                "date": date,
            })
            if len(results) >= count:
                break

        return results
    except Exception as e:
        print(f"   ⚠️ Google News RSS 실패: {e}")
        return []


def _fetch_news_via_google_regex(xml_text: str, count: int) -> list[dict]:
    """XML 파싱 실패 시 정규식 폴백."""
    results = []
    items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    for raw in items[:count]:
        t_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.DOTALL)
        l_m = re.search(r"<link[^>]*>(.*?)</link>", raw, re.DOTALL)
        d_m = re.search(r"<description[^>]*>(.*?)</description>", raw, re.DOTALL)
        title = (t_m.group(1) if t_m else "").strip()
        # CDATA 처리
        title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", title, flags=re.DOTALL)
        link = (l_m.group(1) if l_m else "").strip()
        desc = (d_m.group(1) if d_m else "").strip()
        if not title:
            continue
        results.append({
            "title": _clean_html(title),
            "summary": _clean_html(desc)[:200],
            "link": link,
            "date": "",
        })
    return results


def _fetch_news_via_api(stock_name: str, count: int) -> list[dict]:
    """네이버 검색 API 사용 (NAVER_CLIENT_ID/SECRET 필요)."""
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": stock_name, "display": count, "sort": "date"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        results = []
        for it in items:
            results.append({
                "title": _clean_html(it.get("title", "")),
                "summary": _clean_html(it.get("description", "")),
                "link": it.get("originallink") or it.get("link", ""),
                "date": it.get("pubDate", ""),
            })
        return results
    except Exception as e:
        print(f"   ⚠️ Naver 뉴스 API 실패: {e} → 검색 페이지로 폴백")
        return _fetch_news_via_search(stock_name, count)


def _fetch_news_via_search(stock_name: str, count: int) -> list[dict]:
    """네이버 뉴스 검색 페이지 스크래핑 (API 키 없을 때)."""
    url = f"https://search.naver.com/search.naver?where=news&query={quote(stock_name)}&sort=1"
    try:
        r = requests.get(url, headers=NAVER_HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        # 네이버 뉴스 검색 결과는 클래스 구조가 자주 바뀜 — 관대하게 파싱
        articles = soup.select(".news_tit") or soup.select("a.news_tit") or soup.select(".sds-comps-text")

        for a in articles[:count]:
            title = a.get_text(strip=True)
            link = a.get("href", "") if a.name == "a" else ""
            if title and link:
                results.append({
                    "title": title,
                    "summary": "",
                    "link": link,
                    "date": "",
                })

        # 폴백: 다른 선택자 시도
        if not results:
            for a in soup.find_all("a", class_=re.compile(r"news_tit|tit"))[:count]:
                title = a.get_text(strip=True)
                link = a.get("href", "")
                if title and link and len(title) > 5:
                    results.append({"title": title, "summary": "", "link": link, "date": ""})

        return results[:count]
    except Exception as e:
        print(f"   ⚠️ Naver 뉴스 검색 실패: {e}")
        return []


def _clean_html(text: str) -> str:
    """HTML 태그·엔티티 제거."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&apos;", "'").replace("&#39;", "'")
    return text.strip()


def fetch_price_data(ticker: str) -> dict:
    """1년치 시세 + Naver 재무지표."""
    today = datetime.today().strftime("%Y%m%d")
    one_year_ago = (datetime.today() - timedelta(days=365)).strftime("%Y%m%d")

    df_ohlcv = stock.get_market_ohlcv(one_year_ago, today, ticker)
    if df_ohlcv.empty:
        return {}

    latest = df_ohlcv.iloc[-1]
    prev = df_ohlcv.iloc[-2] if len(df_ohlcv) > 1 else latest
    high_52w = df_ohlcv["고가"].max()
    low_52w = df_ohlcv["저가"].min()

    naver_data = fetch_from_naver_api(ticker)

    change = int(latest["종가"]) - int(prev["종가"])
    change_pct = (change / int(prev["종가"])) * 100 if int(prev["종가"]) else 0

    return {
        "current_price": int(latest["종가"]),
        "change": change,
        "change_pct": round(change_pct, 2),
        "volume": int(latest["거래량"]),
        "high_52w": int(high_52w),
        "low_52w": int(low_52w),
        "market_cap_won": naver_data.get("market_cap_won", 0),
        "per": naver_data.get("per"),
        "pbr": naver_data.get("pbr"),
        "eps": naver_data.get("eps"),
        "bps": naver_data.get("bps"),
        "div_yield": naver_data.get("div_yield"),
        "cns_per": naver_data.get("cns_per"),
        "cns_eps": naver_data.get("cns_eps"),
        "dividend": naver_data.get("dividend"),
        "foreign_rate": naver_data.get("foreign_rate"),
        "price_history": df_ohlcv["종가"].tolist(),
    }


# ─────────────────────────────────────────────────────────────────────
# 3. Claude 분석 호출
# ─────────────────────────────────────────────────────────────────────
ANALYSIS_PROMPT = """당신은 한국 주식 시장 전문 애널리스트입니다.
아래 종목에 대한 자동 분석 리포트를 작성해주세요.

## 종목 정보
- 종목명: {name}
- 티커: {ticker}
- 시장: {market}

## 시세 데이터 (실제 수집값, 정확도 높음)
- 현재가: {current_price:,}원 ({change_sign}{change:,}원, {change_pct:+.2f}%)
- 시가총액: {market_cap_str}
- 거래량: {volume:,}주
- 52주 범위: {low_52w:,} ~ {high_52w:,}원
- 외국인 보유율: {foreign_rate_str}

## 재무 지표 (실제 수집값, 정확도 높음)
- PER: {per_str}배 / 추정 PER: {cns_per_str}배
- PBR: {pbr_str}배
- EPS: {eps_str}원 / 추정 EPS: {cns_eps_str}원
- BPS: {bps_str}원
- 배당수익률: {div_str}% (주당 배당금 {dividend_str}원)

## 최근 뉴스 (Claude가 직접 분석에 활용할 것)
{news_block}

## 작성 지침
1. **사업 내용 + 매출 구조** — 무슨 회사, 사업부문별 매출 비중
2. **재무 지표 평가** — PER/PBR/EPS 동종업계 비교, 추정 PER이 현재 PER보다 크게 낮으면 "실적 회복 기대" 의미
3. **최근 실적 추이** — 위 뉴스와 학습 지식 결합
4. **경쟁사 비교 + 적정주가** — 동종업계 2~3곳 비교, 적정주가 범위 제시
5. **종합 의견** — 강점·리스크·관전포인트 각 3개씩 (위 뉴스에서 단서 활용)

각 섹션은 이모지(🟢/🟡/🔴) 활용, 숫자는 표 형태.
마지막에 디스클레이머 추가: "본 리포트는 자동 생성된 정보 제공용이며 투자 자문이 아닙니다."

마크다운 형식으로만 출력하세요.
"""


def call_claude(name: str, ticker: str, market: str, price_data: dict, news: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    market_cap_str = format_market_cap(price_data.get("market_cap_won", 0))

    def _fmt(v, suffix: str = "", fmt: str = "{:.2f}"):
        return fmt.format(v) + suffix if v is not None else "N/A"

    def _fmt_int(v):
        return f"{int(v):,}" if v is not None else "N/A"

    news_lines = []
    for i, n in enumerate(news[:8], 1):
        title = n.get("title", "")
        summary = n.get("summary", "")
        if summary:
            news_lines.append(f"{i}. {title} — {summary[:80]}")
        else:
            news_lines.append(f"{i}. {title}")
    news_block = "\n".join(news_lines) if news_lines else "(뉴스 없음)"

    prompt = ANALYSIS_PROMPT.format(
        name=name,
        ticker=ticker,
        market=market,
        current_price=price_data["current_price"],
        change_sign="+" if price_data["change"] >= 0 else "",
        change=price_data["change"],
        change_pct=price_data["change_pct"],
        market_cap_str=market_cap_str,
        volume=price_data["volume"],
        low_52w=price_data["low_52w"],
        high_52w=price_data["high_52w"],
        foreign_rate_str=_fmt(price_data.get("foreign_rate"), "%"),
        per_str=_fmt(price_data.get("per")),
        cns_per_str=_fmt(price_data.get("cns_per")),
        pbr_str=_fmt(price_data.get("pbr")),
        eps_str=_fmt_int(price_data.get("eps")),
        cns_eps_str=_fmt_int(price_data.get("cns_eps")),
        bps_str=_fmt_int(price_data.get("bps")),
        div_str=_fmt(price_data.get("div_yield")),
        dividend_str=_fmt_int(price_data.get("dividend")),
        news_block=news_block,
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


# ─────────────────────────────────────────────────────────────────────
# 4. 리포트 작성
# ─────────────────────────────────────────────────────────────────────
def build_report(name: str, ticker: str, market: str,
                 price_data: dict, news: list[dict],
                 claude_analysis: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    market_cap_str = format_market_cap(price_data.get("market_cap_won", 0))

    def _v(key, suffix="", fmt="{:.2f}"):
        v = price_data.get(key)
        return fmt.format(v) + suffix if v is not None else "N/A"

    def _vi(key):
        v = price_data.get(key)
        return f"{int(v):,}" if v is not None else "N/A"

    arrow = "▲" if price_data["change"] >= 0 else "▼"
    change_color = "🔴" if price_data["change"] >= 0 else "🔵"  # 한국식: 상승 빨강

    header = f"""# {name} ({ticker})

> **자동 생성 분석 리포트** · 마지막 갱신: {today}
> 시장: {market} · 본 리포트는 Claude가 자동 생성합니다. 투자 자문이 아닙니다.

---

## 한눈에 보기

| 항목 | 값 |
|------|-----|
| 현재가 | **{price_data['current_price']:,}원** {arrow}{abs(price_data['change']):,}원 ({price_data['change_pct']:+.2f}%) |
| 시가총액 | {market_cap_str} |
| 거래량 | {price_data['volume']:,}주 |
| 52주 범위 | {price_data['low_52w']:,} ~ {price_data['high_52w']:,}원 |
| 외국인 보유율 | {_v('foreign_rate', '%')} |
| PER (실적) | {_v('per', '배')} |
| 추정 PER (예상) | {_v('cns_per', '배')} |
| PBR | {_v('pbr', '배')} |
| EPS | {_vi('eps')}원 |
| BPS | {_vi('bps')}원 |
| 배당수익률 | {_v('div_yield', '%')} |
| 주당 배당금 | {_vi('dividend')}원 |

---

"""

    # 뉴스 섹션
    news_section = "## 📰 최근 뉴스\n\n"
    if news:
        for i, n in enumerate(news[:8], 1):
            title = n.get("title", "")
            summary = n.get("summary", "")
            link = n.get("link", "")
            if link:
                news_section += f"{i}. [{title}]({link})"
            else:
                news_section += f"{i}. {title}"
            if summary:
                news_section += f"\n   {summary[:120]}\n"
            else:
                news_section += "\n"
    else:
        news_section += "_(수집된 뉴스 없음 — Naver 검색 페이지 구조 변경 가능성)_\n"
    news_section += "\n---\n\n"

    memo_section = """

---

## 내 메모 ✏️

```
[ 사용자가 자유롭게 작성하는 영역 ]


```

---

*Generated by Claude · 자동 분석 v0.2*
"""

    return header + news_section + claude_analysis + memo_section


# ─────────────────────────────────────────────────────────────────────
# 5. 단일 종목 분석 (재사용 가능 함수)
# ─────────────────────────────────────────────────────────────────────
def analyze_one(ticker: str, name: str, market: str,
                with_claude: bool = True, verbose: bool = True) -> Optional[Path]:
    """티커 1개 분석 → 리포트 파일 저장. 경로 반환.
    analyze_all.py 에서 루프로 호출함.
    """
    if verbose:
        print(f"📊 [{ticker}] {name} — 시세·재무·뉴스 수집 중...")

    price_data = fetch_price_data(ticker)
    if not price_data:
        if verbose:
            print(f"   ❌ 시세 데이터 없음 (거래정지·신규상장 등)")
        return None

    if verbose:
        change_pct = price_data["change_pct"]
        print(f"   현재가: {price_data['current_price']:,}원 ({change_pct:+.2f}%)")

    news = fetch_naver_news(name, count=8)
    if verbose:
        print(f"   뉴스 {len(news)}개 수집")

    if with_claude:
        if verbose:
            print(f"   🤖 Claude 분석 중...")
        analysis = call_claude(name, ticker, market, price_data, news)
    else:
        analysis = "_(Claude 분석 생략 모드)_"

    report = build_report(name, ticker, market, price_data, news, analysis)

    today_str = datetime.now().strftime("%Y%m%d")
    output_path = REPORT_DIR / f"{ticker}_{name}_{today_str}.md"
    output_path.write_text(report, encoding="utf-8")

    if verbose:
        print(f"   ✅ 저장: {output_path.name} ({output_path.stat().st_size:,} bytes)")

    return output_path


# ─────────────────────────────────────────────────────────────────────
# 6. 메인 실행 (단일 종목)
# ─────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    query = sys.argv[1]
    print(f"🔍 '{query}' 검색 중...")

    resolved = resolve_ticker(query)
    if not resolved:
        print(f"❌ '{query}' 종목을 찾을 수 없습니다.")
        sys.exit(1)

    ticker, name, market = resolved
    print(f"✅ 종목 확인: {name} ({ticker}) — {market}\n")

    output_path = analyze_one(ticker, name, market)
    if output_path:
        print(f"\n✅ 리포트 생성 완료: {output_path}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
