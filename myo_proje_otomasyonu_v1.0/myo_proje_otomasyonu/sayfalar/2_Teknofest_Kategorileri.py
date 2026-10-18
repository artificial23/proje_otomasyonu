import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import select

from modules import matcher, settings, teknofest_scraper, ui
from modules.database import Kullanici, TeknofestKategori, get_session
from modules.text_utils import fold

GUNLER = {"mon": "Pazartesi", "tue": "Salı", "wed": "Çarşamba", "thu": "Perşembe", "fri": "Cuma", "sat": "Cumartesi", "sun": "Pazar"}

u = ui.require_user()
st.title("🚀 TEKNOFEST Yarışmaları")
st.caption("Ön Lisans / Üniversite seviyesine uygun yarışmalar, son başvuru geri sayımları ve şartnameler")

son = settings.get("son_tarama")
ozet = settings.get("son_tarama_ozet") or {}
bilgi = st.container(horizontal=True, vertical_alignment="center")
bilgi.caption(f"Son tarama: {son or 'henüz yapılmadı'}"
              + (f" · {ozet.get('bulunan', 0)} yarışma, {ozet.get('onlisans_uygun', 0)} ön lisansa uygun" if ozet else "")
              + f" · Otomatik tarama: her {GUNLER.get(str(settings.get('teknofest_tarama_gunu')), 'hafta')} {settings.get_int('teknofest_tarama_saati'):02d}:00")
if u.rol == "admin":
    with st.expander("🛰️ Taramayı şimdi çalıştır"):
        st.write("teknofest.org/tr/yarismalar sayfası ve tüm yarışma sayfaları taranır; ön lisansa uygun olanların şartnameleri "
                 "indirilir ve geçmiş yıl dereceleri Ödüllü Projeler Arşivi'ne eklenir. Yaklaşık 1–3 dakika sürer.")
        c1, c2 = st.columns(2)
        hizli = c1.checkbox("Deneme: yalnızca ilk 5 yarışma")
        if c2.button("Taramayı başlat", type="primary"):
            bar = st.progress(0.0, "Başlıyor…")
            sonuc = teknofest_scraper.run_scrape(progress=lambda x, m: bar.progress(min(1.0, x), m), limit=5 if hizli else None)
            if sonuc["hatalar"]:
                st.warning(f"{len(sonuc['hatalar'])} uyarı:\n\n" + "\n".join(f"- {h}" for h in sonuc["hatalar"][:10]))
            st.success(f"{sonuc['bulunan']} yarışma tarandı · {sonuc['yeni']} yeni · {sonuc['guncellenen']} güncellendi · "
                       f"{sonuc['sartname']} şartname · {sonuc['arsiv']} arşiv kaydı")

tab1, tab2 = st.tabs(["🏁 Yarışmalar", "🧭 Projeme uygun yarışmayı bul"])

