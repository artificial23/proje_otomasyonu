import streamlit as st
from sqlalchemy import select

from modules import automation, matcher, rules, settings, ui
from modules.database import Basvuru, Kullanici, Proje, TeknofestKategori, get_session
from modules.text_utils import fold, skill_set

u = ui.require_user()
st.title("📋 Proje Eşleştirme Panosu")
st.caption("TÜBİTAK 2209-A / 2209-B, Bitirme ve TEKNOFEST proje ilanları · yetkinlik bazlı başvuru")

ilan_verebilir = u.rol in ("hoca", "sanayi", "admin")
sekmeler = ["🔎 İlanlar"] + (["➕ Yeni İlan"] if ilan_verebilir else [])
tabs = st.tabs(sekmeler)


@st.dialog("Projeye başvur", width="medium")
def basvuru_dialog(proje_id: int):
    with get_session() as s:
        p = s.get(Proje, proje_id)
    analiz = matcher.yetkinlik_analizi(p.aranan_yetkinlikler, u.yetkinlikler, matcher.ekip_yetkinlikleri(p.id))
    st.markdown(f"**{ui.esc(p.baslik)}**")
    st.write(f"Yetkinlik uyumunuz: **%{analiz.uyum_yuzde:g}**")
    if analiz.ogrencinin_katkisi:
        st.markdown("Ekibe katacağınız yetkinlikler: " + ui.chips(analiz.ogrencinin_katkisi, ok=set(skill_set(analiz.ogrencinin_katkisi))),
                    unsafe_allow_html=True)
    for k in rules.ogrenci_uygunlugu(u, p):
        (st.error if k.seviye == "hata" else st.warning)(f"{k.alan}: {k.mesaj}")
    motivasyon = st.text_area("Neden bu projede yer almak istiyorsunuz? (kısa)", max_chars=1000)
    if st.button("Başvuruyu gönder", type="primary"):
        res = automation.basvuru_yap(u, proje_id, motivasyon)
        if res.ok:
            ui.flash(res.mesaj)
            st.rerun()
        else:
            st.error(res.mesaj)


