import streamlit as st
from evds import evdsAPI
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.express as px
import requests
import warnings
import ssl

# --- SSL YAMASI (GÜVENLİK DUVARI İÇİN) ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
warnings.filterwarnings('ignore')

# --- KULLANICI AYARLARI ---
USER_API_KEY = "Uol1kIOQos" # Anahtarınız bu

# --- SEKTÖR LİSTESİ ---
SECTOR_CODES = {
    "📌 Yİ-ÜFE (Genel - Sanayi)": "TP.TUFE1YI.T1", 
    "📌 H-ÜFE (Genel - Hizmet)": "TP.HUFE17.GENEL",
    "— HİZMET KALEMLERİ —": "—",
    "🛡️ Güvenlik Hizmetleri (N80)": "TP.HUFE17.80",
    "🧹 Temizlik Hizmetleri (N812)": "TP.HUFE17.812",
    "🍽️ Yemek / Catering (I56)": "TP.HUFE17.56",
    "✈️ Yer Hizmetleri & Havayolu (H51)": "TP.HUFE17.51",
    "📦 Depolama ve Lojistik (H52)": "TP.HUFE17.52",
    "💻 IT ve Bilgi Sistemleri (J62)": "TP.HUFE17.62",
    "— MALZEME & İNŞAAT —": "—",
    "🏗️ İnşaat Maliyet Endeksi": "TP.IMS.GENEL",
    "⚡ Elektrik, Gaz Üretim": "TP.YI-UFE.D",
}

st.set_page_config(page_title="TAV Debug Modu", layout="wide")
st.title("🛠️ Hata Tespit Modu (Debug)")

# Sidebar
st.sidebar.header("Ayarlar")
today = date.today()
start_date = st.sidebar.date_input("Başlangıç", today.replace(day=1) - relativedelta(months=13))
end_date = st.sidebar.date_input("Bitiş", today.replace(day=1) - relativedelta(months=1))

valid_options = [k for k in SECTOR_CODES.keys() if k != "—"]
selected_name = st.sidebar.selectbox("Endeks", valid_options)
selected_code = SECTOR_CODES[selected_name]

# --- VERİ ÇEKME FONKSİYONU (AJAN MODU) ---
def debug_run(api_key, start, end, code, name):
    log_area = st.empty() # Ekrana canlı yazı yazacak alan
    
    with st.status("İşlem Adımları İzleniyor...", expanded=True) as status:
        
        # ADIM 1: Bağlantı Kurma
        st.write("1. API Bağlantısı kuruluyor...")
        evds = evdsAPI(api_key)
        if hasattr(evds, 'session'): evds.session.verify = False
        st.write("✅ Kütüphane hazır.")

        # ADIM 2: Tarih Formatlama
        s_str = start.replace(day=1).strftime("%d-%m-%Y")
        e_str = end.replace(day=1).strftime("%d-%m-%Y")
        st.write(f"2. Sorgulanan Tarihler: {s_str} ile {e_str} arası")

        # ADIM 3: Veri İsteme
        series = ["TP.FG.J0", code]
        st.write(f"3. TCMB'den şu kodlar isteniyor: {series}")
        
        try:
            raw_df = evds.get_data(series, startdate=s_str, enddate=e_str)
        except Exception as e:
            st.error(f"❌ HATA OLUŞTU: {e}")
            return None
            
        # ADIM 4: Veri Kontrolü
        if raw_df is None:
            st.error("❌ TCMB 'None' (Boş) döndürdü. API Anahtarı hatalı olabilir.")
            return None
        elif raw_df.empty:
            st.error("❌ TCMB boş tablo döndürdü. Seçilen tarihte veri yok.")
            return None
        
        st.write("✅ Ham Veri Alındı! İlk 5 satır aşağıda:")
        st.dataframe(raw_df.head()) # Veriyi ekrana bas

        # ADIM 5: Sütun Eşleştirme
        st.write("4. Sütunlar eşleştiriliyor...")
        raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
        
        col_map = {}
        tufe_clean = "TPFGJ0"
        ufe_clean = code.replace(".", "").replace("_", "")
        
        for col in raw_df.columns:
            clean = col.replace(".", "").replace("_", "")
            if tufe_clean in clean: col_map[col] = "TÜFE"
            elif ufe_clean in clean: col_map[col] = "UFE"
            
        raw_df.rename(columns=col_map, inplace=True)
        st.write(f"🏷️ Eşleşen Sütunlar: {list(col_map.values())}")
        
        if "TÜFE" not in raw_df.columns or "UFE" not in raw_df.columns:
            st.warning("⚠️ DİKKAT: İstenen sütunlardan biri bulunamadı! TCMB verisi eksik girmiş.")
            st.write("Mevcut Sütunlar:", raw_df.columns.tolist())
            return None

        # ADIM 6: Hesaplama
        raw_df["TÜFE"] = pd.to_numeric(raw_df["TÜFE"], errors='coerce')
        raw_df["UFE"] = pd.to_numeric(raw_df["UFE"], errors='coerce')
        
        row_s = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == pd.Period(start, 'M')]
        row_e = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == pd.Period(end, 'M')]
        
        if row_s.empty or row_e.empty:
            st.error(f"❌ Seçilen Başlangıç ({start.strftime('%m-%Y')}) veya Bitiş ({end.strftime('%m-%Y')}) ayında veri satırı yok.")
            return None
            
        val_s_t, val_e_t = row_s["TÜFE"].values[0], row_e["TÜFE"].values[0]
        val_s_u, val_e_u = row_s["UFE"].values[0], row_e["UFE"].values[0]
        
        st.write(f"🔢 Değerler: TÜFE ({val_s_t} -> {val_e_t}), ÜFE ({val_s_u} -> {val_e_u})")
        
        if pd.isna(val_s_u) or pd.isna(val_e_u):
            st.error("❌ ÜFE Verisi bu tarihlerde 'NaN' (Boş). Muhtemelen henüz açıklanmadı.")
            return None
            
        t_deg = ((val_e_t - val_s_t)/val_s_t)*100
        u_deg = ((val_e_u - val_s_u)/val_s_u)*100
        ort = (t_deg + u_deg)/2
        
        status.update(label="✅ HESAPLAMA BAŞARILI!", state="complete", expanded=False)
        
        return {"t": t_deg, "u": u_deg, "avg": ort}

# --- BUTON ---
if st.button("SORUNU BUL VE HESAPLA"):
    res = debug_run(USER_API_KEY, start_date, end_date, selected_code, selected_name)
    
    if res:
        st.success("🎉 İŞLEM TAMAM!")
        c1, c2, c3 = st.columns(3)
        c1.metric("TÜFE", f"%{res['t']:.2f}")
        c2.metric("ÜFE", f"%{res['u']:.2f}")
        c3.metric("ORTALAMA", f"%{res['avg']:.2f}")
