import streamlit as st
from sqlalchemy import func, select

from modules import automation, matcher, rules, settings, ui
from modules.database import Basvuru, Bildirim, Davet, Proje, TeknofestKategori, get_session

u = ui.require_user()

st.title(f"Merhaba, {u.ad_soyad.split()[0] if u.ad_soyad else ''} 👋")
st.caption(f"{settings.get('universite_adi') or ''} {settings.get('kurum_adi')} · Aktif dönem: {settings.get('aktif_donem')}")

if u.rol == "ogrenci" and not u.yetkinlikler:
    st.warning("Profilinizde yetkinlik yok. Size uygun projeleri ve takım davetlerini alabilmek için **Profilim** sayfasından yetkinliklerinizi ekleyin.")

donem = str(settings.get("aktif_donem"))
yaklasan = automation.yaklasan_son_tarihler(gun=90)
with get_session() as s:
    acik_ilan = s.scalar(select(func.count()).select_from(Proje).where(Proje.durum == "Acik")) or 0
    tf_uygun = s.scalar(select(func.count()).select_from(TeknofestKategori).where(
        TeknofestKategori.aktif.is_(True), TeknofestKategori.onlisans_uygun.is_(True))) or 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Açık proje ilanı", acik_ilan)
c2.metric("Ön lisansa uygun yarışma", tf_uygun, help="TEKNOFEST yarışmaları. Seviyesi belirsiz olanlar ilk taramadan sonra netleşir.")
if yaklasan:
    c3.metric("En yakın son tarih", f"{yaklasan[0]['kalan']} gün", help=yaklasan[0]["baslik"])
else:
    c3.metric("En yakın son tarih", "—")
if u.rol == "ogrenci":
    with get_session() as s:
        bekleyen_davet = s.scalar(select(func.count()).select_from(Davet).where(Davet.ogrenci_id == u.id, Davet.durum == "Gonderildi")) or 0
    c4.metric("Bekleyen davetim", bekleyen_davet)
elif u.rol in ("hoca", "admin"):
    _, sayi, limit = rules.kota_uygun_mu(u.id, "2209-A", donem)
    c4.metric("2209 danışmanlık kotam", f"{sayi}/{limit}")
else:
    c4.metric("İlanlarım", len(automation.hoca_projeleri(u.id)))

sol, sag = st.columns([3, 2], gap="large")

with sol:
    st.subheader("⏰ Yaklaşan son tarihler")
    if not yaklasan:
        st.info("Önümüzdeki 90 gün içinde kayıtlı son tarih yok. TEKNOFEST tarihleri tarama sonrasında burada görünür.")
    for it in yaklasan[:8]:
        with st.container(border=True):
            a, b = st.columns([4, 1.4])
            a.markdown(f"**{ui.esc(it['baslik'])}**  \n<span class='soluk'>{ui.tarih(it['tarih'])} · {ui.esc(it['program'])}</span>",
                       unsafe_allow_html=True)
            b.markdown(ui.kalan_rozet(it["kalan"]))
            if it.get("url"):
                b.link_button("Aç", it["url"], width="stretch")
    if yaklasan:
        st.download_button("📅 Takvime ekle (.ics)", automation.ics_olustur(yaklasan), file_name="proje_son_tarihler.ics",
                           mime="text/calendar")

    if u.rol == "ogrenci":
        st.subheader("✨ Size uygun ilanlar")
        with get_session() as s:
            acik = list(s.scalars(select(Proje).where(Proje.durum == "Acik")))
        skorlar = matcher.ogrenciye_uygun_projeler(u, acik)
        en_iyi = sorted(acik, key=lambda p: skorlar.get(p.id, 0), reverse=True)[:3]
        if not en_iyi:
            st.caption("Şu an açık ilan yok.")
        for p in en_iyi:
            with st.container(border=True):
                st.markdown(f"{ui.tur_rozet(p.tur)} **{ui.esc(p.baslik)}**")
                st.caption(f"Yetkinlik uyumunuz: %{skorlar.get(p.id, 0):g}")
        if en_iyi:
            st.page_link("sayfalar/1_Proje_Eslestirme_Panosu.py", label="Tüm ilanlara git", icon=":material/arrow_forward:")
    elif u.rol in ("hoca", "sanayi", "admin"):
        st.subheader("📥 Onay bekleyen başvurular")
        projeler = automation.hoca_projeleri(u.id) if u.rol != "admin" else []
        if u.rol == "admin":
            with get_session() as s:
                projeler = list(s.scalars(select(Proje)))
        ids = [p.id for p in projeler]
        with get_session() as s:
            bekleyen = s.scalar(select(func.count()).select_from(Basvuru).where(Basvuru.proje_id.in_(ids or [0]), Basvuru.durum == "Beklemede")) or 0
        st.write(f"**{bekleyen}** başvuru kararınızı bekliyor.")
        st.page_link("sayfalar/4_Danisman_Onay_ve_Otomasyon.py", label="Danışman Paneli'ne git", icon=":material/arrow_forward:")

with sag:
    st.subheader("🔔 Bildirimlerim")
    with get_session() as s:
        bildirimler = list(s.scalars(select(Bildirim).where(Bildirim.kullanici_id == u.id, Bildirim.kanal == "uygulama")
                                     .order_by(Bildirim.olusturma.desc()).limit(15)))
    if not bildirimler:
        st.caption("Henüz bildirim yok.")
    else:
        if st.button("Tümünü okundu işaretle", width="stretch"):
            with get_session() as s:
                for b in s.scalars(select(Bildirim).where(Bildirim.kullanici_id == u.id, Bildirim.okundu.is_(False))):
                    b.okundu = True
            st.rerun()
    for b in bildirimler:
        with st.expander(("🔵 " if not b.okundu else "") + b.konu, expanded=False):
            st.caption(ui.tarih(b.olusturma))
            st.text(b.icerik)