with tab1:
    f1, f2, f3 = st.columns([2, 2, 1.4])
    seviye = f1.segmented_control("Seviye", ["Ön lisansa uygun", "Belirsiz dahil", "Tümü"], default="Belirsiz dahil")
    arama = f2.text_input("Ara", placeholder="ör. robot, İHA, yapay zeka")
    sadece_acik = f3.toggle("Başvurusu açık olanlar", value=False, help="Son başvuru tarihi geçmemiş olanlar")
    takip_modu = f3.toggle("Takip ettiklerim", value=False)

    with get_session() as s:
        kats = list(s.scalars(select(TeknofestKategori).where(TeknofestKategori.aktif.is_(True))))
    bugun = dt.date.today()
    if seviye == "Ön lisansa uygun":
        kats = [k for k in kats if k.onlisans_uygun]
    elif seviye == "Belirsiz dahil" or seviye is None:
        kats = [k for k in kats if k.onlisans_uygun is not False]
    if arama:
        a = fold(arama)
        kats = [k for k in kats if a in fold(f"{k.kategori_adi} {k.anahtar_kelimeler} {k.aciklama}")]
    if sadece_acik:
        kats = [k for k in kats if k.son_basvuru_tarihi and k.son_basvuru_tarihi >= bugun]
    takip = set(u.takip_edilen_kategoriler or [])
    if takip_modu:
        kats = [k for k in kats if k.id in takip]
    kats.sort(key=lambda k: (k.son_basvuru_tarihi is None or k.son_basvuru_tarihi < bugun,
                             k.son_basvuru_tarihi or dt.date.max, k.kategori_adi))
    st.write(f"**{len(kats)}** yarışma")

    cols = st.columns(2)
    for i, k in enumerate(kats):
        with cols[i % 2].container(border=True):
            kalan = (k.son_basvuru_tarihi - bugun).days if k.son_basvuru_tarihi else None
            seviye_rozet = (":green-badge[Ön lisans / Üniversite]" if k.onlisans_uygun else
                            ":gray-badge[Ön lisans dışı]" if k.onlisans_uygun is False else ":orange-badge[Seviye: tarama bekleniyor]")
            st.markdown(f"{seviye_rozet} {ui.kalan_rozet(kalan)}" + (" :violet-badge[Takipte]" if k.id in takip else ""))
            st.markdown(f"<div class='kart-baslik'>{ui.esc(k.kategori_adi)}</div>", unsafe_allow_html=True)
            satir = []
            if k.son_basvuru_tarihi:
                satir.append(f"Son başvuru: **{ui.tarih(k.son_basvuru_tarihi)}**")
            if k.odul_miktari:
                satir.append(f"🏆 {ui.esc(k.odul_miktari)}")
            if k.takim_min or k.takim_max:
                satir.append(f"👥 {k.takim_min or '?'}–{k.takim_max or '?'} kişi")
            if satir:
                st.markdown(" · ".join(satir))
            if k.katilim_seviyesi and k.kaynak == "scraper":
                st.caption(f"Katılım: {k.katilim_seviyesi}")
            btn = st.container(horizontal=True)
            if k.sartname_yerel_yol and Path(k.sartname_yerel_yol).exists():
                btn.download_button("📄 Şartname", Path(k.sartname_yerel_yol).read_bytes(), file_name=Path(k.sartname_yerel_yol).name,
                                    mime="application/pdf", key=f"sp_{k.id}")
            elif k.sartname_pdf_url:
                btn.link_button("📄 Şartname", k.sartname_pdf_url)
            if k.url:
                btn.link_button("Sayfa", k.url)
            if btn.button("Takibi bırak" if k.id in takip else "🔔 Takip et", key=f"tk_{k.id}",
                          help="Takip ettiğiniz yarışmaların son tarihleri için 10 ve 3 gün kala hatırlatma alırsınız."):
                yeni = sorted(takip - {k.id}) if k.id in takip else sorted(takip | {k.id})
                with get_session() as s:
                    s.get(Kullanici, u.id).takip_edilen_kategoriler = yeni
                st.rerun()
            if k.takvim or k.rapor_sablonlari or k.aciklama:
                with st.expander("Ayrıntılar"):
                    if k.aciklama:
                        st.write(k.aciklama[:1200] + ("…" if len(k.aciklama) > 1200 else ""))
                    if k.takvim:
                        st.dataframe(pd.DataFrame([{"Aşama": t["asama"], "Tarih": dt.date.fromisoformat(t["tarih"]).strftime("%d.%m.%Y")}
                                                   for t in k.takvim]), hide_index=True, width="stretch")
                    for r in k.rapor_sablonlari or []:
                        st.markdown(f"- [{ui.esc(r.get('ad') or 'Rapor şablonu')}]({r['url']})")
            if u.rol == "admin":
                with st.expander("✏️ Düzenle (yönetici)"):
                    with st.form(f"kat_{k.id}"):
                        uy = st.selectbox("Ön lisansa uygun mu?", ["Bilinmiyor", "Evet", "Hayır"],
                                          index=0 if k.onlisans_uygun is None else (1 if k.onlisans_uygun else 2))
                        sb = st.date_input("Son başvuru tarihi", value=k.son_basvuru_tarihi, format="DD.MM.YYYY")
                        anahtar = st.text_area("Anahtar kelimeler (eşleştirme için)", value=k.anahtar_kelimeler or "")
                        sart = st.text_input("Şartname PDF bağlantısı", value=k.sartname_pdf_url or "")
                        if st.form_submit_button("Kaydet"):
                            with get_session() as s:
                                kk = s.get(TeknofestKategori, k.id)
                                kk.onlisans_uygun = {"Bilinmiyor": None, "Evet": True, "Hayır": False}[uy]
                                kk.son_basvuru_tarihi = sb
                                kk.anahtar_kelimeler = anahtar
                                if sart != (kk.sartname_pdf_url or ""):
                                    kk.sartname_pdf_url, kk.sartname_yerel_yol = sart or None, None
                            st.rerun()

    if u.rol == "admin":
        with st.expander("➕ Elle yarışma ekle"):
            with st.form("yeni_kat"):
                ad = st.text_input("Yarışma adı")
                url = st.text_input("Sayfa bağlantısı")
                sb = st.date_input("Son başvuru tarihi", value=None, format="DD.MM.YYYY")
                anahtar = st.text_area("Anahtar kelimeler")
                if st.form_submit_button("Ekle") and ad:
                    teknofest_scraper.save_category({"kategori_adi": ad, "son_basvuru_tarihi": sb, "onlisans_uygun": True},
                                                    teknofest_scraper.slug_from_name(ad), url, kaynak="manuel")
                    with get_session() as s:
                        kk = s.scalar(select(TeknofestKategori).where(TeknofestKategori.slug == teknofest_scraper.slug_from_name(ad)))
                        kk.anahtar_kelimeler = anahtar
                    st.rerun()

with tab2:
    st.write("Proje fikrinizi yazın; sistem TF-IDF benzerliğiyle en uygun TEKNOFEST kategorilerini önersin.")
    metin = st.text_area("Proje başlığı ve kısa özet", height=140,
                         placeholder="Ör. Atölyede malzeme taşıyan, QR kod okuyarak istasyonlar arasında gezen otonom mobil robot…")
    if st.button("Eşleştir", type="primary") and metin.strip():
        es = matcher.teknofest_eslestir(metin[:120], metin, "", u.yetkinlikler if u.rol == "ogrenci" else [], top_n=5)
        if not es:
            st.info("Eşik üzerinde eşleşme bulunamadı; metni biraz daha ayrıntılandırmayı deneyin.")
        for e in es:
            st.progress(min(1.0, e["skor"] / 60), f"{e['kategori_adi']} — uyum %{e['skor']:g}")
