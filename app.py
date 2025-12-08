# --- 1. ADIM: BU BLOK EN ÜSTTE OLMALI (SSL YAMASI) ---
import ssl

# Python'un standart SSL oluşturucusunu, bizim "güvensiz" versiyonumuzla değiştiriyoruz.
# Bu fonksiyon sıralamayı doğru yaparak o hatayı engeller.
def create_forcefully_insecure_context():
    # TLS protokolü ile boş bir context yarat
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    # ÖNCE bunu kapatmak zorundayız (Hatanın sebebi bu sıraydı)
    context.check_hostname = False 
    # SONRA bunu kapatabiliriz
    context.verify_mode = ssl.CERT_NONE 
    return context

# Yamayı uygula: Artık Python her HTTPS bağlantısında bu fonksiyonu kullanacak
ssl._create_default_https_context = create_forcefully_insecure_context
# -----------------------------------------------------

import streamlit as st
from evds import evdsAPI
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.express as px
import warnings

# Diğer uyarıları da sustur
warnings.filterwarnings('ignore')

# --- KULLANICI AYARLARI ---
USER_API_KEY = "Uol1kIOQos"

# --- LİSTE ---
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

st.set_page_config(page_title="TAV Fiyat Farkı", layout="wide")
st.title("🧮 Profesyonel Fiyat Farkı Hesaplama")

# Sidebar
st.sidebar.header("Ayarlar")
today = date.today()
# Hata almamak için varsayılan tarihleri güvenli aralığa çekiyoruz
s_date = st.sidebar.date_input("Başlangıç", today.replace(day=1) - relativedelta(months=13))
e_date = st.sidebar.date_input("Bitiş", today.replace(day=1) - relativedelta(months=2))

valid_options = [k for k in SECTOR_CODES.keys() if k != "—"]
sel_name = st.sidebar.selectbox("Endeks", valid_options)
sel_code = SECTOR_CODES[sel_name]

st.sidebar.info(f"Formül: (TÜFE + {sel_name}) / 2")

# --- VERİ ÇEKME ---
def get_data(api_key, start, end, code, name):
    evds = evdsAPI(api_key)
    # Ekstra güvenlik: Session verify'ı da kapatalım
    if hasattr(evds, 'session'): evds.session.verify = False

    s_str = start.replace(day=1).strftime("%d-%m-%Y")
    e_str = end.replace(day=1).strftime("%d-%m-%Y")
    
    try:
        raw_df = evds.get_data(["TP.FG.J0", code], startdate=s_str, enddate=e_str)
    except Exception as e:
        return None, f"Bağlantı Hatası: {e}"

    if raw_df is None or raw_df.empty:
        return None, "Veri boş döndü. Tarihleri kontrol edin."

    # İşleme
    raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
    
    # Sütun Bulma
    col_map = {}
    tufe_clean = "TPFGJ0"
    ufe_clean = code.replace(".", "").replace("_", "")
    
    for col in raw_df.columns:
        c = col.replace(".", "").replace("_", "")
        if tufe_clean in c: col_map[col] = "TÜFE"
        elif ufe_clean in c: col_map[col] = "UFE"
        
    raw_df.rename(columns=col_map, inplace=True)
    
    if "TÜFE" not in raw_df.columns or "UFE" not in raw_df.columns:
        return None, f"Veri eksik. TCMB '{name}' verisini bu tarihler için girmemiş olabilir."
        
    # Hesap
    raw_df["TÜFE"] = pd.to_numeric(raw_df["TÜFE"], errors='coerce')
    raw_df["UFE"] = pd.to_numeric(raw_df["UFE"], errors='coerce')
    
    row_s = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == pd.Period(start, 'M')]
    row_e = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == pd.Period(end, 'M')]
    
    if row_s.empty or row_e.empty:
        return None, "Seçilen aylarda veri yok."
        
    s_t, e_t = row_s["TÜFE"].values[0], row_e["TÜFE"].values[0]
    s_u, e_u = row_s["UFE"].values[0], row_e["UFE"].values[0]
    
    if pd.isna(s_u) or pd.isna(e_u):
        return None, "ÜFE verisi NaN (Boş)."
        
    t_deg = ((e_t - s_t)/s_t)*100
    u_deg = ((e_u - s_u)/s_u)*100
    avg = (t_deg + u_deg)/2
    
    return {
        "start": start.strftime("%m-%Y"), "end": end.strftime("%m-%Y"),
        "t_deg": t_deg, "u_deg": u_deg, "avg": avg,
        "raw": raw_df
    }, None

# --- EKRAN ---
if st.button("HESAPLA"):
    with st.spinner("İşleniyor..."):
        res, err = get_data(USER_API_KEY, s_date, e_date, sel_code, sel_name)
        
        if err:
            st.error(f"❌ {err}")
        else:
            st.success(f"Dönem: {res['start']} -> {res['end']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("TÜFE", f"%{res['t_deg']:.2f}")
            c2.metric("ÜFE", f"%{res['u_deg']:.2f}")
            c3.metric("ORTALAMA", f"%{res['avg']:.2f}")
            
            st.dataframe(res['raw'])
