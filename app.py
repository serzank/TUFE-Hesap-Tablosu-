import streamlit as st
from evds import evdsAPI
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.express as px

# --- KULLANICI AYARLARI ---
USER_API_KEY = "Uol1kIOQos"

# --- Sayfa Ayarları ---
st.set_page_config(page_title="TAV Özel Tarihli Fiyat Farkı", layout="wide")

st.title("🧮 İki Tarih Arası Fiyat Farkı Hesaplama")
st.markdown("""
Bu araç, seçilen **Başlangıç** ve **Bitiş** ayları arasındaki TÜFE, Yİ-ÜFE ve Ortalama artış oranını hesaplar.
Özellikle sözleşme başı ile güncel hakediş dönemi arasındaki net farkı bulmak için tasarlanmıştır.
""")

# --- Sidebar ---
st.sidebar.header("Tarih Aralığı Seçimi")

# Varsayılanlar
today = date.today()
default_end = today.replace(day=1) - relativedelta(months=1) # Geçen ay
default_start = default_end - relativedelta(months=12) # 1 yıl öncesi

start_date = st.sidebar.date_input("Başlangıç Tarihi (Baz Ay)", default_start)
end_date = st.sidebar.date_input("Bitiş Tarihi (Güncel Ay)", default_end)

st.sidebar.info("Not: Gün gün değil, seçilen tarihlerin ait olduğu **AY** baz alınır.")
st.sidebar.markdown("---")
st.sidebar.success("✅ API Bağlantısı Hazır")

# --- Yardımcı Fonksiyonlar ---
def get_custom_range_data(api_key, start, end):
    evds = evdsAPI(api_key)
    
    # Tarih Kontrolü
    if start >= end:
        return None, "Başlangıç tarihi, bitiş tarihinden önce olmalıdır.", None
    
    # API sorgusu için format (GG-AA-YYYY)
    start_str = start.replace(day=1).strftime("%d-%m-%Y")
    end_str = end.replace(day=1).strftime("%d-%m-%Y")
    
    series = ["TP.FG.J0", "TP.TUFE1YI.T1"]
    
    try:
        raw_df = evds.get_data(series, startdate=start_str, enddate=end_str)
    except Exception as e:
        return None, f"Veri çekilemedi: {str(e)}", None
    
    # Veri işleme
    if raw_df is None or raw_df.empty:
        return None, "TCMB'den veri dönmedi.", None

    raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
    raw_df.rename(columns={
        "TP_FG_J0": "TÜFE",
        "TP_TUFE1YI_T1": "Yİ-ÜFE",
        "Tarih": "Dönem"
    }, inplace=True)
    
    # Sadece sayısal sütunları float'a çevir (NaN hatalarını önlemek için)
    raw_df["TÜFE"] = pd.to_numeric(raw_df["TÜFE"], errors='coerce')
    raw_df["Yİ-ÜFE"] = pd.to_numeric(raw_df["Yİ-ÜFE"], errors='coerce')
    
    # Başlangıç ve Bitiş değerlerini bulma
    start_period = pd.Period(start, freq='M')
    end_period = pd.Period(end, freq='M')
    
    start_row = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == start_period]
    end_row = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == end_period]
    
    if start_row.empty or end_row.empty:
        return None, None, "Seçilen tarihlerden biri için TCMB verisi bulunamadı."
        
    if start_row.isnull().values.any() or end_row.isnull().values.any():
        return None, "Seçilen dönemde veri eksik.", None

    # Değerleri al
    s_tufe = float(start_row["TÜFE"].values[0])
    s_ufe = float(start_row["Yİ-ÜFE"].values[0])
    
    e_tufe = float(end_row["TÜFE"].values[0])
    e_ufe = float(end_row["Yİ-ÜFE"].values[0])
    
    # Hesaplamalar
    tufe_degisim = ((e_tufe - s_tufe) / s_tufe) * 100
    ufe_degisim = ((e_ufe - s_ufe) / s_ufe) * 100
    avg_degisim = (tufe_degisim + ufe_degisim) / 2
    
    summary = {
        "Başlangıç Dönemi": start.strftime("%B %Y"),
        "Bitiş Dönemi": end.strftime("%B %Y"),
        "TÜFE Artış (%)": tufe_degisim,
        "Yİ-ÜFE Artış (%)": ufe_degisim,
        "Ortalama (T+Ü)/2 (%)": avg_degisim,
        "Başlangıç TÜFE": s_tufe,
        "Bitiş TÜFE": e_tufe,
        "Başlangıç ÜFE": s_ufe,
        "Bitiş ÜFE": e_ufe
    }
    
    return summary, raw_df, None

# --- Ana Ekran ---

if st.button("Hesapla"):
    with st.spinner('TCMB EVDS verileri çekiliyor...'):
        # Verileri fonksiyondan alıyoruz
        summary, trend_df, error = get_custom_range_data(USER_API_KEY, start_date, end_date)
        
        # 1. KONTROL: Fonksiyon hata döndürdü mü?
        if error:
            st.error(f"Veri çekme hatası: {error}")
            st.info("İpucu: Seçilen aylara ait veriler TCMB tarafından henüz açıklanmamış olabilir veya API anahtarınız hatalıdır.")
        
        # 2. KONTROL: Summary gerçekten bir sözlük mü?
        elif summary is not None and isinstance(summary, dict):
            # Analiz Dönemi Bilgisi
            st.success(f"Analiz Dönemi: {summary.get('Başlangıç Dönemi')} ➡️ {summary.get('Bitiş Dönemi')}")
            
            # --- SONUÇ KARTLARI ---
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("TÜFE Artışı", f"%{summary['TÜFE Artış (%)']:.2f}")
            with c2:
                st.metric("Yİ-ÜFE Artışı", f"%{summary['Yİ-ÜFE Artış (%)']:.2f}")
            with c3:
                st.metric("Ortalama (T+Ü)/2", f"%{summary['Ortalama (T+Ü)/2 (%)']:.2f}")

            st.divider()

            # --- DETAY TABLOSU ---
            st.subheader("📋 Detaylı Hesap Tablosu")
            
            # Burada summary artik garanti altinda oldugu icin hata almayacaksiniz
            detail_data = {
                "Endeks Tipi": ["TÜFE (Tüketici)", "Yİ-ÜFE (Üretici)", "Ortalama"],
                "Başlangıç Endeksi": [summary["Başlangıç TÜFE"], summary["Başlangıç ÜFE"], None],
                "Bitiş Endeksi": [summary["Bitiş TÜFE"], summary["Bitiş ÜFE"], None],
                "Değişim Oranı (%)": [summary["TÜFE Artış (%)"], summary["Yİ-ÜFE Artış (%)"], summary["Ortalama (T+Ü)/2 (%)"]]
            }
            df_display = pd.DataFrame(detail_data)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # --- GRAFİK ---
            if trend_df is not None:
                st.subheader("📈 Dönem İçindeki Seyir")
                fig = px.line(trend_df, x="Dönem", y=["TÜFE", "Yİ-ÜFE"], markers=True)
                st.plotly_chart(fig, use_container_width=True)
        
        # 3. KONTROL: Beklenmedik bir boş dönme durumu
        else:
            st.warning("Seçilen kriterlere uygun veri bulunamadı.")
