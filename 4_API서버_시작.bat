@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ============================================
echo  API 서버 시작 (localhost:8000)
echo  문서 보기: http://localhost:8000/docs
echo  종료: Ctrl+C
echo ============================================
echo.
python -m uvicorn server:app --reload --port 8000
pause
