#!/usr/bin/env bash
# Proje Kuluçka — macOS / Linux başlatma betiği
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[HATA] python3 bulunamadı. Python 3.11+ kurun: https://www.python.org/downloads/"
  exit 1
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "İlk kurulum yapılıyor, birkaç dakika sürebilir..."
  "$PY" -m venv .venv
fi
if [ ! -f ".venv/kurulum_tamam.txt" ]; then
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  echo tamam > .venv/kurulum_tamam.txt
fi
echo "Proje Kuluçka başlatılıyor: http://localhost:8501  (durdurmak için Ctrl+C)"
( sleep 6; .venv/bin/python -m webbrowser -t http://localhost:8501 >/dev/null 2>&1 ) &
exec .venv/bin/python -m streamlit run app.py --server.port 8501
