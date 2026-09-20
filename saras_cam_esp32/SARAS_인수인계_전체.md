# Saras 자동차 캠 작업 — 전체 인수인계 (단일 파일)

> ## 로컬 클로드에게 주는 첫 지시
>
> **이 파일 하나에 모든 것이 들어있습니다.** 아래 순서로 진행하세요.
>
> 1. **9장의 소스 3개를 실제 파일로 복원**하세요. 그대로 옮겨 적으면 됩니다:
>    - `saras_cam_esp32/saras_cam_esp32.ino`  (아두이노 스케치, 폴더명과 파일명이 같아야 열립니다)
>    - `saras_cam_esp32/cam_diag.py`
>    - `saras_cam_esp32/캠_진단.bat`
> 2. **0~5장을 읽어 맥락을 파악**하세요. 이미 끝난 분석이니 다시 하지 마세요.
> 3. **6장 Step 2부터 실행**하세요 (컴파일 → 업로드 → 시리얼 로그).
>    로컬 세션이므로 COM 포트와 `172.30.1.41` 에 직접 접근할 수 있습니다. 직접 하세요.
> 4. 먼저 확인: 작업 경로가 `C:\...` 면 정상, `/home/user/...` 면 또 클라우드입니다.
>    후자라면 사용자에게 알리고 로컬로 다시 띄우라고 하세요.
>
> 사용자는 한국어로 대화하며, 자신을 "형님"으로 불리는 것에 익숙합니다.

---

## 0. 왜 세션을 옮겼나

이전 작업은 **클라우드 컨테이너**에서 진행됐습니다 (`/home/user/stock-app`, Linux).
그래서 아래 두 가지를 할 수 없었습니다:

- ESP32 의 **COM 포트 접근** (컨테이너에 USB 장치가 없음)
- **집 와이파이의 `172.30.1.41` 접속** (프록시가 403 으로 차단)

로컬 세션에서는 둘 다 가능합니다. **이게 이 인수인계의 핵심 목적입니다.**

확인법: 작업 경로가 `C:\...` 면 로컬(정상), `/home/user/...` 면 다시 클라우드입니다.

---

## 1. 지금 상태 한 줄 요약

캠 펌웨어 **v2 를 만들어서 브랜치에 올렸고, 아직 실기기에서 한 번도 검증되지 않았습니다.**
당장 할 일은 **업로드 → 시리얼 로그 확인** 입니다.

미해결 문제 2개:
1. **상하(틸트) 서보가 안 움직인다** — 원인 미확정 (아래 3장)
2. **`http://172.30.1.41` 이 안 열린다** — 원인 미확정 (아래 4장)

---

## 2. 프로젝트 전체 구조 (파악 완료)

`kjh964-creator/stock-app` 레포에는 **성격이 다른 두 프로젝트가 섞여 있습니다.**

### 2-1. 주식앱 (v0.5, 완성 상태) — 레포의 99%
| 파일 | 줄수 | 역할 |
|---|---|---|
| `app.py` | 2222 | Streamlit 5탭 UI (섹터/관심종목/주식뉴스/새 정보/보관함) + 비밀번호 잠금 |
| `analyze_stock.py` | 783 | 단일종목 분석 (시세+재무+Claude) |
| `user_input.py` | 465 | 유튜브/URL/텍스트 → Claude 분석 |
| `server.py` | 401 | FastAPI 14개 엔드포인트 |
| `analyze_all.py` | 292 | 50종목 일괄 분석 |
| `event_alert.py` | 196 | 급등락 감지 + 텔레그램 |
| 보조 6개 | 1081 | 보관함·폴더·뉴스캐시·섹터 |

데이터: `data/reports/` 리포트 111개(2026-05-10자), 보관함 json 5개.
파이썬 12개 파일 전부 문법 통과. **이번 자동차 작업에서 주식앱은 한 줄도 건드리지 않았습니다.**

### 2-2. 자동차 — 조각만 있음
| 파일 | 상태 |
|---|---|
| `car_door.html` | 토레스 도어 BLE 제어 페이지 (연결/열림/잠금/트렁크 3초) |
| `saras_cam_esp32/saras_cam_esp32.ino` | **← 이번에 만든 캠 펌웨어 v2** |
| `saras_cam_esp32/cam_diag.py`, `캠_진단.bat` | PC 에서 돌리는 진단 도구 |

### 2-3. ⚠️ 레포에 없는 것 (git 히스토리 전체 확인함)
- `CAR_DOOR` 라는 이름으로 광고하는 **ESP32 BLE 도어 펌웨어** (car_door.html 의 상대) — 없음
- **바퀴/모터 제어 ESP32 펌웨어** (자동차 본체) — 없음
- **기존 조종 페이지** — 캠 펌웨어 주석이 "조종 페이지 img용" 이라고 참조하는데 그 페이지가 없음
- **AI 자율주행 코드** (`/capture` 를 불러 쓰는 쪽) — 없음

→ 사용자 PC 에만 있을 가능성이 높습니다. **핸드폰 조종 페이지를 만들려면 모터 펌웨어의
명령 규약(전진/후진/조향 URL 형식)을 알아야 하므로, 이 파일들을 받아야 합니다.**

---

## 3. 미해결 ①: 상하(틸트) 서보가 안 움직임

### 지금까지 분석한 것 (다시 안 해도 됨)

원본 v1 코드에서 팬(좌우)과 틸트(상하)의 **코드 경로가 완전히 대칭**입니다:

```
pan  : ledcAttach(13, 50, 16) -> servoWrite(13, deg) -> ledcWrite(13, duty)
tilt : ledcAttach(15, 50, 16) -> servoWrite(15, deg) -> ledcWrite(15, duty)
```

같은 함수, 같은 duty 계산(`us = 500 + deg*2000/180`, `duty = us*65535/20000`).
**소프트웨어만 보면 좌우만 되고 상하가 안 될 이유가 없습니다.**

비대칭인 것은 딱 하나:
```c
#define PAN_MIN   0 / PAN_MAX  180     // 범위 180도
#define TILT_MIN 30 / TILT_MAX 150     // 범위 120도 — constrain 으로 강제 클램프
```
→ `/servo?tilt=0` 이나 `?tilt=180` 을 보내면 30/150 으로 깎여서 "반응 없음"처럼 보일 수 있음.

