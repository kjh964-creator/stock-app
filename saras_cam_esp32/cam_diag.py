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
