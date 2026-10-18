FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    TZ=Europe/Istanbul \
    KULUCKA_VERI_DIZINI=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
