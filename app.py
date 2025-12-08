import streamlit as st
from evds import evdsAPI
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

# --- KULLANICI AYARLARI ---
USER_API_KEY = "Uol1kIOQos"

# --- Sayfa Ayarları ---
st.set_page_config(page_title="TAV Fiyat Farkı Analizi", layout="wide")

st.title("📈 Satın Alma Fiyat Farkı & Artış Analizi")
st.markdown("""
Bu araç, tanımlı API anahtarı üzerinden **TÜFE**, **Yİ-ÜFE** ve **(TÜFE+ÜFE)/2** artış oranlarını otomatik hesaplar.
""")

# --- Sidebar ---
st.sidebar.header("Dönem Seçimi")

# Varsayılan tarih ayarı (Geçen ay)
today = date.today()
first_day_of_current_month = today.replace(day=1)
default_date = first_day_of_current_month - relativedelta(months=1)

ref_date = st.sidebar.date_input("Analiz Edilecek Dönem (Referans Ay)", default_date)

st.sidebar.markdown("---")
st.sidebar.success("✅ API Bağlantısı Hazır")

# --- Yardımcı Fonksiyonlar ---
def get_inflation_data(api_key, target_date):
    evds = evdsAPI(api_key)
    
    # Tarihleri belirle
    dates_to_fetch = {
        "Seçilen Ay": target_date,
        "1 Ay Önce": target_date - relativedelta(months=1),
        "3 Ay Önce": target_date - relativedelta(months=3),
        "6 Ay Önce": target_date - relativedelta(months=6),
        "1 Yıl Önce": target_date - relativedelta(months=12),
        "Yılbaşı (Önceki Aralık)": date(target_date.year - 1, 12, 1)
    }
    
    # API sorgusu için tarih aralığı
    start_date_query = min(dates_to_fetch.values()).replace(day=1).strftime("%d-%m-%Y")
    end_date_query = target_date.replace(day=1).strftime("%d-%m-%Y")
    
    series = ["TP.FG.J0", "TP.TUFE1YI.T1"] 
    
    try:
        raw_df = evds.get_data(series, startdate=start_date_query, enddate=end_date_query)
    except Exception as e:
        return None, f"Veri çekilirken hata oluştu: {str(e)}"
    
    # Tarih formatlama
    raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
    
    results = []
    
    target_period = pd.Period(target_date, freq='M')
    current_row = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == target_period]
    
    if current_row.empty:
        return None, "Seçilen tarih için TCMB henüz veri açıklamamış olabilir."

    if pd.isna(current_row["TP_FG_J0"].values[0]) or pd.isna(current_row["TP_TUFE1YI_T1"].values[0]):
        return None, "Seçilen ay için veri boş görünüyor."

    tufe_current = float(current_row["TP_FG_J0"].values[0])
    ufe_current = float(current_row["TP_TUFE1YI_T1"].values[0])
    
    for label, d in dates_to_fetch.items():
        if label == "Seçilen Ay": continue
        
        past_period = pd.Period(d, freq='M')
        past_row = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == past_period]
        
        if not past_row.empty:
            val_tufe = past_row["TP_FG_J0"].values[0]
            val_ufe = past_row["TP_TUFE1YI_T1"].values[0]

            if pd.notna(val_tufe) and pd.notna(val_ufe):
                tufe_old = float(val_tufe)
                ufe_old = float(val_ufe)
                
                # Artış Oranları
                tufe_change = ((tufe_current - tufe_old) / tufe_old) * 100
                ufe_change = ((ufe_current - ufe_old) / ufe_old) * 100
                
                # ORTALAMA HESABI (Yeni Eklenen Kısım)
                avg_change = (tufe_change + ufe_change) / 2
                
                results.append({
                    "Dönem": label,
                    "Kıyaslanan Tarih": d.strftime("%B %Y"),
                    "TÜFE Artışı (%)": round(tufe_change, 2),
                    "Yİ-ÜFE Artışı (%)": round(ufe_change, 2),
                    "Ortalama (T+Ü)/2": round(avg_change, 2), # Yeni Sütun
                    "TÜFE Endeks": tufe_old,
                    "ÜFE Endeks": ufe_old
                })
            
    return pd.DataFrame(results), None

# --- Ana Ekran ---

if st.button("Analizi Başlat"):
    with st.spinner('TCMB verileri işleniyor...'):
        df_result, error = get_inflation_data(USER_API_KEY, ref_date)
        
        if error:
            st.error(error)
        else:
            st.success(f"✅ {ref_date.strftime('%B %Y')} Referanslı Analiz Tamamlandı")
            
            st.subheader("📊 Fiyat Farkı Tablosu")
            
            # Tablo Formatlama (Yeni sütunu da ekledik)
            st.dataframe(
                df_result.style.format({
                    "TÜFE Artışı (%)": "{:.2f}%",
                    "Yİ-ÜFE Artışı (%)": "{:.2f}%",
                    "Ortalama (T+Ü)/2": "{:.2f}%", # Format ayarı
                    "TÜFE Endeks": "{:.2f}",
                    "ÜFE Endeks": "{:.2f}"
                }),
                use_container_width=True,
                height=300
            )
            
            st.info("İpucu: 'Ortalama (T+Ü)/2' sütunu, sözleşmelerdeki aritmetik ortalama formülü için hesaplanmıştır.")
            
            csv = df_result.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Raporu İndir (CSV)",
                csv,
                f"enflasyon_fark_analizi_{ref_date}.csv",
                "text/csv"
            )