**그리고 v1 은 `ledcAttach()` 의 반환값(bool)을 버렸습니다.** 그래서 LEDC 채널 붙이기가
실패해도 조용히 넘어갔고, 지금까지 원인을 알 방법이 없었습니다. ← **이게 진단 불가의 원인**

### v2 에서 넣은 진단 장치
1. `ledcAttachChannel()` 반환값을 부팅 로그와 `/status` 에 출력
2. `/servotest?ch=tilt` — 틸트만 단독으로 5도씩 자동 스윕 + 원인별 안내 출력
3. 점검 페이지(`/`)에서 폰으로 직접 상하 버튼 조작 가능

### 판정 트리 (이 순서로 좁힐 것)

```
부팅 로그의  [서보] TILT pin=15 ch=1 attach=??
├─ FAIL → LEDC 핀 충돌. TILT_PIN 을 14 로 바꿔 재업로드하면 끝.
└─ OK   → 소프트 정상. /servotest?ch=tilt 실행
          ├─ 움직인다      → 펌웨어 정상. 조종하는 쪽 명령 문제.
          ├─ 안 움직인다   → 신호선 배선 → 서보 5V → GND 공통 → 서보 고장 순
          └─ 떨리기만 한다 → 5V 전류 부족. 전원 별도 공급.
```

### 아직 확인 못 한 것 (사용자에게 물어볼 것)
- **SD 카드가 꽂혀 있는지** — GPIO 13/15 는 SD 카드 신호선과 공유됨. 꽂혀 있으면 빼고 테스트.
- **서보 5V 를 캠보드에서 따왔는지** — 별도 공급이어야 함. 캠보드에서 따면 전류 부족.
- **두 서보 신호선을 서로 바꿔 끼워봤는지** — 이게 결정적 교차 테스트.
  문제 서보가 13번 핀에서 잘 돌면 GPIO15/배선 문제, 바꿔도 안 돌면 서보 자체/기구부 걸림.

---

## 4. 미해결 ②: `http://172.30.1.41` 이 안 열림

원인 미확정. 아직 부팅 로그를 못 봤습니다. 확인 순서:

1. **시리얼 로그가 답** — `[WiFi] 연결됨! IP -> ???`
   - 다른 IP 가 찍혔으면 그 IP 로 접속하면 끝
   - `[WiFi] 연결중....` 에서 멈춤 → SSID/비밀번호, **2.4GHz 여부** (ESP32 는 5GHz 안 됨)
   - 로그가 처음부터 계속 반복 → 전원 부족(브라운아웃)
   - 아무것도 안 찍힘 → 보드 선택/포트/RX-TX 반대
2. **폰이 같은 와이파이인지** — LTE/5G 면 절대 안 열림. 가장 흔한 원인.
3. **PC 에서 `ping 172.30.1.41`** — 응답 있으면 보드 정상, 폰 쪽 문제
4. **정적 IP 충돌 배제** — v2 에 `#define USE_STATIC_IP 1` 을 넣어뒀음.
   `0` 으로 바꿔 올리면 DHCP 로 동작하고 시리얼에 IP 가 찍힘.
5. **공유기 단말 간 차단(AP isolation)** — PC ping 은 되는데 폰만 안 되면 이것.
   KT 공유기 설정에서 "무선 단말 간 차단" 해제.
6. **전원** — USB 5V 가 약하면 WiFi 연결 시점에 브라운아웃 리셋 반복.

---

## 5. 캠 펌웨어 v2 — v1 에서 고친 것

`saras_cam_esp32/saras_cam_esp32.ino` (약 490줄). **`/servo` 응답 형식은 v1 과 동일하게
유지**했으므로 기존 조종 페이지가 안 깨집니다 (`pan=90 tilt=90`, text/plain).

| # | 문제 | 수정 |
|---|---|---|
| 1 | **스트림 헤더 버퍼 넘침 (실제 버그)** — `char hdr[80]` 에 87바이트 헤더를 만들고 `snprintf` 반환값 `n=87` 로 전송 → 버퍼 밖 7바이트를 그대로 내보냄. Content-Length 가 잘려 스트림이 랜덤하게 끊김 | `hdr[128]` + 길이 클램프 |
| 2 | `camera_config_t c;` 미초기화 — 스택 쓰레기값이 안 채운 필드에 들어감 | `= {}` 로 0 초기화 |
| 3 | `/capture` 와 `/stream` 이 프레임버퍼를 동시에 잡아 다툼 | FreeRTOS 뮤텍스로 직렬화 |
| 4 | PSRAM 없을 때 VGA 초기화 실패 | QVGA+DRAM 자동 강등 + 1회 재시도 |
| 5 | 스트림 종료 시 마지막 chunk 미전송 (소켓 누수) | `httpd_resp_send_chunk(req, NULL, 0)` |
| 6 | 스트림 끊김/지연 | `WiFi.setSleep(false)` |
| 7 | WiFi 연결 실패 시 무한대기, loop 에 재연결 감시 없음 | 15초 타임아웃 재시도 + 5초마다 감시 |
| 8 | 확인 페이지 IP 하드코딩, `<img src=':81/stream'>` 잘못된 상대경로 | `location.hostname` 사용 |
| 9 | `ledcAttach` 반환값 버림 | 시리얼 + `/status` 로 보고 |

작성 중 컴파일 에러 2개도 잡았음:
- `HTTPD_503_SERVICE_UNAVAILABLE` 는 esp_http_server 에 **없는 상수** → `HTTPD_500_INTERNAL_SERVER_ERROR`
- `strcasecmp` → `strcmp` (헤더 의존 제거)

**아직 컴파일 검증은 안 됐습니다** (클라우드에 arduino-cli 가 없었음). 로컬에서 첫 컴파일 시
에러 가능성 있음. 요구사항: **ESP32 Arduino Core 3.x** (`ledcAttachChannel`, `ledcWrite(pin, duty)` 사용).

