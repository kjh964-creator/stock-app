@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ============================================
echo  이벤트 체크 (3% 이상 등락 / 거래량 급증)
echo ============================================
echo.
python event_alert.py
echo.
pause
