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
  if (!WiFi.config(local_IP, gateway, subnet, dns1)) {
    Serial.println("[WiFi] 정적 IP 설정 실패 -> DHCP 로 진행");
  }
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
