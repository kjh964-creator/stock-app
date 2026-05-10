"""
analyze_all.py — 관심종목 일괄 분석 (v0.2)

사용법:
    python analyze_all.py                  # watchlist.csv 의 모든 종목 분석 (오늘 분석된 건 스킵)
    python analyze_all.py --force          # 오늘 분석된 것도 다시 분석
    python analyze_all.py --group 관심1    # 특정 그룹만
    python analyze_all.py --skip-etf       # ETF 제외 (기본값: 제외)
    python analyze_all.py --include-etf    # ETF 포함

결과:
    data/reports/{ticker}_{name}_{날짜}.md  (각 종목별)
    data/reports/_INDEX_{날짜}.md           (전체 인덱스 + 요약)
"""

from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

# analyze_stock 모듈에서 함수 import (한 번에 환경변수·경로도 로드됨)
from analyze_stock import (
    PROJECT_ROOT,
    REPORT_DIR,
    WATCHLIST_PATH,
    analyze_one,
    detect_market,
)


def parse_args():
    p = argparse.ArgumentParser(description="관심종목 일괄 분석")
    p.add_argument("--force", action="store_true", help="오늘 분석된 것도 다시 실행")
    p.add_argument("--group", default=None, help="특정 그룹만 (예: 관심1)")
    p.add_argument("--skip-etf", dest="skip_etf", action="store_true", default=True,
                   help="ETF 제외 (기본값)")
    p.add_argument("--include-etf", dest="skip_etf", action="store_false",
                   help="ETF 포함")
    p.add_argument("--max", type=int, default=None, help="최대 N개만 (테스트용)")
    return p.parse_args()


def load_watchlist(group: Optional[str] = None, skip_etf: bool = True) -> pd.DataFrame:
    """watchlist.csv 로드 + 필터링."""
    if not WATCHLIST_PATH.exists():
        print(f"❌ {WATCHLIST_PATH} 파일이 없습니다.")
        sys.exit(1)

    df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    df = df.fillna({"ticker": "", "is_etf": False, "note": ""})

    # 그룹 필터
    if group:
        df = df[df["group"] == group]

    # ETF 제외
    if skip_etf:
        df = df[df["is_etf"].astype(str).str.lower() != "true"]

    # 티커 없는 항목 제외 + 정규화
    df = df[df["ticker"].astype(str).str.strip() != ""]
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)

    # 중복 제거 (같은 종목이 여러 그룹에 있으면 한 번만 분석)
    df_unique = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)

    return df_unique


def report_already_exists_today(ticker: str, name: str) -> Optional[Path]:
    """오늘 날짜 리포트가 이미 있으면 경로 반환."""
    today_str = datetime.now().strftime("%Y%m%d")
    candidate = REPORT_DIR / f"{ticker}_{name}_{today_str}.md"
    if candidate.exists() and candidate.stat().st_size > 1000:
        return candidate
    return None


