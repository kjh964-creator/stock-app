"""
event_alert.py — 이벤트 감지 + 알림 (v0.3)

watchlist.csv 의 모든 종목에 대해:
  1. 오늘 등락률 ±3% 이상 → 급등락 이벤트
  2. 거래량 평균 대비 3배 이상 → 거래량 급증 이벤트
  3. 결과를 콘솔 출력 + 텔레그램 발송 (설정 시)

사용법:
    python event_alert.py                       # 전체 체크
    python event_alert.py --threshold 5         # 5% 임계값으로
    python event_alert.py --no-telegram         # 텔레그램 안 보내기

텔레그램 셋업:
    1. @BotFather 에서 봇 생성 → BOT_TOKEN 받기
    2. 본인 봇에게 아무 메시지 발송
    3. https://api.telegram.org/bot<TOKEN>/getUpdates 접속해서 chat.id 확인
    4. .env 에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력
"""

from __future__ import annotations

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv
from pykrx import stock

load_dotenv()

PROJECT_ROOT = Path(__file__).parent
WATCHLIST_PATH = PROJECT_ROOT / "watchlist.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def parse_args():
    p = argparse.ArgumentParser(description="이벤트 감지 + 알림")
    p.add_argument("--threshold", type=float, default=3.0, help="등락률 임계값 (기본 3.0%%)")
    p.add_argument("--volume-mult", type=float, default=3.0, help="거래량 배수 임계값 (기본 3.0배)")
    p.add_argument("--no-telegram", action="store_true", help="텔레그램 발송 안 함")
    p.add_argument("--group", default=None, help="특정 그룹만")
    return p.parse_args()


def send_telegram(message: str) -> bool:
    """텔레그램 메시지 발송. 토큰 없으면 무시."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"⚠️ Telegram 전송 실패: {e}")
        return False


def check_one_stock(ticker: str, name: str, threshold_pct: float, volume_mult: float) -> Optional[dict]:
    """단일 종목 이벤트 체크. 이벤트 발생 시 dict 반환, 없으면 None."""
    today = datetime.today().strftime("%Y%m%d")
    one_month_ago = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")

    try:
        df = stock.get_market_ohlcv(one_month_ago, today, ticker)
    except Exception:
        return None

    if df.empty or len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    today_close = int(latest["종가"])
    prev_close = int(prev["종가"])
    today_volume = int(latest["거래량"])

    if prev_close == 0:
        return None

    change_pct = (today_close - prev_close) / prev_close * 100
    avg_volume = int(df["거래량"].mean())
    volume_ratio = today_volume / avg_volume if avg_volume else 0

    events = []
    if abs(change_pct) >= threshold_pct:
        direction = "급등" if change_pct > 0 else "급락"
        events.append(f"📈 {direction} {change_pct:+.2f}%")

    if volume_ratio >= volume_mult:
        events.append(f"📊 거래량 {volume_ratio:.1f}배 (평균 대비)")

    if not events:
        return None

    return {
        "ticker": ticker,
        "name": name,
        "today_close": today_close,
        "change_pct": change_pct,
        "volume": today_volume,
        "volume_ratio": volume_ratio,
        "events": events,
    }


def format_alert_message(events_found: list[dict]) -> str:
    """텔레그램용 메시지 포맷."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"*🚨 주식 이벤트 알림 ({today})*", ""]

    risers = [e for e in events_found if e["change_pct"] > 0]
    fallers = [e for e in events_found if e["change_pct"] < 0]

    if risers:
        lines.append("*🔴 급등 종목*")
        for e in sorted(risers, key=lambda x: -x["change_pct"]):
            lines.append(
                f"• `{e['ticker']}` *{e['name']}*: {e['today_close']:,}원 "
                f"({e['change_pct']:+.2f}%) · 거래량 {e['volume_ratio']:.1f}x"
            )
        lines.append("")

    if fallers:
        lines.append("*🔵 급락 종목*")
        for e in sorted(fallers, key=lambda x: x["change_pct"]):
            lines.append(
                f"• `{e['ticker']}` *{e['name']}*: {e['today_close']:,}원 "
                f"({e['change_pct']:+.2f}%) · 거래량 {e['volume_ratio']:.1f}x"
            )
        lines.append("")

    return "\n".join(lines)


def main():
    args = parse_args()

    if not WATCHLIST_PATH.exists():
        print(f"❌ {WATCHLIST_PATH} 없음")
        sys.exit(1)

    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": "", "is_etf": False})
    df = df[df["is_etf"].astype(str).str.lower() != "true"]
    df = df[df["ticker"].astype(str).str.strip() != ""]
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    if args.group:
        df = df[df["group"] == args.group]

    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)

    print(f"🔎 {len(df)}개 종목 이벤트 체크 (임계값: ±{args.threshold}% 또는 거래량 {args.volume_mult}배)")
    print()

    events_found = []
    for i, row in df.iterrows():
        ticker = str(row["ticker"]).zfill(6)
        name = str(row["name"])
        result = check_one_stock(ticker, name, args.threshold, args.volume_mult)
        if result:
            events_found.append(result)
            arrow = "▲" if result["change_pct"] > 0 else "▼"
            print(f"  {arrow} {ticker} {name}: {result['today_close']:,}원 ({result['change_pct']:+.2f}%) · 거래량 {result['volume_ratio']:.1f}x")
            for ev in result["events"]:
                print(f"      {ev}")

    print()
    print("=" * 50)
    print(f"감지된 이벤트: {len(events_found)}건")

    if events_found and not args.no_telegram:
        message = format_alert_message(events_found)
        if send_telegram(message):
            print("✅ Telegram 발송 완료")
        elif TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            print("⚠️ Telegram 발송 실패 (네트워크/토큰 문제)")
        else:
            print("ℹ️ Telegram 미설정 — 콘솔 출력만 (.env 에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 추가 시 자동 발송)")


if __name__ == "__main__":
    main()
