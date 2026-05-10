@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ============================================
echo  Python 라이브러리 설치/업데이트
echo  처음 한 번만 실행하면 됩니다
echo ============================================
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo ============================================
echo  설치 완료. 아무 키나 누르면 닫힙니다.
echo ============================================
pause >nul