def write_index_report(results: list[dict], output_path: Path):
    """일괄 분석 결과 인덱스 마크다운 작성."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_str = datetime.now().strftime("%Y%m%d")

    success = [r for r in results if r["status"] in ("success", "cached")]
    failed = [r for r in results if r["status"] == "failed"]

    lines = [
        f"# 관심종목 일괄 분석 인덱스",
        f"",
        f"> 생성: {today} · 총 {len(results)}종목 (성공 {len(success)}, 실패 {len(failed)})",
        f"",
        f"---",
        f"",
        f"## 그룹별 종목",
        f"",
    ]

    by_group: dict[str, list[dict]] = {}
    for r in results:
        for g in r.get("groups", []):
            by_group.setdefault(g, []).append(r)

    for group_name in sorted(by_group.keys()):
        lines.append(f"### {group_name}")
        lines.append("")
        lines.append("| # | 종목 | 시세 | 등락 | 시가총액 | PER | PBR | 리포트 |")
        lines.append("|---|------|-----:|-----:|---------:|----:|----:|--------|")
        for i, r in enumerate(by_group[group_name], 1):
            ticker = r["ticker"]
            name = r["name"]
            price = r.get("current_price")
            change_pct = r.get("change_pct")
            market_cap_str = r.get("market_cap_str", "—")
            per = r.get("per")
            pbr = r.get("pbr")

            price_s = f"{int(price):,}원" if price else "—"
            change_s = f"{change_pct:+.2f}%" if change_pct is not None else "—"
            per_s = f"{per:.1f}" if per else "—"
            pbr_s = f"{pbr:.1f}" if pbr else "—"

            report_path = r.get("report_path")
            link_s = f"[보기](./{report_path.name})" if report_path else "❌"

            lines.append(
                f"| {i} | **{name}** ({ticker}) | {price_s} | {change_s} "
                f"| {market_cap_str} | {per_s} | {pbr_s} | {link_s} |"
            )
        lines.append("")

    if failed:
        lines.append("---")
        lines.append("")
        lines.append("## ❌ 실패 종목")
        lines.append("")
        for r in failed:
            lines.append(f"- {r['name']} ({r['ticker']}): {r.get('error', 'unknown')}")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    args = parse_args()

    print("=" * 60)
    print("📈 관심종목 일괄 분석 시작")
    print("=" * 60)

    df = load_watchlist(group=args.group, skip_etf=args.skip_etf)
    if args.max:
        df = df.head(args.max)

    if df.empty:
        print("❌ 분석할 종목이 없습니다.")
        sys.exit(1)

    print(f"📋 대상: {len(df)}개 종목")
    if args.skip_etf:
        print(f"   (ETF 제외)")
    if args.group:
        print(f"   (그룹: {args.group})")
    print()

    # 그룹 정보 매핑 (티커당 어느 그룹들에 속하는지)
    full_df = pd.read_csv(WATCHLIST_PATH, dtype={"ticker": str})
    full_df["ticker"] = full_df["ticker"].fillna("").str.zfill(6)
    ticker_to_groups: dict[str, list[str]] = {}
    for _, row in full_df.iterrows():
        t = str(row["ticker"]).strip()
        g = str(row.get("group", ""))
        if t and g:
            ticker_to_groups.setdefault(t, []).append(g)

    results = []
    start_time = time.time()

    for i, row in df.iterrows():
        ticker = str(row["ticker"]).zfill(6)
        name = str(row["name"])
        market = str(row.get("market", "")) or detect_market(ticker)
        groups = ticker_to_groups.get(ticker, [])

        idx = len(results) + 1
        elapsed = int(time.time() - start_time)
        print(f"[{idx}/{len(df)}] {ticker} {name} ({market}) — 경과 {elapsed}s")

        # 캐시 체크
        if not args.force:
            cached = report_already_exists_today(ticker, name)
            if cached:
                print(f"   💾 오늘 이미 분석됨 — 스킵 (--force 로 강제 재실행 가능)")
                # 캐시된 정보 일부만 추출 (간단히)
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "groups": groups,
                    "status": "cached",
                    "report_path": cached,
                })
                print()
                continue

        # 분석 실행
        try:
            output_path = analyze_one(ticker, name, market, with_claude=True, verbose=True)
            if output_path:
                # price_data 다시 안 부르고 리포트 헤더에서 읽을 수도 있지만 간단히 None
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "groups": groups,
                    "status": "success",
                    "report_path": output_path,
                })
            else:
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "groups": groups,
                    "status": "failed",
                    "error": "시세 데이터 없음",
                })
        except KeyboardInterrupt:
            print("\n⛔ 사용자 중단. 지금까지 분석된 종목은 저장됨.")
            break
        except Exception as e:
            print(f"   ❌ 에러: {e}")
            results.append({
                "ticker": ticker,
                "name": name,
                "market": market,
                "groups": groups,
                "status": "failed",
                "error": str(e),
            })

        print()

    # 인덱스 리포트 작성
    today_str = datetime.now().strftime("%Y%m%d")
    index_path = REPORT_DIR / f"_INDEX_{today_str}.md"

    # 각 결과에 가격 데이터 추가 시도 (이미 분석된 리포트 헤더에서 읽기)
    # 간단화: 인덱스에는 종목명·티커·리포트 링크만 (가격 정보는 리포트 안에)
    for r in results:
        path = r.get("report_path")
        if path and path.exists():
            try:
                # 리포트 헤더에서 가격 등 정보 추출 (정규식)
                text = path.read_text(encoding="utf-8")
                import re as _re
                m_price = _re.search(r"\*\*([\d,]+)원\*\*", text)
                if m_price:
                    r["current_price"] = float(m_price.group(1).replace(",", ""))
                m_chg = _re.search(r"\(([+-]?\d+\.\d+)%\)", text)
                if m_chg:
                    r["change_pct"] = float(m_chg.group(1))
                m_cap = _re.search(r"시가총액 \| ([\d,.]+조원|\d+[\d,]*억원)", text)
                if m_cap:
                    r["market_cap_str"] = m_cap.group(1)
                m_per = _re.search(r"PER \(실적\) \| ([\d.]+)배", text)
                if m_per:
                    r["per"] = float(m_per.group(1))
                m_pbr = _re.search(r"PBR \| ([\d.]+)배", text)
                if m_pbr:
                    r["pbr"] = float(m_pbr.group(1))
            except Exception:
                pass

    write_index_report(results, index_path)

    elapsed_total = int(time.time() - start_time)
    print("=" * 60)
    print(f"✅ 일괄 분석 완료 ({elapsed_total}초 소요)")
    success = sum(1 for r in results if r["status"] in ("success", "cached"))
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"   성공: {success}개 / 실패: {failed}개")
    print(f"   인덱스: {index_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
