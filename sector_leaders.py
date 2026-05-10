"""
sector_leaders.py — 한국 주식 섹터별 대표종목 (시총·점유율 기준 리더 순)

각 섹터의 1위부터 10위까지. 시장에서 그 섹터를 이끄는 종목 위주로.
일부 섹터(통신·철강 등)는 상장사가 적어 5~7개만.
"""

from __future__ import annotations

# 섹터 → [(ticker, name, market)]
SECTOR_LEADERS: dict[str, list[tuple[str, str, str]]] = {
    "반도체": [
        ("005930", "삼성전자", "KOSPI"),
        ("000660", "SK하이닉스", "KOSPI"),
        ("042700", "한미반도체", "KOSPI"),
        ("000990", "DB하이텍", "KOSPI"),
        ("058470", "리노공업", "KOSDAQ"),
        ("240810", "원익IPS", "KOSDAQ"),
        ("357780", "솔브레인", "KOSDAQ"),
        ("005290", "동진쎄미켐", "KOSDAQ"),
        ("039030", "이오테크닉스", "KOSDAQ"),
        ("402340", "SK스퀘어", "KOSPI"),
    ],
    "2차전지·배터리": [
        ("373220", "LG에너지솔루션", "KOSPI"),
        ("006400", "삼성SDI", "KOSPI"),
        ("003670", "포스코퓨처엠", "KOSPI"),
        ("247540", "에코프로비엠", "KOSDAQ"),
        ("066970", "엘앤에프", "KOSDAQ"),
        ("096770", "SK이노베이션", "KOSPI"),
        ("005070", "코스모신소재", "KOSPI"),
        ("278280", "천보", "KOSDAQ"),
        ("336370", "솔루스첨단소재", "KOSPI"),
        ("121600", "나노신소재", "KOSDAQ"),
    ],
    "자동차": [
        ("005380", "현대차", "KOSPI"),
        ("000270", "기아", "KOSPI"),
        ("012330", "현대모비스", "KOSPI"),
        ("018880", "한온시스템", "KOSPI"),
        ("204320", "HL만도", "KOSPI"),
        ("307950", "현대오토에버", "KOSPI"),
        ("011210", "현대위아", "KOSPI"),
        ("005850", "에스엘", "KOSPI"),
        ("003620", "KG모빌리티", "KOSPI"),
        ("161390", "한국타이어앤테크놀로지", "KOSPI"),
    ],
    "바이오·제약": [
        ("207940", "삼성바이오로직스", "KOSPI"),
        ("068270", "셀트리온", "KOSPI"),
        ("000100", "유한양행", "KOSPI"),
        ("326030", "SK바이오팜", "KOSPI"),
        ("128940", "한미약품", "KOSPI"),
        ("185750", "종근당", "KOSPI"),
        ("006280", "녹십자", "KOSPI"),
        ("069620", "대웅제약", "KOSPI"),
        ("001060", "JW중외제약", "KOSPI"),
        ("003850", "보령", "KOSPI"),
    ],
    "인터넷·게임": [
        ("035420", "NAVER", "KOSPI"),
        ("035720", "카카오", "KOSPI"),
        ("259960", "크래프톤", "KOSPI"),
        ("036570", "엔씨소프트", "KOSPI"),
        ("251270", "넷마블", "KOSPI"),
        ("293490", "카카오게임즈", "KOSDAQ"),
        ("263750", "펄어비스", "KOSDAQ"),
        ("112040", "위메이드", "KOSDAQ"),
        ("078340", "컴투스", "KOSDAQ"),
        ("194480", "데브시스터즈", "KOSDAQ"),
    ],
    "금융·은행": [
        ("105560", "KB금융", "KOSPI"),
        ("055550", "신한지주", "KOSPI"),
        ("086790", "하나금융지주", "KOSPI"),
        ("316140", "우리금융지주", "KOSPI"),
        ("138040", "메리츠금융지주", "KOSPI"),
        ("006800", "미래에셋증권", "KOSPI"),
        ("039490", "키움증권", "KOSPI"),
        ("071050", "한국금융지주", "KOSPI"),
        ("005940", "NH투자증권", "KOSPI"),
        ("032830", "삼성생명", "KOSPI"),
    ],
    "통신·미디어": [
        ("017670", "SK텔레콤", "KOSPI"),
        ("030200", "KT", "KOSPI"),
        ("032640", "LG유플러스", "KOSPI"),
        ("189300", "인텔리안테크", "KOSDAQ"),
        ("034120", "SBS", "KOSPI"),
    ],
    "조선·방산": [
        ("329180", "HD현대중공업", "KOSPI"),
        ("042660", "한화오션", "KOSPI"),
        ("047810", "한국항공우주", "KOSPI"),
        ("079550", "LIG넥스원", "KOSPI"),
        ("012450", "한화에어로스페이스", "KOSPI"),
        ("272210", "한화시스템", "KOSPI"),
        ("064350", "현대로템", "KOSPI"),
        ("103140", "풍산", "KOSPI"),
        ("010140", "삼성중공업", "KOSPI"),
        ("010620", "현대미포조선", "KOSPI"),
    ],
    "화학·정유": [
        ("051910", "LG화학", "KOSPI"),
        ("011170", "롯데케미칼", "KOSPI"),
        ("009830", "한화솔루션", "KOSPI"),
        ("011790", "SKC", "KOSPI"),
        ("298020", "효성티앤씨", "KOSPI"),
        ("120110", "코오롱인더", "KOSPI"),
        ("006650", "대한유화", "KOSPI"),
        ("285130", "SK케미칼", "KOSPI"),
        ("010060", "OCI", "KOSPI"),
        ("298050", "효성첨단소재", "KOSPI"),
    ],
    "철강·금속": [
        ("005490", "POSCO홀딩스", "KOSPI"),
        ("004020", "현대제철", "KOSPI"),
        ("010130", "고려아연", "KOSPI"),
        ("058430", "포스코스틸리온", "KOSPI"),
        ("016380", "KG스틸", "KOSPI"),
        ("000670", "영풍", "KOSPI"),
    ],
    "식음료·유통": [
        ("097950", "CJ제일제당", "KOSPI"),
        ("271560", "오리온", "KOSPI"),
        ("004370", "농심", "KOSPI"),
        ("139480", "이마트", "KOSPI"),
        ("004170", "신세계", "KOSPI"),
        ("023530", "롯데쇼핑", "KOSPI"),
        ("069960", "현대백화점", "KOSPI"),
        ("007070", "GS리테일", "KOSPI"),
        ("005180", "빙그레", "KOSPI"),
        ("005300", "롯데칠성", "KOSPI"),
    ],
}

