"""Akıllı Proje Kuluçka ve Otomasyon Sistemi — Streamlit ana giriş noktası.

Çalıştırma:  streamlit run app.py
"""
from __future__ import annotations

import logging

import streamlit as st

from modules import config, notifier, settings, ui
from modules.database import has_admin, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

st.set_page_config(page_title="Proje Kuluçka", page_icon="🎓", layout="wide")
init_db()
ui.start_embedded_scheduler()
ui.cerez_isle()

if not has_admin():
    ui.setup_wizard()
    st.stop()

user = ui.current_user()
if not user:
    ui.login_screen()
    st.stop()

if user.sifre_degismeli or not user.kvkk_onay:
    ui.zorunlu_sifre_degistir(user)
    st.stop()

# Davet bağlantısıyla gelindiyse profil sayfasına yönlendirme bilgisi
davet = st.query_params.get("davet") or st.session_state.get("bekleyen_davet")
if davet and user.rol == "ogrenci":
    st.session_state["acik_davet"] = davet
st.session_state.pop("bekleyen_davet", None)
if "davet" in st.query_params:
    del st.query_params["davet"]

P = "sayfalar/"
ana = st.Page(P + "0_Ana_Sayfa.py", title="Ana Sayfa", icon=":material/home:", default=True)
pano = st.Page(P + "1_Proje_Eslestirme_Panosu.py", title="Proje Panosu", icon=":material/view_kanban:", url_path="proje-panosu")
tf = st.Page(P + "2_Teknofest_Kategorileri.py", title="TEKNOFEST Yarışmaları", icon=":material/rocket_launch:", url_path="teknofest")
arsiv = st.Page(P + "3_Odullu_Projeler_Arsivi.py", title="Ödüllü Projeler Arşivi", icon=":material/emoji_events:", url_path="arsiv")
danisman = st.Page(P + "4_Danisman_Onay_ve_Otomasyon.py", title="Danışman Paneli", icon=":material/fact_check:", url_path="danisman")
profil = st.Page(P + "5_Profilim.py", title="Profilim", icon=":material/person:", url_path="profil")
yonetim = st.Page(P + "6_Yonetim_Paneli.py", title="Yönetim Paneli", icon=":material/settings:", url_path="yonetim")

sayfalar = {"Keşfet": [ana, pano, tf, arsiv]}
if user.rol in ("hoca", "sanayi", "admin"):
    sayfalar["Yönet"] = [danisman]
sayfalar["Hesabım"] = [profil]
if user.rol == "admin":
    sayfalar["Hesabım"].append(yonetim)

with st.sidebar:
    st.markdown(f"**{ui.ROL_IKON.get(user.rol, '')} {ui.esc(user.ad_soyad)}**")
    st.caption(f"{ui.auth.ROLLER.get(user.rol, user.rol)} · {settings.get('kurum_adi')}")
    okunmamis = notifier.okunmamis_sayisi(user.id)
    if okunmamis:
        st.caption(f"🔔 {okunmamis} okunmamış bildirim (Ana Sayfa)")
    if st.button("Çıkış yap", icon=":material/logout:", width="stretch"):
        ui.logout()

pg = st.navigation(sayfalar, position="sidebar")
if st.session_state.get("acik_davet") and pg.title not in ("Profilim",):
    st.info("📩 Bir takım davetiniz var: **Profilim > Davetlerim** bölümünden yanıtlayabilirsiniz.")
pg.run()

with st.sidebar:
    st.divider()
    st.caption(f"{config.APP_NAME} · v{config.APP_VERSION}")