# ---------------------------------------------------------------------------
# İlanlar
# ---------------------------------------------------------------------------
with tabs[0]:
    katalog = settings.get("yetkinlik_katalogu") or []
    f1, f2, f3, f4 = st.columns([2, 2, 2, 1.3])
    tur_sec = f1.multiselect("Tür", rules.TURLER, placeholder="Tümü")
    yet_sec = f2.multiselect("Yetkinlik", katalog, placeholder="Tümü")
    arama = f3.text_input("Ara", placeholder="başlık, özet, anahtar kelime")
    sadece_acik = f4.toggle("Yalnız açık", value=True)

    with get_session() as s:
        q = select(Proje).where(Proje.durum != "Iptal").order_by(Proje.olusturma.desc())
        projeler = list(s.scalars(q))
        kullanicilar = {k.id: k for k in s.scalars(select(Kullanici).where(Kullanici.rol.in_(["hoca", "sanayi", "admin"])))}
        benim_basvurular = {b.proje_id: b for b in s.scalars(select(Basvuru).where(Basvuru.ogrenci_id == u.id))}
        kategoriler = {k.id: k for k in s.scalars(select(TeknofestKategori))}

    if sadece_acik:
        projeler = [p for p in projeler if p.durum == "Acik"]
    else:
        projeler = [p for p in projeler if p.durum != "Taslak" or p.olusturan_id == u.id]
    if tur_sec:
        projeler = [p for p in projeler if p.tur in tur_sec]
    if yet_sec:
        isteneler = set(skill_set(yet_sec))
        projeler = [p for p in projeler if isteneler & set(skill_set(p.aranan_yetkinlikler))]
    if arama:
        a = fold(arama)
        projeler = [p for p in projeler if a in fold(f"{p.baslik} {p.ozet} {p.anahtar_kelimeler}")]

    skorlar = matcher.ogrenciye_uygun_projeler(u, projeler) if u.rol == "ogrenci" else {}
    if u.rol == "ogrenci":
        projeler.sort(key=lambda p: skorlar.get(p.id, 0), reverse=True)
        st.caption("İlanlar yetkinliklerinize göre sıralandı. ✅ yeşil etiketler sizde olan yetkinliklerdir.")

    st.write(f"**{len(projeler)}** ilan")
    benim = set(skill_set(u.yetkinlikler))
    for p in projeler:
        uyeler = rules.ekip_uyeleri(p.id)
        dan = kullanicilar.get(p.danisman_id)
        san = kullanicilar.get(p.sanayi_danisman_id) if p.sanayi_danisman_id else None
        with st.container(border=True):
            ust, sag = st.columns([4.2, 1.3])
            with ust:
                st.markdown(f"{ui.tur_rozet(p.tur)} {ui.durum_rozet(p.durum)} :gray-badge[{p.kod or ''}] :gray-badge[{p.donem}]")
                st.markdown(f"<div class='kart-baslik'>{ui.esc(p.baslik)}</div>", unsafe_allow_html=True)
                bilgi = f"Danışman: {ui.esc(dan.ad_soyad) if dan else '—'}"
                if san or p.sanayi_kurulus:
                    bilgi += f" · Sanayi: {ui.esc(p.sanayi_kurulus or (san.kurum if san else ''))}"
                bilgi += f" · Ekip: {len(uyeler)}/{p.max_ekip}"
                st.markdown(f"<span class='soluk'>{bilgi}</span>", unsafe_allow_html=True)
                aranan = set(skill_set(p.aranan_yetkinlikler))
                st.markdown(ui.chips(p.aranan_yetkinlikler, ok=benim if u.rol == "ogrenci" else None), unsafe_allow_html=True)
                if p.teknofest_eslesmeler:
                    st.markdown("🚀 TEKNOFEST çapraz başvuru önerisi: " + " · ".join(
                        f"{ui.esc(e['kategori_adi'])} (%{e['skor']:g})" for e in p.teknofest_eslesmeler))
                if p.ozet:
                    with st.expander("Özet"):
                        st.write(p.ozet)
            with sag:
                if u.rol == "ogrenci":
                    st.metric("Uyumunuz", f"%{skorlar.get(p.id, 0):g}")
                    b = benim_basvurular.get(p.id)
                    if b and b.durum in ("Beklemede", "Kabul", "Ret"):
                        st.markdown({"Beklemede": ":orange-badge[Başvuru bekliyor]", "Kabul": ":green-badge[Ekiptesiniz]",
                                     "Ret": ":gray-badge[Olumsuz]"}[b.durum])
                    elif p.durum == "Acik":
                        if st.button("Başvur", key=f"basvur_{p.id}", type="primary", width="stretch"):
                            basvuru_dialog(p.id)
                elif p.danisman_id == u.id or p.olusturan_id == u.id or u.rol == "admin":
                    st.page_link("sayfalar/4_Danisman_Onay_ve_Otomasyon.py", label="Yönet", icon=":material/tune:")

