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