### 주소 목록
| 주소 | 설명 |
|---|---|
| `/` | 점검 페이지 (폰에서 서보 직접 조작) |
| `:81/stream` | MJPEG 실시간 영상 |
| `/capture` | JPEG 사진 한 장 |
| `/servo?pan=90&tilt=90` | 절대 각도 (pan 0~180, tilt 30~150) |
| `/servo?dp=10&dt=-10` | 상대 이동 |
| `/status` | 상태 JSON (서보 attach 여부, PSRAM, heap, RSSI) |
| `/servotest?ch=tilt` | 틸트 단독 자동 스윕 |

OTA: `saras-cam` / `saras1234`

### 배선
| 용도 | 핀 |
|---|---|
| 팬(좌우) 신호 | GPIO 13 |
| 틸트(상하) 신호 | GPIO 15 (안 되면 14 로 변경) |
| 서보 전원 | **별도 5V** (캠보드에서 따면 전류 부족) |
| GND | 공통 필수 |

**서보에 쓰면 안 되는 핀**: 0(XCLK), 4(플래시LED), 16(PSRAM), 12(부팅 스트래핑 — 보드 안 켜짐)

---

## 6. 로컬 세션이 바로 할 일

### Step 1. v2 소스 가져오기
브랜치 `claude/keen-knuth-6zarw9` 의 `saras_cam_esp32/` 폴더.
로컬 폴더가 git clone 이 아니면 GitHub 웹에서 해당 브랜치의 파일을 내려받으면 됩니다.

### Step 2. 컴파일 + 업로드 (로컬에서 직접 가능)
```cmd
arduino-cli core install esp32:esp32
arduino-cli compile --fqbn esp32:esp32:esp32cam saras_cam_esp32
arduino-cli board list
arduino-cli upload -p COM? --fqbn esp32:esp32:esp32cam saras_cam_esp32
```
아두이노 IDE 로 하셔도 됩니다 (보드: **AI Thinker ESP32-CAM**).

### Step 3. 시리얼 로그 수집 — 이게 제일 중요
```cmd
python saras_cam_esp32/cam_diag.py
```
또는 `캠_진단.bat` 더블클릭. COM 포트 자동 탐색 → 보드 리셋 → 15초 수집 →
서보/카메라/WiFi 자동 판정 → 찾은 IP 로 ping + `/status` 확인 → `캠진단결과.txt` 저장.

로컬 세션이라면 직접 읽어도 됩니다:
```cmd
arduino-cli monitor -p COM? -c baudrate=115200
```

기대 출력:
```
===== Saras CAM v2 부팅 =====
[서보] PAN  pin=13 ch=0 attach=OK
[서보] TILT pin=15 ch=1 attach=OK      ← 핵심
[카메라] OK (PSRAM 있음, VGA)
[WiFi] 정적 IP 사용: 172.30.1.41
[WiFi] 연결됨! IP -> 172.30.1.41 (RSSI -52 dBm)
```

### Step 4. 3장·4장의 판정 트리대로 좁히기

### Step 5. 실기기 테스트 10단계
| # | 테스트 | 통과 기준 |
|---|---|---|
| 1 | 부팅·WiFi | `[WiFi] 연결됨! IP -> ...` |
| 2 | 카메라 | `[카메라] OK` |
| 3 | 점검 페이지 | `http://<IP>/` 열림 |
| 4 | 사진 1장 | `/capture` JPEG, 반복 새로고침도 OK |
| 5 | **스트림** | `:81/stream` **30초 이상 안 끊김** (v1 버그 ①이 여기서 터졌음) |
| 6 | 서보 팬 | `/servo?pan=45` → `?pan=135` 좌우 움직임 |
| 7 | 서보 틸트 | `/servo?tilt=60` → `?tilt=120` 상하 움직임 |
| 8 | 상대이동 | `/servo?dp=10` 연타 시 10도씩 누적 |
| 9 | 스트림+캡처 동시 | 스트림 켠 채 `/capture` 둘 다 정상 (수정 ③) |
| 10 | OTA | 무선 업로드 성공 |

---

## 7. 그다음 (사용자 요청사항)

**핸드폰에서 조종할 수 있는 페이지를 만드는 것.** (PC용 조종 페이지가 아니라 폰 전용)

시작 전에 필요한 것:
1. **틸트 문제 해결 여부** — 상하가 살아있는지에 따라 UI 가 달라짐 (상하 버튼 vs 각도 슬라이더)
2. **모터 펌웨어의 명령 규약** — 전진/후진/조향을 어떤 URL·형식으로 받는지 모름.
   2-3 장의 "레포에 없는 것" 참고. 사용자에게 파일을 받아야 함.

디자인 참고: 기존 `car_door.html` 이 다크 테마(`#101418`) + 큰 버튼 + `viewport user-scalable=no`
구조라 폰에 맞춰져 있음. 같은 톤으로 맞추면 일관성이 생김.

---

## 8. 커밋 이력 (브랜치 `claude/keen-knuth-6zarw9`)

| 커밋 | 내용 |
|---|---|
| `7631e00` | 캠 펌웨어 v2 — 버그 수정 + 서보 진단 기능 |
| `a2b263d` | `USE_STATIC_IP` 토글 + 접속 실패 진단 문서 |
| `39f2132` | 캠 진단 도구 (`cam_diag.py`, `캠_진단.bat`) |

`main` 은 건드리지 않았습니다. 주식앱 파일도 전혀 수정하지 않았습니다.

---

# 9. 소스 전체 (여기서 파일로 복원)

아래 3개를 `saras_cam_esp32/` 폴더에 그대로 저장하세요.

## 9-1. `saras_cam_esp32/saras_cam_esp32.ino`

요구사항: 아두이노 보드 **AI Thinker ESP32-CAM**, **ESP32 Arduino Core 3.x**
(`ledcAttachChannel`, `ledcWrite(pin, duty)` 를 사용하므로 2.x 에서는 컴파일되지 않습니다)