SECTOR_GROUP_NAME = "섹터대표"


def get_all_sector_stocks() -> list[dict]:
    """전체 섹터 대표 종목 평탄화 리스트.
    Returns: [{ticker, name, market, sector}]
    """
    flat = []
    for sector, stocks in SECTOR_LEADERS.items():
        for ticker, name, market in stocks:
            flat.append({
                "ticker": ticker,
                "name": name,
                "market": market,
                "sector": sector,
            })
    return flat


def init_sector_group(group_name: str = SECTOR_GROUP_NAME) -> tuple[int, int]:
    """섹터대표 그룹을 watchlist.csv 에 추가.
    이미 있는 종목은 스킵. (추가된 개수, 스킵된 개수) 반환.
    """
    from pathlib import Path
    import pandas as pd

    csv_path = Path(__file__).parent / "watchlist.csv"
    if not csv_path.exists():
        df = pd.DataFrame(columns=["group", "name", "ticker", "market", "is_etf", "note"])
    else:
        df = pd.read_csv(csv_path, dtype={"ticker": str})
        df = df.fillna({"ticker": "", "is_etf": False, "note": ""})

    existing_in_group = set(
        df[df["group"] == group_name]["ticker"].astype(str).str.zfill(6).tolist()
    )

    added = 0
    skipped = 0
    new_rows = []
    for sector, stocks in SECTOR_LEADERS.items():
        for ticker, name, market in stocks:
            if ticker in existing_in_group:
                skipped += 1
                continue
            new_rows.append({
                "group": group_name,
                "name": name,
                "ticker": ticker,
                "market": market,
                "is_etf": False,
                "note": sector,
            })
            added += 1

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df.to_csv(csv_path, index=False)

    return added, skipped


def get_sector_group_tickers(group_name: str = SECTOR_GROUP_NAME) -> list[tuple[str, str, str]]:
    """섹터대표 그룹의 종목 (ticker, name, market) 리스트."""
    from pathlib import Path
    import pandas as pd
    csv_path = Path(__file__).parent / "watchlist.csv"
    if not csv_path.exists():
        return []
    df = pd.read_csv(csv_path, dtype={"ticker": str})
    df = df[df["group"] == group_name].fillna({"ticker": "", "market": "KOSPI"})
    df["ticker"] = df["ticker"].str.zfill(6)
    df = df[df["ticker"].str.strip() != ""]
    return list(zip(df["ticker"].tolist(), df["name"].tolist(), df["market"].tolist()))
