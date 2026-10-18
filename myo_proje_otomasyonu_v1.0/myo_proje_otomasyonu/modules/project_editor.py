"""Proje içerik (TYBS bölümleri) düzenleyicisi — danışman paneli ve öğrenci takım sayfasında ortak kullanılır."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from . import automation, rules, settings, ui
from .database import Proje, TeknofestKategori, get_session
from .text_utils import parse_list, word_count


def _sayac(metin: str, minimum: int = 0, kelime: tuple[int, int] | None = None) -> None:
    if kelime:
        n = word_count(metin)
        ok = kelime[0] <= n <= kelime[1]
        st.caption(f"{'✅' if ok else '⚠️'} {n} kelime (TYBS: {kelime[0]}–{kelime[1]})")
    elif minimum:
        n = len((metin or "").strip())
        st.caption(f"{'✅' if n >= minimum else '⚠️'} {n} karakter (TYBS: en az {minimum})")


def icerik_duzenleyici(proje: Proje, kullanici_id: int, duzenleyebilir: bool = True) -> None:
    p = proje
    k = f"ed{p.id}_"
    tub = p.tur in rules.TUBITAK_TURLERI
    if not duzenleyebilir:
        st.info("Bu projenin içeriğini görüntüleme yetkiniz var; düzenleme danışman ve ekip içindir.")

    st.markdown("##### Temel bilgiler")
    baslik = st.text_input("Başlık", p.baslik, key=k + "baslik", disabled=not duzenleyebilir)
    ozet = st.text_area("Özet", p.ozet, height=160, key=k + "ozet", disabled=not duzenleyebilir,
                        help="TYBS: 25–450 kelime; bilimsel nitelik, yöntem, proje yönetimi ve yaygın etkiyi kapsamalı.")
    _sayac(ozet, kelime=(25, 450) if tub else None)
    c1, c2, c3 = st.columns([3, 1, 1])
    anahtar = c1.text_input("Anahtar kelimeler", p.anahtar_kelimeler, key=k + "anahtar", disabled=not duzenleyebilir)
    sure = c2.number_input("Süre (ay)", 1, 24, int(p.sure_ay or 12), key=k + "sure", disabled=not duzenleyebilir)
    etik = c3.checkbox("Etik kurul gerekli", p.etik_kurul_gerekli, key=k + "etik", disabled=not duzenleyebilir)
    katalog = list(dict.fromkeys((settings.get("yetkinlik_katalogu") or []) + list(p.aranan_yetkinlikler or [])))
    aranan = st.multiselect("Aranan yetkinlikler", katalog, default=p.aranan_yetkinlikler or [], accept_new_options=True, placeholder="Seçin veya yazıp Enter ile ekleyin",
                            key=k + "aranan", disabled=not duzenleyebilir)

    st.markdown("##### TYBS bölümleri" if tub else "##### Proje içeriği")
    alanlar: dict[str, str] = {}
    if p.tur == "2209-A":
        tanim = [("konu_onemi", "1.1 Konunun Önemi ve Bilimsel Niteliği", 350), ("amac_hedefler", "1.2 Amaç ve Hedefler", 350)]
    elif p.tur == "2209-B":
        tanim = [("amac_hedefler", "1.1 Amaç ve Hedefler", 350), ("yenilikci_yon", "1.2 Yenilikçi Yönü ve Teknolojik Değeri", 350)]
    else:
        tanim = [("konu_onemi", "Problem / Konunun önemi", 0), ("amac_hedefler", "Amaç ve hedefler", 0),
                 ("yenilikci_yon", "Yenilikçi (özgün) yönü", 0)]
    tanim += [("yontem", "2. Yöntem" if tub else "Yöntem", 350 if tub else 0),
              ("arastirma_olanaklari", "3.3 Araştırma Olanakları" if tub else "Kullanılacak olanaklar", 0),
              ("yaygin_etki", ("4. Sanayi Odaklı Çıktıları ve Yaygın Etki" if p.tur == "2209-B" else "4. Yaygın Etki") if tub else "Beklenen çıktılar", 0),
              ("diger_konular", "5. Belirtmek İstediğiniz Diğer Konular" if tub else "Diğer", 0),
              ("kaynaklar", "Kaynaklar (her satıra bir kaynak; DOI'si olanlarda DOI zorunlu)", 0)]
    for alan, etiket, minimum in tanim:
        alanlar[alan] = st.text_area(etiket, getattr(p, alan) or "", height=130 if minimum else 100, key=k + alan,
                                     disabled=not duzenleyebilir)
        _sayac(alanlar[alan], minimum)

    st.markdown("##### 3.1 Çalışma takvimi" if tub else "##### İş-zaman planı")
    if tub:
        st.caption("Başarı ölçütü katkılarının toplamı %100 olmalı. Literatür taraması, rapor yazımı, yaygınlaştırma ve malzeme alımı "
                   "ayrı iş adımı yazılmaz.")
    plan = p.is_plani or rules.varsayilan_is_plani(p.sure_ay)
    plan_df = pd.DataFrame(plan, columns=["is_paketi", "sorumlu", "baslangic_ay", "bitis_ay", "basari_olcutu", "katki_yuzde"])
    plan_ed = st.data_editor(plan_df, num_rows="dynamic", key=k + "plan", disabled=not duzenleyebilir, width="stretch",
                             column_config={
                                 "is_paketi": st.column_config.TextColumn("İş adımı", width="large"),
                                 "sorumlu": st.column_config.TextColumn("Sorumlu"),
                                 "baslangic_ay": st.column_config.NumberColumn("Başl. ay", min_value=1, max_value=24, step=1),
                                 "bitis_ay": st.column_config.NumberColumn("Bitiş ay", min_value=1, max_value=24, step=1),
                                 "basari_olcutu": st.column_config.TextColumn("Başarı ölçütü (ölçülebilir)", width="large"),
                                 "katki_yuzde": st.column_config.NumberColumn("Katkı %", min_value=0, max_value=100, step=1),
                             })
    toplam = float(pd.to_numeric(plan_ed["katki_yuzde"], errors="coerce").fillna(0).sum()) if len(plan_ed) else 0
    st.caption(f"{'✅' if abs(toplam - 100) < 0.01 else '⚠️'} Katkı toplamı: %{toplam:g}")

    st.markdown("##### 3.2 Risk yönetimi")
    risk_df = pd.DataFrame(p.risk_plani or rules.varsayilan_risk_plani(), columns=["is_paketi_no", "risk", "b_plani"])
    risk_ed = st.data_editor(risk_df, num_rows="dynamic", key=k + "risk", disabled=not duzenleyebilir, width="stretch",
                             column_config={"is_paketi_no": st.column_config.NumberColumn("İş adımı no", step=1),
                                            "risk": st.column_config.TextColumn("Risk", width="large"),
                                            "b_plani": st.column_config.TextColumn("B planı", width="large")})

    st.markdown("##### Bütçe")
    limit = settings.get_int("butce_limit_2209b" if p.tur == "2209-B" else "butce_limit_2209a")
    butce_df = pd.DataFrame(p.butce or [], columns=["kalem", "tur", "adet", "birim_fiyat", "gerekce"])
    butce_ed = st.data_editor(butce_df, num_rows="dynamic", key=k + "butce", disabled=not duzenleyebilir, width="stretch",
                              column_config={
                                  "kalem": st.column_config.TextColumn("Kalem", width="medium"),
                                  "tur": st.column_config.SelectboxColumn("Tür", options=["Sarf Malzeme", "Makine-Teçhizat", "Hizmet Alımı", "Yazılım", "Ulaşım", "Diğer"]),
                                  "adet": st.column_config.NumberColumn("Adet", min_value=0, step=1),
                                  "birim_fiyat": st.column_config.NumberColumn("Birim fiyat (TL)", min_value=0, format="%.2f"),
                                  "gerekce": st.column_config.TextColumn("Gerekçe", width="large"),
                              })
    adet = pd.to_numeric(butce_ed.get("adet"), errors="coerce").fillna(0) if len(butce_ed) else pd.Series(dtype=float)
    birim = pd.to_numeric(butce_ed.get("birim_fiyat"), errors="coerce").fillna(0) if len(butce_ed) else pd.Series(dtype=float)
    butce_toplam = float((adet * birim).sum()) if len(butce_ed) else 0.0
    if tub:
        st.caption(f"{'✅' if butce_toplam <= limit else '❌'} Toplam {butce_toplam:,.2f} TL / üst limit {limit:,} TL")
    else:
        st.caption(f"Toplam {butce_toplam:,.2f} TL")

    st.markdown("##### TEKNOFEST çapraz başvuru")
    with get_session() as s:
        kats = list(s.scalars(select(TeknofestKategori).where(TeknofestKategori.aktif.is_(True), TeknofestKategori.onlisans_uygun.is_not(False))
                              .order_by(TeknofestKategori.kategori_adi)))
    onerilen = {e["kategori_id"]: e["skor"] for e in (p.teknofest_eslesmeler or [])}
    secenekler = [None] + sorted(kats, key=lambda x: -onerilen.get(x.id, 0))
    idx = next((i for i, x in enumerate(secenekler) if x and x.id == p.eslesen_teknofest_kat_id), 0)
    kat = st.selectbox("Hedef TEKNOFEST yarışması", secenekler, index=idx, key=k + "kat", disabled=not duzenleyebilir,
                       format_func=lambda x: "— Yok —" if x is None else (f"⭐ {x.kategori_adi} (%{onerilen[x.id]:g})" if x.id in onerilen else x.kategori_adi))

    if duzenleyebilir:
        c1, c2 = st.columns([1, 1])
        if c1.button("💾 Kaydet", type="primary", key=k + "kaydet", width="stretch"):
            plan_list = []
            for r in plan_ed.fillna("").to_dict("records"):
                if not str(r.get("is_paketi", "")).strip():
                    continue
                plan_list.append({"is_paketi": str(r["is_paketi"]), "sorumlu": str(r.get("sorumlu", "")),
                                  "baslangic_ay": int(float(r.get("baslangic_ay") or 1)), "bitis_ay": int(float(r.get("bitis_ay") or 1)),
                                  "basari_olcutu": str(r.get("basari_olcutu", "")), "katki_yuzde": float(r.get("katki_yuzde") or 0)})
            risk_list = [{"is_paketi_no": int(float(r.get("is_paketi_no") or 0)), "risk": str(r.get("risk", "")), "b_plani": str(r.get("b_plani", ""))}
                         for r in risk_ed.fillna("").to_dict("records") if str(r.get("risk", "")).strip()]
            butce_list = []
            for r in butce_ed.fillna("").to_dict("records"):
                if not str(r.get("kalem", "")).strip():
                    continue
                a = float(r.get("adet") or 0)
                bf = float(r.get("birim_fiyat") or 0)
                butce_list.append({"kalem": str(r["kalem"]), "tur": str(r.get("tur", "")), "adet": int(a) if a == int(a) else a,
                                   "birim_fiyat": bf, "tutar": a * bf, "gerekce": str(r.get("gerekce", ""))})
            yeni = {"baslik": baslik.strip() or p.baslik, "ozet": ozet, "anahtar_kelimeler": anahtar, "sure_ay": int(sure),
                    "etik_kurul_gerekli": etik, "aranan_yetkinlikler": parse_list(aranan), "is_plani": plan_list,
                    "risk_plani": risk_list, "butce": butce_list, "eslesen_teknofest_kat_id": kat.id if kat else None, **alanlar}
            yenile = (ozet != p.ozet) or (baslik != p.baslik) or (anahtar != p.anahtar_kelimeler)
            automation.proje_guncelle(p.id, yeni, kullanici_id, eslesme_yenile=yenile)
            for ek in ("plan", "risk", "butce"):
                st.session_state.pop(k + ek, None)
            st.toast("Kaydedildi." + (" TEKNOFEST eşleşmeleri güncellendi." if yenile else ""), icon="✅")
            st.rerun()
        if c2.button("🔄 TEKNOFEST eşleşmesini yenile", key=k + "yenile", width="stretch"):
            automation.proje_guncelle(p.id, {}, kullanici_id, eslesme_yenile=True)
            st.rerun()
        if p.teknofest_eslesmeler:
            st.caption("Öneriler: " + " · ".join(f"{e['kategori_adi']} (%{e['skor']:g})" for e in p.teknofest_eslesmeler))