```cpp
/*
  Saras Robot - ESP32-CAM 펌웨어 v2 (AI-Thinker 보드)
  ==================================================
  v1 대비 수정 내역
   [1] 스트림 헤더 버퍼 넘침 수정 (hdr[80] -> hdr[128] + 길이 클램프)  ★스트림 끊김 원인
   [2] camera_config_t 를 0으로 초기화 (안 채운 필드 쓰레기값 방지)
   [3] /capture 와 /stream 의 카메라 동시접근을 뮤텍스로 직렬화
   [4] PSRAM 없으면 QVGA 로 자동 강등 (VGA 초기화 실패 방지)
   [5] 스트림 종료 시 마지막 chunk 전송, WiFi.setSleep(false),
       WiFi 무한대기 제거 + loop 재연결 감시, 확인페이지 IP 하드코딩 제거
   [6] ledcAttach 성공/실패를 시리얼과 /status 로 보고  ★상하 서보 진단용
   [7] /status (JSON 상태) 와 /servotest (서보 단독 자동점검) 추가

  주소
   http://<IP>/                 : 점검 페이지 (폰에서 바로 서보 눌러볼 수 있음)
   http://<IP>:81/stream        : 실시간 영상 (MJPEG)
   http://<IP>/capture          : 사진 한 장 (AI 자율주행용)
   http://<IP>/servo?pan=90&tilt=90   : 절대 각도
   http://<IP>/servo?dp=10&dt=-10     : 상대 이동
   http://<IP>/status           : 상태 JSON (서보 attach 여부 포함)
   http://<IP>/servotest?ch=tilt      : 틸트만 단독 자동 스윕 (상하 고장 진단)
   OTA: saras-cam / saras1234

  서보 배선
   팬(좌우)  신호선 -> GPIO 13
   틸트(상하) 신호선 -> GPIO 15
   서보 전원 5V 는 반드시 별도 공급, GND 는 캠보드와 공통

  업로드: 보드 "AI Thinker ESP32-CAM" 선택
*/
#include "esp_camera.h"
#include <WiFi.h>
#include <ArduinoOTA.h>
#include "esp_http_server.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

// ===== WiFi =====
const char* ssid = "KT_GiGA_C991";
const char* pass = "heddbc2183";

// ===== 정적 IP =====
// 접속이 안 되면 USE_STATIC_IP 을 0 으로 바꿔 올리세요.
// 공유기가 IP 를 주고, 시리얼에 찍힌 그 IP 로 접속하면 됩니다. (정적 IP 충돌 배제용)
#define USE_STATIC_IP 1
IPAddress local_IP(172, 30, 1, 41);
IPAddress gateway (172, 30, 1, 1);
IPAddress subnet  (255, 255, 255, 0);
IPAddress dns1    (172, 30, 1, 1);

// ===== OTA =====
const char* OTA_NAME = "saras-cam";
const char* OTA_PASS = "saras1234";

// ===== 서보 =====
// AI-Thinker 에서 서보 신호선으로 써도 되는 핀: 13, 15, 14, 2
//  쓰면 안 되는 핀: 0(카메라 XCLK), 4(플래시 LED), 16(PSRAM), 12(부팅 스트래핑 - 보드 안 켜짐)
//  ※ 15번이 의심되면 아래 TILT_PIN 을 14 로만 바꿔서 다시 올려보면 핀 문제인지 바로 확인됨
#define PAN_PIN   13
#define TILT_PIN  15
#define PAN_CH     0      // LEDC 채널 고정 (카메라가 채널4/타이머2 를 쓰므로 0,1 은 안전)
#define TILT_CH    1
#define PAN_MIN    0
#define PAN_MAX  180
#define TILT_MIN  30      // 아래로 너무 꺾여 선 안 당기게 제한
#define TILT_MAX 150

int  panDeg  = 90;
int  tiltDeg = 90;
bool panOK   = false;     // ledcAttach 성공 여부
bool tiltOK  = false;
bool camOK   = false;

void servoWrite(int pin, int deg) {
  // 50Hz, 16bit. 0도=500us, 180도=2500us
  uint32_t us   = 500 + (uint32_t)deg * 2000 / 180;
  uint32_t duty = (uint32_t)((uint64_t)us * 65535 / 20000);
  ledcWrite(pin, duty);
}

void setServos() {
  panDeg  = constrain(panDeg,  PAN_MIN,  PAN_MAX);
  tiltDeg = constrain(tiltDeg, TILT_MIN, TILT_MAX);
  if (panOK)  servoWrite(PAN_PIN,  panDeg);
  if (tiltOK) servoWrite(TILT_PIN, tiltDeg);
}

// 한 서보만 천천히 훑기 (자동점검용)
static void sweep(int pin, int from, int to, int step, int ms) {
  if (from <= to) { for (int d = from; d <= to; d += step) { servoWrite(pin, d); delay(ms); } }
  else            { for (int d = from; d >= to; d -= step) { servoWrite(pin, d); delay(ms); } }
}

// ===== 카메라 핀 (AI-Thinker) =====
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22

httpd_handle_t httpd_main   = NULL;  // 80: /, /capture, /servo, /status, /servotest
httpd_handle_t httpd_stream = NULL;  // 81: /stream

// ---------- [3] 카메라 동시접근 직렬화 ----------
static SemaphoreHandle_t camLock = NULL;

static camera_fb_t* camGrab(uint32_t waitMs) {
  if (!camOK || camLock == NULL) return NULL;
  if (xSemaphoreTake(camLock, pdMS_TO_TICKS(waitMs)) != pdTRUE) return NULL;
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) xSemaphoreGive(camLock);   // 실패하면 바로 반납
  return fb;
}

static void camRelease(camera_fb_t *fb) {
  esp_camera_fb_return(fb);
  xSemaphoreGive(camLock);
}

// ---------- /capture ----------
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = camGrab(3000);
  if (!fb) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "camera busy");
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t r = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  camRelease(fb);
  return r;
}

// ---------- /servo?pan=..&tilt=..  또는 ?dp=..&dt=.. (상대이동) ----------
static esp_err_t servo_handler(httpd_req_t *req) {
  char q[128], v[16];
  if (httpd_req_get_url_query_str(req, q, sizeof(q)) == ESP_OK) {
    if (httpd_query_key_value(q, "pan",  v, sizeof(v)) == ESP_OK) panDeg  = atoi(v);
    if (httpd_query_key_value(q, "tilt", v, sizeof(v)) == ESP_OK) tiltDeg = atoi(v);
    if (httpd_query_key_value(q, "dp",   v, sizeof(v)) == ESP_OK) panDeg  += atoi(v);
    if (httpd_query_key_value(q, "dt",   v, sizeof(v)) == ESP_OK) tiltDeg += atoi(v);
  }
  setServos();
  // 응답 형식은 v1 과 동일하게 유지 (기존 조종 페이지 호환)
  char out[64];
  int n = snprintf(out, sizeof(out), "pan=%d tilt=%d", panDeg, tiltDeg);
  if (n > (int)sizeof(out) - 1) n = sizeof(out) - 1;
  httpd_resp_set_type(req, "text/plain");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, out, n);
}

// ---------- [7] /status : 상태 JSON ----------
static esp_err_t status_handler(httpd_req_t *req) {
  char out[384];
  int n = snprintf(out, sizeof(out),
    "{\"pan\":%d,\"tilt\":%d,"
    "\"panPin\":%d,\"tiltPin\":%d,"
    "\"panAttach\":%s,\"tiltAttach\":%s,"
    "\"tiltRange\":[%d,%d],"
    "\"camera\":%s,\"psram\":%s,"
    "\"heap\":%u,\"rssi\":%d,\"ip\":\"%s\",\"upSec\":%lu}",
    panDeg, tiltDeg,
    PAN_PIN, TILT_PIN,
    panOK ? "true" : "false", tiltOK ? "true" : "false",
    TILT_MIN, TILT_MAX,
    camOK ? "true" : "false", psramFound() ? "true" : "false",
    (unsigned)ESP.getFreeHeap(), (int)WiFi.RSSI(),
    WiFi.localIP().toString().c_str(), (unsigned long)(millis() / 1000));
  if (n > (int)sizeof(out) - 1) n = sizeof(out) - 1;
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, out, n);
}

// ---------- [7] /servotest?ch=pan|tilt : 서보 하나만 단독 자동점검 ----------
static esp_err_t servotest_handler(httpd_req_t *req) {
  char q[64], v[16];
  bool isTilt = false;
  if (httpd_req_get_url_query_str(req, q, sizeof(q)) == ESP_OK &&
      httpd_query_key_value(q, "ch", v, sizeof(v)) == ESP_OK) {
    if (strcmp(v, "tilt") == 0 || strcmp(v, "t") == 0) isTilt = true;
  }
  const int  pin  = isTilt ? TILT_PIN : PAN_PIN;
  const int  ch   = isTilt ? TILT_CH  : PAN_CH;
  const bool ok   = isTilt ? tiltOK   : panOK;
  const int  lo   = isTilt ? TILT_MIN : PAN_MIN;
  const int  hi   = isTilt ? TILT_MAX : PAN_MAX;
  const char* nm  = isTilt ? "tilt(상하)" : "pan(좌우)";

  char out[512];
  int n;
  if (!ok) {
    n = snprintf(out, sizeof(out),
      "%s 점검 불가\n"
      "pin=%d ch=%d attach=FAIL\n"
      "-> LEDC 채널을 못 잡았습니다. 핀 충돌입니다.\n"
      "   TILT_PIN 을 14 로 바꿔서 다시 올려보세요.\n", nm, pin, ch);
  } else {
    int mid = (lo + hi) / 2;
    sweep(pin, mid, lo,  5, 25);   // 중앙 -> 최소
    delay(300);
    sweep(pin, lo,  hi,  5, 25);   // 최소 -> 최대
    delay(300);
    sweep(pin, hi,  mid, 5, 25);   // 최대 -> 중앙
    if (isTilt) tiltDeg = mid; else panDeg = mid;

    n = snprintf(out, sizeof(out),
      "%s 스윕 완료\n"
      "pin=%d ch=%d attach=OK\n"
      "경로: %d -> %d -> %d -> %d (5도씩)\n"
      "\n"
      "지금 서보가 움직였나요?\n"
      "  움직였다 -> 펌웨어/핀 정상. 조종 명령 쪽 문제입니다.\n"
      "  안 움직였다 -> 신호선(GPIO %d) 배선, 서보 5V 전원,\n"
      "                 GND 공통 연결, 서보 자체 고장 순으로 확인.\n"
      "  떨리기만 한다 -> 5V 전류 부족입니다. 전원 분리 공급 필요.\n",
      nm, pin, ch, mid, lo, hi, mid, pin);
  }
  if (n > (int)sizeof(out) - 1) n = sizeof(out) - 1;
  httpd_resp_set_type(req, "text/plain; charset=utf-8");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, out, n);
}

// ---------- / (점검 페이지, IP 하드코딩 없음) ----------
static const char INDEX_HTML[] PROGMEM =
"<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>"
"<meta name='viewport' content='width=device-width,initial-scale=1,user-scalable=no'>"
"<title>Saras CAM 점검</title><style>"
"*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}"
"body{margin:0;padding:16px;background:#101418;color:#eee;font-family:'Malgun Gothic',sans-serif;text-align:center}"
"h3{margin:0 0 10px}"
"img{width:100%;max-width:480px;aspect-ratio:4/3;border-radius:12px;background:#000;object-fit:cover}"
"button{margin:4px;padding:14px 16px;font-size:16px;font-weight:700;border:0;border-radius:10px;background:#185FA5;color:#fff}"
"button:active{transform:scale(.96)}"
".t{background:#5D4037}.c{background:#1B5E20}"
"#log{margin-top:12px;font-size:13px;color:#8cf;white-space:pre-line;text-align:left;"
"max-width:480px;margin-left:auto;margin-right:auto;line-height:1.6}"
"a{color:#8cf}</style></head><body>"
"<h3>Saras CAM 점검</h3><img id='v'>"
"<div><button onclick=\"sv('dt=-10')\">상하 &minus;10</button>"
"<button class='c' onclick=\"sv('pan=90&tilt=90')\">중앙</button>"
"<button onclick=\"sv('dt=10')\">상하 &plus;10</button></div>"
"<div><button onclick=\"sv('dp=-10')\">좌우 &minus;10</button>"
"<button onclick=\"sv('dp=10')\">좌우 &plus;10</button></div>"
"<div><button class='t' onclick=\"go('/servotest?ch=pan')\">좌우 자동점검</button>"
"<button class='t' onclick=\"go('/servotest?ch=tilt')\">상하 자동점검</button></div>"
"<p><a href='/capture' target='_blank'>사진 1장</a> &middot; "
"<a href='/status' target='_blank'>상태 JSON</a></p><div id='log'></div>"
"<script>var L=document.getElementById('log');"
"document.getElementById('v').src='http://'+location.hostname+':81/stream';"
"function sv(q){go('/servo?'+q)}"
"function go(u){L.textContent='...';fetch(u).then(function(r){return r.text()})"
".then(function(t){L.textContent=t}).catch(function(e){L.textContent='실패: '+e})}"
"</script></body></html>";

static esp_err_t index_handler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html; charset=utf-8");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

// ---------- /stream (MJPEG, 포트 81) ----------
#define BOUNDARY "123456789000000000000987654321"
static const char* STREAM_PART =
  "\r\n--" BOUNDARY "\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t stream_handler(httpd_req_t *req) {
  char hdr[128];                 // [1] v1 은 80 이라 실제 87바이트 헤더가 잘려 나갔음
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=" BOUNDARY);
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");

  int miss = 0;
  while (true) {
    camera_fb_t *fb = camGrab(500);
    if (!fb) {
      if (++miss > 20) break;    // 프레임을 계속 못 잡으면 종료
      delay(20);
      continue;
    }
    miss = 0;

    int n = snprintf(hdr, sizeof(hdr), STREAM_PART, (unsigned)fb->len);
    if (n < 0) n = 0;
    if (n > (int)sizeof(hdr) - 1) n = sizeof(hdr) - 1;   // [1] 잘림 대비 클램프

    bool ok = (httpd_resp_send_chunk(req, hdr, n) == ESP_OK) &&
              (httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len) == ESP_OK);
    camRelease(fb);
    if (!ok) break;              // 클라이언트 끊김
  }
  httpd_resp_send_chunk(req, NULL, 0);   // [5] 마무리 chunk 로 소켓 정리
  return ESP_OK;
}

void startServers() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port      = 80;
  cfg.lru_purge_enable = true;
  cfg.max_uri_handlers = 8;
  httpd_uri_t u_index   = {.uri="/",          .method=HTTP_GET, .handler=index_handler,     .user_ctx=NULL};
  httpd_uri_t u_capture = {.uri="/capture",   .method=HTTP_GET, .handler=capture_handler,   .user_ctx=NULL};
  httpd_uri_t u_servo   = {.uri="/servo",     .method=HTTP_GET, .handler=servo_handler,     .user_ctx=NULL};
  httpd_uri_t u_status  = {.uri="/status",    .method=HTTP_GET, .handler=status_handler,    .user_ctx=NULL};
  httpd_uri_t u_svtest  = {.uri="/servotest", .method=HTTP_GET, .handler=servotest_handler, .user_ctx=NULL};
  if (httpd_start(&httpd_main, &cfg) == ESP_OK) {
    httpd_register_uri_handler(httpd_main, &u_index);
    httpd_register_uri_handler(httpd_main, &u_capture);
    httpd_register_uri_handler(httpd_main, &u_servo);
    httpd_register_uri_handler(httpd_main, &u_status);
    httpd_register_uri_handler(httpd_main, &u_svtest);
    Serial.println("[HTTP] 80 포트 시작");
  } else {
    Serial.println("[HTTP] 80 포트 시작 실패!");
  }

  httpd_config_t cfg2 = HTTPD_DEFAULT_CONFIG();
  cfg2.server_port      = 81;
  cfg2.ctrl_port        = 32769;
  cfg2.lru_purge_enable = true;
  httpd_uri_t u_stream = {.uri="/stream", .method=HTTP_GET, .handler=stream_handler, .user_ctx=NULL};
  if (httpd_start(&httpd_stream, &cfg2) == ESP_OK) {
    httpd_register_uri_handler(httpd_stream, &u_stream);
    Serial.println("[HTTP] 81 포트(스트림) 시작");
  } else {
    Serial.println("[HTTP] 81 포트 시작 실패!");
  }
}

// ---------- 카메라 초기화 ----------
static bool cameraInit() {
  camera_config_t c = {};            // [2] 0 초기화
  c.ledc_channel = LEDC_CHANNEL_4;   // 서보는 채널 0,1 -> 충돌 없음
  c.ledc_timer   = LEDC_TIMER_2;
  c.pin_d0 = Y2_GPIO_NUM;  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk     = XCLK_GPIO_NUM;
  c.pin_pclk     = PCLK_GPIO_NUM;
  c.pin_vsync    = VSYNC_GPIO_NUM;
  c.pin_href     = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn     = PWDN_GPIO_NUM;
  c.pin_reset    = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.grab_mode    = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    c.frame_size   = FRAMESIZE_VGA;      // 640x480
    c.jpeg_quality = 12;
    c.fb_count     = 2;
    c.fb_location  = CAMERA_FB_IN_PSRAM;
  } else {
    c.frame_size   = FRAMESIZE_QVGA;     // [4] PSRAM 없으면 VGA 는 초기화 실패함
    c.jpeg_quality = 15;
    c.fb_count     = 1;
    c.fb_location  = CAMERA_FB_IN_DRAM;
  }

  esp_err_t e = esp_camera_init(&c);
  if (e != ESP_OK) {
    Serial.printf("[카메라] 초기화 실패 0x%x -> QVGA 로 재시도\n", e);
    c.frame_size  = FRAMESIZE_QVGA;
    c.fb_count    = 1;
    c.fb_location = CAMERA_FB_IN_DRAM;
    e = esp_camera_init(&c);
  }
  if (e != ESP_OK) {
    Serial.printf("[카메라] 최종 초기화 실패 0x%x (카메라 리본 케이블 확인)\n", e);
    return false;
  }

  // 화면 뒤집기 (카메라가 뒤집혀 장착된 경우)
  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 1);
  }
  Serial.printf("[카메라] OK (PSRAM %s, %s)\n",
                psramFound() ? "있음" : "없음",
                psramFound() ? "VGA" : "QVGA");
  return true;
}

// ---------- WiFi ----------
static void wifiConnect() {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);              // [5] 절전 끄기 - 스트림 지연/끊김 방지
#if USE_STATIC_IP
  if (!WiFi.config(local_IP, gateway, subnet, dns1)) {
    Serial.println("[WiFi] 정적 IP 설정 실패 -> DHCP 로 진행");
  } else {
    Serial.printf("[WiFi] 정적 IP 사용: %s\n", local_IP.toString().c_str());
  }
#else
  Serial.println("[WiFi] DHCP 모드 (공유기가 IP 배정)");
#endif
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, pass);

  Serial.print("[WiFi] 연결중");
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
    if (millis() - t0 > 15000) {     // [5] 무한대기 대신 재시도
      Serial.println(" 15초 초과 -> 재시도");
      WiFi.disconnect();
      delay(200);
      WiFi.begin(ssid, pass);
      t0 = millis();
    }
  }
  Serial.printf("\n[WiFi] 연결됨! IP -> %s (RSSI %d dBm)\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n===== Saras CAM v2 부팅 =====");

  // ---- 서보 초기화 ([6] 성공/실패를 반드시 출력) ----
  panOK  = ledcAttachChannel(PAN_PIN,  50, 16, PAN_CH);
  tiltOK = ledcAttachChannel(TILT_PIN, 50, 16, TILT_CH);
  Serial.printf("[서보] PAN  pin=%2d ch=%d attach=%s\n", PAN_PIN,  PAN_CH,  panOK  ? "OK" : "FAIL");
  Serial.printf("[서보] TILT pin=%2d ch=%d attach=%s\n", TILT_PIN, TILT_CH, tiltOK ? "OK" : "FAIL");
  if (!tiltOK) {
    Serial.println("[서보] !! 틸트 LEDC 붙이기 실패 -> TILT_PIN 을 14 로 바꿔 보세요");
  }
  setServos();
  Serial.printf("[서보] 시작 위치 pan=%d tilt=%d (틸트 허용 %d~%d)\n",
                panDeg, tiltDeg, TILT_MIN, TILT_MAX);

  // ---- 카메라 ----
  camLock = xSemaphoreCreateMutex();
  if (camLock == NULL) Serial.println("[카메라] 뮤텍스 생성 실패!");
  camOK = cameraInit();

  // ---- WiFi ----
  wifiConnect();

  // ---- OTA ----
  ArduinoOTA.setHostname(OTA_NAME);
  ArduinoOTA.setPassword(OTA_PASS);
  ArduinoOTA.begin();

  startServers();

  String ip = WiFi.localIP().toString();
  Serial.println("---------------------------------------");
  Serial.println("점검  : http://" + ip + "/");
  Serial.println("스트림: http://" + ip + ":81/stream");
  Serial.println("캡처  : http://" + ip + "/capture");
  Serial.println("상태  : http://" + ip + "/status");
  Serial.println("상하점검: http://" + ip + "/servotest?ch=tilt");
  Serial.println("---------------------------------------");
}

void loop() {
  ArduinoOTA.handle();

  // [5] WiFi 끊김 감시 (5초마다)
  static uint32_t lastCheck = 0;
  if (millis() - lastCheck > 5000) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WiFi] 끊김 -> 재연결 시도");
      WiFi.disconnect();
      delay(100);
      WiFi.begin(ssid, pass);
    }
  }
  delay(2);
}
```

