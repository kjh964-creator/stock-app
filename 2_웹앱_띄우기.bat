@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ============================================
echo  주식정보 웹앱 시작
echo ============================================
echo.
echo  본 PC 에서 접속:
echo    http://localhost:8501
echo.
echo  같은 와이파이의 폰/태블릿에서 접속하려면
echo  아래 IP 주소를 폰 브라우저에 입력하세요:
echo.
ipconfig | findstr /R /C:"IPv4.*"
echo.
echo  → 위 IPv4 주소 뒤에 ":8501" 붙이기
echo    예) http://192.168.1.10:8501
echo.
echo  ⚠️ 처음 실행 시 Windows 방화벽 알림 뜨면
echo     "액세스 허용" 클릭하세요.
echo.
echo  종료: 이 창에서 Ctrl+C
echo ============================================
echo.
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
pause
