@echo off
chcp 65001 >nul
title Proje Kulucka
cd /d "%~dp0"
set PYTHONUTF8=1

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo [HATA] Python bulunamadi.
  echo https://www.python.org/downloads/ adresinden Python 3.11 veya ustunu kurun
  echo ve kurulumda "Add Python to PATH" kutusunu isaretleyin.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Ilk kurulum yapiliyor, bu islem birkac dakika surebilir...
  python -m venv .venv
  if errorlevel 1 ( pause & exit /b 1 )
)

if not exist ".venv\kurulum_tamam.txt" (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [HATA] Paketler kurulamadi. Internet baglantinizi kontrol edin.
    pause
    exit /b 1
  )
  echo tamam> ".venv\kurulum_tamam.txt"
)

echo.
echo Proje Kulucka baslatiliyor: http://localhost:8501
echo Kapatmak icin bu pencereyi kapatin.
echo.
start "" /b cmd /c "ping -n 7 127.0.0.1 >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.port 8501
pause