## 9-2. `saras_cam_esp32/cam_diag.py`

PC 에서 COM 포트를 자동으로 찾아 부팅 로그를 수집하고 판정까지 하는 도구.
로컬 세션이라면 이 스크립트를 직접 실행해서 출력을 읽으면 됩니다.

```python
# -*- coding: utf-8 -*-
"""
cam_diag.py — Saras CAM 자동 진단 (형님 PC 에서 실행)

하는 일:
  1. ESP32 가 붙은 COM 포트 자동 탐색
  2. 보드 리셋 후 부팅 로그 수집 (115200)
  3. 로그에서 서보 attach / 카메라 / WiFi IP 판정
  4. 그 IP 로 ping + HTTP 접속 확인
  5. 전체 결과를 캠진단결과.txt 로 저장

사용법:  캠_진단.bat 더블클릭   (또는  python cam_diag.py [COM3])
"""
import io
import re
import subprocess
import sys
import time
import urllib.request

BAUD = 115200
READ_SECONDS = 15
OUT_FILE = "캠진단결과.txt"

lines_out = []


def say(msg=""):
    print(msg)
    lines_out.append(msg)


def find_port(explicit=None):
    try:
        from serial.tools import list_ports
    except ImportError:
        return None, "pyserial 이 없습니다. 캠_진단.bat 으로 실행하세요."

    ports = list(list_ports.comports())
    if not ports:
        return None, "COM 포트가 하나도 없습니다. USB 케이블과 드라이버(CP2102/CH340)를 확인하세요."

    say("발견된 COM 포트:")
    for p in ports:
        say("  %-6s  %s" % (p.device, p.description))
    say()

    if explicit:
        for p in ports:
            if p.device.upper() == explicit.upper():
                return p.device, None
        return None, "%s 를 찾을 수 없습니다." % explicit

    # USB-시리얼 칩 우선 (블루투스 가상포트 제외)
    for key in ("CP210", "CH340", "CH910", "FTDI", "FT232", "USB 직렬", "USB Serial", "Silicon Labs"):
        for p in ports:
            if key.lower() in (p.description or "").lower():
                return p.device, None
    return ports[0].device, None


def grab_serial(port):
    import serial

    say("=" * 55)
    say("[1] %s 열기 (%d bps) → 보드 리셋 → %d초 수집" % (port, BAUD, READ_SECONDS))
    say("=" * 55)
    try:
        ser = serial.Serial(port, BAUD, timeout=0.3)
    except Exception as e:
        say("포트 열기 실패: %s" % e)
        say("→ 아두이노 IDE 의 시리얼 모니터가 열려 있으면 닫고 다시 실행하세요.")
        return ""

    # 정상 부팅 리셋 (DTR=GPIO0 high 유지, RTS=EN 을 잠깐 low)
    try:
        ser.dtr = False
        ser.rts = True
        time.sleep(0.15)
        ser.rts = False
    except Exception:
        pass

    ser.reset_input_buffer()
    buf = bytearray()
    t0 = time.time()
    while time.time() - t0 < READ_SECONDS:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
            sys.stdout.write(chunk.decode("utf-8", "replace"))
            sys.stdout.flush()
    ser.close()

    text = buf.decode("utf-8", "replace")
    lines_out.append(text)
    say()
    if not text.strip():
        say("!! 아무것도 수신되지 않았습니다.")
        say("   - 보드에 전원이 들어오는지 (빨간 LED)")
        say("   - RX/TX 를 서로 바꿔 꽂았는지")
        say("   - 다른 COM 포트인지 (python cam_diag.py COM5 처럼 지정)")
    return text


def judge(log):
    say("=" * 55)
    say("[2] 로그 판정")
    say("=" * 55)

    if not log.strip():
        say("  로그가 없어 판정 불가.")
        return None

    if log.count("Saras CAM v2 부팅") > 1 or log.count("rst:0x") > 2:
        say("  * 부팅이 반복됩니다 → 전원 부족(브라운아웃) 또는 크래시.")
        say("    5V 전원을 더 튼튼한 것으로 바꿔보세요.")

    if "Saras CAM v2" not in log:
        say("  * v2 펌웨어가 아닙니다. v2 를 먼저 업로드하세요.")
        say("    (v2 가 아니면 서보 진단 로그가 안 찍힙니다)")

    m = re.search(r"\[서보\]\s*PAN\s+pin=\s*(\d+)\s+ch=(\d+)\s+attach=(\w+)", log)
    if m:
        say("  PAN (좌우) : pin=%s ch=%s attach=%s" % m.groups())
    m = re.search(r"\[서보\]\s*TILT\s+pin=\s*(\d+)\s+ch=(\d+)\s+attach=(\w+)", log)
    if m:
        pin, ch, st = m.groups()
        say("  TILT(상하) : pin=%s ch=%s attach=%s" % (pin, ch, st))
        if st != "OK":
            say("    ==> 핀 충돌입니다. TILT_PIN 을 14 로 바꿔 재업로드하세요.")
        else:
            say("    ==> 소프트웨어 정상. 배선/5V전원/서보 고장 쪽입니다.")
            say("        /servotest?ch=tilt 로 스윕 시켜보세요.")
    else:
        say("  TILT 로그 없음 → v2 업로드 여부 확인 필요")

    if "[카메라] OK" in log:
        say("  카메라     : OK")
    elif "카메라" in log:
        for ln in log.splitlines():
            if "카메라" in ln:
                say("  카메라     : %s" % ln.strip())

    ip = None
    m = re.search(r"\[WiFi\] 연결됨! IP -> ([0-9.]+)", log)
    if m:
        ip = m.group(1)
        say("  WiFi       : 연결됨, IP = %s" % ip)
    elif "연결중" in log:
        say("  WiFi       : 연결 실패 (연결중... 에서 멈춤)")
        say("    ==> SSID/비밀번호, 2.4GHz 여부 확인. ESP32 는 5GHz 안 됩니다.")
    return ip


def check_net(ip):
    say()
    say("=" * 55)
    say("[3] 네트워크 확인  (%s)" % ip)
    say("=" * 55)
    try:
        r = subprocess.run(["ping", "-n", "3", ip], capture_output=True, text=True, timeout=25)
        out = r.stdout or r.stderr
        say(out.strip())
    except Exception as e:
        say("ping 실행 실패: %s" % e)

    for path in ("/status", "/"):
        url = "http://%s%s" % (ip, path)
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                body = resp.read(600).decode("utf-8", "replace")
            say("  %-28s HTTP %s" % (url, resp.status))
            if path == "/status":
                say("    %s" % body.strip())
        except Exception as e:
            say("  %-28s 실패: %s" % (url, e))


def main():
    say("Saras CAM 진단  (%s)" % time.strftime("%Y-%m-%d %H:%M:%S"))
    say()
    explicit = sys.argv[1] if len(sys.argv) > 1 else None
    port, err = find_port(explicit)
    if err:
        say(err)
    log = grab_serial(port) if port else ""
    ip = judge(log)
    if ip:
        check_net(ip)
    else:
        say()
        say("IP 를 못 찾아 네트워크 확인은 건너뜁니다.")

    say()
    say("=" * 55)
    say("끝. 이 파일(%s) 내용 전체를 클로드에게 붙여주세요." % OUT_FILE)
    say("=" * 55)

    with io.open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(str(x) for x in lines_out))


if __name__ == "__main__":
    main()
```

## 9-3. `saras_cam_esp32/캠_진단.bat`

사용자가 더블클릭으로 돌릴 수 있는 실행 파일. `pyserial` 을 알아서 설치합니다.
(로컬 클로드가 직접 `python cam_diag.py` 를 돌릴 수 있으면 이 파일은 없어도 됩니다)

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Saras CAM 진단

echo ============================================
echo   Saras CAM 자동 진단
echo ============================================
echo.
echo   * 아두이노 IDE 의 시리얼 모니터가 열려 있으면 닫아주세요
echo     (포트를 한 프로그램만 쓸 수 있습니다)
echo.
pause

echo.
echo [준비] pyserial 확인...
python -m pip install --quiet --disable-pip-version-check pyserial
if errorlevel 1 (
  echo   pyserial 설치 실패. python 이 설치되어 있는지 확인하세요.
  pause
  exit /b 1
)

echo [실행] 진단 시작 ^(보드 자동 리셋 후 15초 수집^)
echo.
python cam_diag.py %1

echo.
echo ============================================
echo   결과가 캠진단결과.txt 에 저장되었습니다.
echo   이 파일을 열어서 내용 전체를 클로드에게 붙여주세요.
echo ============================================
echo.
notepad 캠진단결과.txt
pause
```
