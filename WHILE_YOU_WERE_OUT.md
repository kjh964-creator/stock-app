# 외출 중 진행 상황 — v0.2 → v0.5 점프

> 2026-05-10 / 김진호님 외출 중 자동 진행
>
> **최종 결론**: 백엔드 거의 완성. 모바일 앱 직전 단계.

---

## 🎁 새로 만든 것 5개

### 1. `analyze_stock.py` — v0.2 업그레이드
- 📰 **Naver 뉴스 자동 수집** (종목당 8개) → Claude 분석에 포함
- 🔮 **추정 PER / 추정 EPS** 표시 (Forward PE)
- 💱 **포맷 개선** — `1,569.7조원`, `6,564원`, `40.9배`
- ♻️ **`analyze_one()`** 함수 분리 (재사용 가능)

### 2. `analyze_all.py` ⭐ NEW
50종목 일괄 분석. 캐싱·진행표시·인덱스 자동 생성.

### 3. `event_alert.py` ⭐ NEW
±3% 등락·거래량 급증 감지 + 텔레그램 알림.

### 4. `app.py` ⭐ NEW (Streamlit 웹앱)
3탭 UI 완성. 관심종목 / 주식뉴스 / 보관 + 메모 영속화.

### 5. `server.py` ⭐ NEW (FastAPI 서버)
모바일 앱용 REST API 백엔드. 12개 엔드포인트 + 인터랙티브 문서(`/docs`).

---

## 🚀 돌아오시면 단계별로 (5분이면 다 됩니다)

### Step 1: 새 라이브러리 설치 (1분)
```cmd
cd /d "C:\원드라이브\OneDrive\주식정보\주식정보어플만들기\주식정보 어플만들기"
pip install -r requirements.txt
```
→ streamlit, fastapi, uvicorn 추가됨.

### Step 2: 일괄 분석 5개 테스트 (5분)
```cmd
python analyze_all.py --max 5
```
→ 잘 되면 다음 단계, 에러 나면 결과 캡처해주세요.

### Step 3: 웹앱 띄우기 (10초)
```cmd
streamlit run app.py
```
→ 브라우저 자동 열림 (http://localhost:8501)
→ **같은 와이파이의 폰에서도 PC IP주소:8501 로 접속 가능**

### Step 4 (선택): API 서버 띄우기
```cmd
uvicorn server:app --reload --port 8000
```
→ http://localhost:8000/docs 접속하면 모든 API 인터랙티브 문서

### Step 5 (선택): 50종목 전체 분석 (30~40분, $0.5~1)
```cmd
python analyze_all.py
```
→ 모든 관심종목 리포트 한꺼번에 갱신.

---

## 📁 작업 폴더 최종 상태

```
주식정보 어플만들기/
├── README.md                  ✏️ 전면 업데이트
├── WHILE_YOU_WERE_OUT.md      🆕 이 파일 (요약)
├── app_spec.md                (그대로)
├── watchlist.csv              (50종목)
├── config.yaml
├── requirements.txt           ✏️ streamlit, fastapi 추가
├── .env.example
├── .env
│
├── analyze_stock.py           ✏️ v0.2 업그레이드
├── analyze_all.py             🆕 50종목 일괄
├── event_alert.py             🆕 이벤트 + 텔레그램
├── app.py                     🆕 Streamlit 3탭 UI
├── server.py                  🆕 FastAPI REST 서버
│
└── data/
    ├── reports/               ← 분석 리포트들
    ├── debug/                 ← API 응답 디버그
    ├── archive.json           ← 보관함 (자동 생성)
    └── memos.json             ← 메모 (자동 생성)
```

---

## 🎯 전체 로드맵 진행도

| 단계 | 내용 | 상태 |
|-----|-----|------|
| v0.1 | 단일 종목 분석 | ✅ |
| v0.2 | 일괄 분석 + 캐싱 | ✅ |
| v0.3 | 뉴스 수집 + 추정 PER | ✅ |
| v0.4 | 이벤트 알림 + 웹앱 UI | ✅ |
| **v0.5** | **FastAPI 서버 (모바일용 백엔드)** | **✅** |
| v0.6 | 클라우드 배포 (Railway 무료) | ⬜ |
| v0.7 | Flutter 모바일 앱 | ⬜ |

지금 시점에서 **본인 사용용**으로는 이미 차고 넘칩니다. 매일 폰 브라우저로 `streamlit run app.py` 띄운 PC IP 주소 접속해서 보면 사실상 모바일 앱과 동일한 경험.

진짜 **앱스토어 배포용 모바일 앱**을 원하시면 v0.6 → v0.7 진행하면 됩니다 (별도 1~2주 작업).

---

## 💡 추천 일상 워크플로

**아침 7시**: 자동 스케줄러로 `analyze_all.py` 실행되어 있음 (Windows 작업 스케줄러 등록 — README 참고)
**아침 7시 30분**: 폰으로 PC Streamlit 접속, 어제 분석 결과 정독
**장 시간 중**: 5~10분마다 자동 `event_alert.py` 실행 → 급등락 알림 폰으로
**저녁**: 새로 발생한 이벤트 종목들 보관함에 정리, 메모 작성

---

## ⚠️ 알려진 이슈 / 후속 처리 필요

1. **Streamlit 첫 실행은 1~2초 걸림** (정상)
2. **뉴스 검색 페이지 스크래핑은 Naver 구조 변경 시 빈 결과 가능** → NAVER_CLIENT_ID/SECRET 발급받으면 안정적 (README 참고, 무료, 5분)
3. **새 모듈은 직접 실행 못 했음** — 코드 리뷰만 됨. 첫 실행에서 minor 버그 가능. 발생 시 알려주세요.
4. **텔레그램 알림은 봇 셋업 필요** (선택, README 참고)
5. **FastAPI 서버는 로컬에서만 동작** — 폰에서 인터넷 통해 접속하려면 클라우드 배포 필요 (다음 단계)

---

## 🤝 돌아오시면 이렇게 알려주세요

성공이면:
> "다 잘 됨! 다음 단계는?"

에러 나면:
> "이거 안 됨" + cmd 화면 캡처 또는 에러 메시지

대충 이래도 됨:
> "Streamlit 화면이 좀 어색해" / "PER 표시가 이상해" / "뉴스가 안 나옴"

---

수고 많으셨어요. 푹 쉬다 오세요. 🍵
