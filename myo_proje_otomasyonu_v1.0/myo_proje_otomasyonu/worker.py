"""Arka plan zamanlayıcısı (sunucu kurulumları için ayrı süreç).

Kullanım:
    KULUCKA_ZAMANLAYICI=harici streamlit run app.py   # arayüz (zamanlayıcısız)
    python worker.py                                  # zamanlanmış görevler

Tek bilgisayar kurulumunda buna gerek yoktur: zamanlayıcı varsayılan olarak
Streamlit uygulamasının içinde çalışır.
"""
import logging

from modules import scheduler

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    scheduler.run_blocking()
