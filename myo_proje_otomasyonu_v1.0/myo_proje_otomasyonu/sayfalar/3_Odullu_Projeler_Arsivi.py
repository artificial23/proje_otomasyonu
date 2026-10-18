import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from modules import importer, ui
from modules.database import OdulluProje, TeknofestKategori, get_session
from modules.text_utils import fold, parse_list

u = ui.require_user()
st.title("🏆 Ödüllü Projeler Arşivi")
st.caption("Geçmiş yıllarda TEKNOFEST'te derece alan projeler ve kurum içinde destek kazanan 2209 / bitirme projeleri — ilham kartları")

with get_session() as s:
    kayitlar = list(s.scalars(select(OdulluProje).order_by(OdulluProje.yil.desc(), OdulluProje.kategori_adi)))
    kategoriler = {k.id: k.kategori_adi for k in s.scalars(select(TeknofestKategori))}

if not kayitlar:
    st.info("Arşiv henüz boş. TEKNOFEST taraması geçmiş yıl derecelerini otomatik ekler; sonuçlanan kurum projeleri de "
            "danışman sonucu girdiğinde buraya aktarılır. Yöneticiler Excel ile toplu kayıt yükleyebilir.")

programlar = sorted({k.program for k in kayitlar})
kat_adlari = sorted({k.kategori_adi for k in kayitlar if k.kategori_adi})
yillar = sorted({k.yil for k in kayitlar if k.yil}, reverse=True)

f1, f2, f3, f4 = st.columns([1.4, 2.4, 1.2, 2])
prog = f1.multiselect("Program", programlar, placeholder="Tümü")
kat = f2.multiselect("Kategori", kat_adlari, placeholder="Tümü")
yil = f3.multiselect("Yıl", yillar, placeholder="Tümü")
arama = f4.text_input("Ara", placeholder="takım, proje, teknoloji, kurum")

liste = kayitlar
if prog:
    liste = [k for k in liste if k.program in prog]
if kat:
    liste = [k for k in liste if k.kategori_adi in kat]
if yil:
    liste = [k for k in liste if k.yil in yil]
if arama:
    a = fold(arama)
    liste = [k for k in liste if a in fold(f"{k.proje_adi} {k.takim_adi} {k.kurum_adi} {k.proje_ozeti} {' '.join(k.kullanilan_teknolojiler or [])}")]

m1, m2, m3 = st.columns(3)
m1.metric("Kayıt", len(liste))
m2.metric("Kategori", len({k.kategori_adi for k in liste}))
m3.metric("Kurum içi başarı", sum(1 for k in liste if (k.kaynak or "").startswith("Kurum")))

cols = st.columns(3)
for i, k in enumerate(liste[:300]):
    with cols[i % 3].container(border=True):
        derece_renk = "orange" if "1" in (k.derece or "")[:3] or "birinci" in fold(k.derece) else "violet"
        st.markdown(f":{derece_renk}-badge[{ui.esc(k.derece) or 'Derece'}] :gray-badge[{k.yil or '—'}] :blue-badge[{k.program}]"
                    + (" :red-badge[DEMO]" if k.kaynak == "DEMO" else ""))
        st.markdown(f"<div class='kart-baslik'>{ui.esc(k.proje_adi or k.takim_adi)}</div>", unsafe_allow_html=True)
        alt = []
        if k.proje_adi and k.takim_adi:
            alt.append(f"Takım: {ui.esc(k.takim_adi)}")
        if k.kurum_adi:
            alt.append(ui.esc(k.kurum_adi))
        alt.append(ui.esc(k.kategori_adi))
        st.markdown(f"<span class='soluk'>{' · '.join(alt)}</span>", unsafe_allow_html=True)
        if k.kullanilan_teknolojiler:
            st.markdown(ui.chips(k.kullanilan_teknolojiler), unsafe_allow_html=True)
        if k.proje_ozeti:
            with st.expander("Özet"):
                st.write(k.proje_ozeti)
        if k.rapor_url:
            st.link_button("Rapor / kaynak", k.rapor_url)
        if u.rol == "admin":
            if st.button("Sil", key=f"sil_{k.id}", type="tertiary"):
                with get_session() as s:
                    s.delete(s.get(OdulluProje, k.id))
                st.rerun()
if len(liste) > 300:
    st.caption("İlk 300 kayıt gösteriliyor; filtreleri daraltın.")

if u.rol in ("hoca", "admin"):
    st.divider()
    with st.expander("➕ Arşive kayıt ekle"):
        with st.form("arsiv_ekle", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            proje_adi = c1.text_input("Proje adı")
            takim = c2.text_input("Takım adı")
            yil_in = c3.number_input("Yıl", 2015, 2100, 2025)
            c4, c5, c6 = st.columns(3)
            program = c4.selectbox("Program", ["TEKNOFEST", "2209-A", "2209-B", "Bitirme", "Diğer"])
            kat_sec = c5.selectbox("Kategori", ["—"] + sorted(set(kategoriler.values())))
            derece = c6.text_input("Derece", placeholder="Birincilik / Finalist / Destek Kazandı")
            kurum = st.text_input("Kurum")
            ozet = st.text_area("Proje özeti ve yöntemi")
            tekno = st.text_input("Kullanılan teknolojiler (virgülle)")
            rapor = st.text_input("Rapor / kaynak bağlantısı")
            if st.form_submit_button("Kaydet", type="primary"):
                try:
                    with get_session() as s:
                        kid = next((i for i, n in kategoriler.items() if n == kat_sec), None)
                        s.add(OdulluProje(proje_adi=proje_adi, takim_adi=takim, yil=int(yil_in), program=program,
                                          kategori_id=kid, kategori_adi=kat_sec if kat_sec != "—" else program, derece=derece,
                                          kurum_adi=kurum, proje_ozeti=ozet, kullanilan_teknolojiler=parse_list(tekno),
                                          rapor_url=rapor or None, kaynak="manuel"))
                except IntegrityError:
                    # (kategori, yıl, derece, takım) benzersiz olmalı
                    st.error("Aynı kategori, yıl, derece ve takım adıyla bir kayıt arşivde zaten var.")
                else:
                    ui.flash("Eklendi.")
                    st.rerun()
    if u.rol == "admin":
        with st.expander("📥 Excel ile toplu yükle"):
            st.download_button("Örnek Excel şablonu", importer.ornek_excel("arsiv"), file_name="arsiv_sablonu.xlsx")
            dosya = st.file_uploader("Excel / CSV", type=["xlsx", "csv"], key="arsiv_up")
            if dosya and st.button("Yükle"):
                n, hatalar = importer.arsivi_ice_aktar(dosya)
                st.success(f"{n} kayıt eklendi.")
                for h in hatalar:
                    st.warning(h)
