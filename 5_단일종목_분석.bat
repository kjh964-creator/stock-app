@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ============================================
echo  단일 종목 분석
echo ============================================
echo.
set /p TICKER="종목 코드 또는 이름 입력 (예: 005930 또는 삼성전자): "
if "%TICKER%"=="" (
    echo 입력값 없음. 종료합니다.
    pause
    exit /b
)
python analyze_stock.py %TICKER%
echo.
pause
