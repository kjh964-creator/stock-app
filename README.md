# 주식정보 앱 — 백엔드 (v0.4)

Claude API 가 한국 주식을 자동으로 분석해서 리포트를 생성하고, 이벤트 발생 시 알림을 보내며, 웹 UI 로 확인까지 가능한 시스템.

---

## 🚀 핵심 명령어 (3가지)

```bash
# 1) 50종목 일괄 분석 (매일 장 마감 후 1회)
python analyze_all.py

# 2) 이벤트 체크 + 텔레그램 알림 (수시로)
python event_alert.py

# 3) 웹앱 UI 실행 (브라우저로 확인)
streamlit run app.py
```

---

## 📋 빠른 시작

### 단일 종목 분석 (가장 단순)

```bash
python analyze_stock.py 005930          # 티커
python analyze_stock.py 삼성전자          # 종목명
```

### 일괄 분석 옵션

```bash
python analyze_all.py                  # 전체 (오늘 분석된 건 자동 스킵)
python analyze_all.py --force          # 강제 재분석
python analyze_all.py --group 관심1     # 특정 그룹만
python analyze_all.py --max 5          # 상위 5개만 (테스트용)
python analyze_all.py --include-etf    # ETF 포함
```

### 이벤트 알림 옵션

```bash
python event_alert.py                  # ±3% 등락 또는 거래량 3배 이상
python event_alert.py --threshold 5    # 5% 임계값
python event_alert.py --no-telegram    # 콘솔 출력만
```

### 웹앱 UI

```bash
streamlit run app.py
```

→ 브라우저 자동 열림 (http://localhost:8501)
→ 같은 와이파이의 폰에서도 `IP주소:8501` 로 접속 가능 (예: `192.168.1.10:8501`)
→ 3탭 UI: 관심종목 / 주식뉴스 / 보관

---

## 🆕 버전 변경사항

### v0.4 (현재)
- 📱 Streamlit 웹앱 (`app.py`) — 3탭 UI 완성
- 🚨 이벤트 알림 (`event_alert.py`) — 텔레그램 발송 지원
- 💾 보관함·메모 데이터 영속화 (`data/archive.json`, `data/memos.json`)

### v0.3
- 📰 Naver 뉴스 자동 수집 (종목당 8개)
- 🔮 추정 PER / 추정 EPS 표시 (Forward PE)
- 💱 한국 단위 포맷 개선 (1,569.7조원)

### v0.2
- 📊 일괄 분석 (`analyze_all.py`) — 50종목 한 번에
- 💾 캐싱 — 같은 날 재분석 안 함

### v0.1
- ✅ 단일 종목 분석 (시세 + 재무지표 + Claude 분석)

---

## 📁 프로젝트 구조

```
주식정보 어플만들기/
├── README.md              ← 이 파일
├── app_spec.md            ← 앱 명세서
├── watchlist.csv          ← 관심종목 50개
├── config.yaml            ← 설정 (분석 주기·임계값)
├── requirements.txt       ← Python 라이브러리
├── .env                   ← API 키 (직접 작성)
│
├── analyze_stock.py       ← 단일 종목 분석 ⭐
├── analyze_all.py         ← 50종목 일괄 분석 ⭐
├── event_alert.py         ← 이벤트 감지 + 알림 ⭐
├── app.py                 ← Streamlit 웹앱 ⭐
│
└── data/
    ├── reports/
    │   ├── 005930_삼성전자_20260510.md     ← 종목별 리포트
    │   └── _INDEX_20260510.md              ← 일괄 분석 인덱스
    ├── archive.json                         ← 보관함
    ├── memos.json                           ← 종목별 메모
    └── debug/
        └── naver_api_005930.json            ← API 응답 디버그
```

---

## 🔧 추가 셋업 (선택)

### 텔레그램 알림 (이벤트 즉시 폰으로 받기)

1. 텔레그램에서 `@BotFather` 검색 → `/newbot` → 봇 이름 입력 → **BOT_TOKEN** 받기
2. 만든 봇 검색해서 `/start` 메시지 발송
3. 브라우저에서 https://api.telegram.org/bot본인토큰/getUpdates 접속
4. 응답 JSON 에서 `"chat":{"id":12345678}` 의 숫자 = **CHAT_ID**
5. `.env` 파일에 입력:
   ```
   TELEGRAM_BOT_TOKEN=8123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TELEGRAM_CHAT_ID=12345678
   ```
6. 테스트: `python event_alert.py`

### Naver 뉴스 API (안정적 뉴스 수집)

1. https://developers.naver.com/apps/ 에서 **애플리케이션 등록**
2. 사용 API: **검색** 체크
3. 발급된 Client ID / Secret 을 `.env` 에 입력:
   ```
   NAVER_CLIENT_ID=xxxxxxxxxxxxxx
   NAVER_CLIENT_SECRET=xxxxxxxxxx
   ```
4. 자동으로 공식 API 사용 (월 25,000회 무료)

### 매일 자동 실행 (Windows 작업 스케줄러)

1. **시작** → "작업 스케줄러" 검색 → 열기
2. **기본 작업 만들기**
3. 트리거: 매일 오후 6:30
4. 동작: 프로그램 시작 → `python.exe` → 인수: `analyze_all.py` → 시작 위치: 작업 폴더 경로

---

## 📑 리포트 구성 (각 종목)

마크다운 파일 7개 섹션:
1. **한눈에 보기** — 시세·시가총액·PER/PBR/EPS/배당·외국인 보유율
2. **📰 최근 뉴스** — Naver 자동 수집 8개
3. **사업 내용 + 매출 구조**
4. **재무 지표 평가** — 동종업계 비교
5. **최근 실적 추이** — 뉴스 + Claude 학습 지식 결합
6. **경쟁사 비교 + 적정주가**
7. **종합 의견** — 강점·리스크·관전포인트 + 내 메모란

---

## ⚠️ 주의사항

- **투자 자문 아님** — 정보 제공 목적입니다.
- **시세 15~20분 지연** — pykrx 무료 데이터.
- **API 키 보안** — `.env` 는 `.gitignore` 등록됨, 깃에 올리지 마세요.
- **Claude API 비용** — 50종목 첫 분석 약 $0.5~1, 캐싱으로 재분석은 0원.

---

## 🛠️ 트러블슈팅

| 증상 | 해결 |
|------|------|
| `KRX 로그인 실패: KRX_ID...` | 무시 OK — 안내 메시지일 뿐 실제 데이터 정상 |
| `pykrx Expecting value...` | KRX 단일날짜 엔드포인트 불안정. Naver API 자동 폴백 |
| 뉴스가 비어있음 | Naver 검색 페이지 구조 변경. NAVER_CLIENT_ID 발급 권장 |
| Streamlit 안 깔림 | `pip install streamlit>=1.32.0` |
| 텔레그램 안 옴 | BOT_TOKEN, CHAT_ID 확인. `python event_alert.py` 실행 시 메시지 확인 |

---

## 🎯 다음 로드맵

| 버전 | 내용 | 상태 |
|-----|-----|------|
| v0.1~v0.4 | 백엔드 + 웹앱 | ✅ 완성 |
| v0.5 | FastAPI 서버화 (모바일 앱이 호출할 API) | 다음 |
| v0.6 | Flutter 모바일 앱 | 그 다음 |
| v0.7 | 클라우드 배포 (Railway/Fly.io) | 마지막 |