# ---------------------------------------------------------------------------
# Yeni ilan
# ---------------------------------------------------------------------------
if ilan_verebilir:
    with tabs[1]:
        with get_session() as s:
            hocalar = list(s.scalars(select(Kullanici).where(Kullanici.rol.in_(["hoca", "admin"]), Kullanici.aktif.is_(True)).order_by(Kullanici.ad_soyad)))
            sanayiciler = list(s.scalars(select(Kullanici).where(Kullanici.rol == "sanayi", Kullanici.aktif.is_(True)).order_by(Kullanici.ad_soyad)))
        donem = str(settings.get("aktif_donem"))
        tur = st.segmented_control("Proje türü", rules.TURLER, default="2209-B" if u.rol == "sanayi" else "2209-A")
        tur = tur or "2209-A"
        if tur in rules.TUBITAK_TURLERI:
            st.caption(f"TÜBİTAK {tur}: en çok 12 ay, yürütücü dahil en fazla {settings.get_int('max_ekip_2209')} kişi, "
                       f"bütçe üst limiti {settings.get_int('butce_limit_2209a' if tur == '2209-A' else 'butce_limit_2209b'):,} TL. "
                       "Danışman kotası dolu ise ilan 'Yedek Havuz'a alınır.")
        with st.form("yeni_ilan", clear_on_submit=False):
            baslik = st.text_input("Proje başlığı *", max_chars=300)
            ozet = st.text_area("Özet / Proje fikri *", height=150,
                                help="TÜBİTAK için özet 25–450 kelime olmalıdır. Bu metin TEKNOFEST eşleştirmesinde de kullanılır.")
            anahtar = st.text_input("Anahtar kelimeler (virgülle)", placeholder="PLC, görüntü işleme, otomasyon")
            aranan = st.multiselect("Aranan yetkinlikler *", settings.get("yetkinlik_katalogu") or [], accept_new_options=True, placeholder="Seçin veya yazıp Enter ile ekleyin")
            c1, c2, c3 = st.columns(3)
            if u.rol == "hoca":
                dan_idx = next((i for i, h in enumerate(hocalar) if h.id == u.id), 0)
            else:
                dan_idx = 0
            danisman = c1.selectbox("Akademik danışman *", hocalar, index=dan_idx if hocalar else None,
                                    format_func=lambda h: f"{h.unvan + ' ' if h.unvan and not h.ad_soyad.startswith(h.unvan) else ''}{h.ad_soyad}")
            if danisman:
                uygun, sayi, limit = rules.kota_uygun_mu(danisman.id, tur, donem)
                c1.caption(f"Kota: {sayi}/{limit} {'✅' if uygun else '⚠️ dolu → yedek havuz'}")
            sure = c2.number_input("Süre (ay)", 1, 24, 12 if tur in rules.TUBITAK_TURLERI else 8)
            ekip_siniri = max(1, rules.ekip_limiti(tur))
            max_ekip = c3.number_input("Maks. ekip (öğrenci)", 1, ekip_siniri, ekip_siniri)
            sanayi_id, sanayi_kurulus = None, None
            if tur == "2209-B" or tur == "Bitirme":
                c4, c5 = st.columns(2)
                if u.rol == "sanayi":
                    sanayi_id, sanayi_kurulus = u.id, u.kurum
                    c4.text_input("Sanayi kuruluşu", value=u.kurum or "", disabled=True)
                else:
                    secenek = [None] + sanayiciler
                    sec = c4.selectbox("Sanayi danışmanı (kayıtlıysa)", secenek,
                                       format_func=lambda x: "— Seçilmedi —" if x is None else f"{x.ad_soyad} ({x.kurum or ''})")
                    sanayi_id = sec.id if sec else None
                    sanayi_kurulus = c5.text_input("Sanayi kuruluşu", value=(sec.kurum if sec else "") or "")
            etik = st.checkbox("Etik kurul onayı gerekebilir (insan/hayvan deneği, anket vb.)")
            taslak = st.checkbox("Taslak olarak kaydet (yayınlama)")
            onizle = st.form_submit_button("🔍 Benzerlik ve TEKNOFEST eşleşmesini önizle")
            kaydet = st.form_submit_button("📢 İlanı yayınla", type="primary")

        if onizle or kaydet:
            if not baslik.strip() or not ozet.strip() or not aranan:
                st.error("Başlık, özet ve en az bir aranan yetkinlik zorunludur.")
                st.stop()
            benzer = matcher.benzer_projeler(baslik, ozet)
            if benzer:
                st.warning("Benzer ilanlar bulundu (fikir tekrarı olabilir):\n\n" + "\n".join(
                    f"- **{b['baslik']}** ({b['tur']}, {b['donem']}) — benzerlik %{b['skor']:g}" for b in benzer))
            es = matcher.teknofest_eslestir(baslik, ozet, anahtar, aranan)
            if es:
                st.info("🚀 Önerilen TEKNOFEST kategorileri: " + " · ".join(f"**{e['kategori_adi']}** (%{e['skor']:g})" for e in es))
            else:
                st.caption("Eşik üzerinde TEKNOFEST eşleşmesi bulunamadı.")
        if kaydet:
            if not danisman:
                st.error("Danışman seçin.")
                st.stop()
            res = automation.proje_olustur({
                "baslik": baslik, "ozet": ozet, "anahtar_kelimeler": anahtar, "aranan_yetkinlikler": aranan, "tur": tur,
                "danisman_id": danisman.id, "sure_ay": sure, "max_ekip": max_ekip, "sanayi_danisman_id": sanayi_id,
                "sanayi_kurulus": sanayi_kurulus, "etik_kurul_gerekli": etik, "taslak": taslak,
            }, u)
            (st.success if res.ok else st.error)(res.mesaj)
            if res.ok:
                st.balloons()
                st.caption(f"Proje kodu: {res.veri.kod}. İçerik bölümlerini (TYBS) Danışman Paneli'nden doldurabilirsiniz.")
