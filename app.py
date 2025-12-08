# --- 1. ADIM: BU KOD BLOKU EN ÜSTTE KALMALIDIR (NÜKLEER SSL YAMASI) ---
import ssl

# Python'un standart "Güvenli Bağlantı Oluşturma" fonksiyonunu hackliyoruz.
# Standart fonksiyonu silip, yerine her şeyi kabul eden kendi fonksiyonumuzu koyuyoruz.
def create_hacked_ssl_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    # Boş bir SSL protokolü yarat
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    # ÖNCE: Sunucu adı kontrolünü kapat (Hatanın sebebi bu sıralamaydı)
    context.check_hostname = False
    # SONRA: Sertifika doğrulamasını kapat
    context.verify_mode = ssl.CERT_NONE
    return context

# Python'un orijinal fonksiyonunu eziyoruz. Artık tüm kütüphaneler bu gevşek ayarı kullanacak.
ssl.create_default_context = create_hacked_ssl_context
# ----------------------------------------------------------------------

import streamlit as st
from evds import evdsAPI
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.express as px
import warnings

# Tüm uyarıları sustur
warnings.filterwarnings('ignore')

# --- KULLANICI AYARLARI ---
USER_API_KEY = "Uol1kIOQos"

# --- GENİŞLETİLMİŞ LİSTE (TAV ÖZEL) ---
SECTOR_CODES = {
    "📌 Yİ-ÜFE (Genel - Sanayi)": "TP.TUFE1YI.T1", 
    "📌 H-ÜFE (Genel - Hizmet)": "TP.HUFE17.GENEL",
    
    "— HİZMET SÖZLEŞMELERİ —": "—",
    "🛡️ Güvenlik Hizmetleri (N80)": "TP.HUFE17.80",
    "🧹 Temizlik Hizmetleri (N812)": "TP.HUFE17.812",
    "🍽️ Yemek / Catering (I56)": "TP.HUFE17.56",
    "✈️ Havayolu Taşımacılığı (H51)": "TP.HUFE17.51",
    "📦 Depolama ve Lojistik (H52)": "TP.HUFE17.52",
    "💻 IT ve Danışmanlık (J62)": "TP.HUFE17.62",
    "📄 Büro Yönetimi (N82)": "TP.HUFE17.82",
    
    "— MALZEME & İNŞAAT —": "—",
    "🏗️ İnşaat Maliyet Endeksi": "TP.IMS.GENEL",
    "⚡ Elektrik, Gaz Üretim": "TP.YI-UFE.D",
}

st.set_page_config(page_title="TAV Fiyat Farkı", layout="wide")
st.title("🧮 Profesyonel Fiyat Farkı Hesaplama")

# --- SIDEBAR ---
st.sidebar.header("Ayarlar")
today = date.today()
s_date = st.sidebar.date_input("Başlangıç", today.replace(day=1) - relativedelta(months=13))
e_date = st.sidebar.date_input("Bitiş", today.replace(day=1) - relativedelta(months=2))

# Çizgileri filtrele
valid_opts = [k for k in SECTOR_CODES.keys() if k != "—"]
sel_name = st.sidebar.selectbox("Endeks Seçimi", valid_opts)
sel_code = SECTOR_CODES[sel_name]

st.sidebar.success(f"Formül: (TÜFE + {sel_name}) / 2")

# --- VERİ ÇEKME FONKSİYONU ---
def get_data_secure(api_key, start, end, code, name):
    # EVDS kütüphanesini başlat
    evds = evdsAPI(api_key)
    
    # Ekstra Güvenlik: Session seviyesinde de verify kapatıyoruz (Çift dikiş)
    if hasattr(evds, 'session'):
        evds.session.verify = False
        evds.session.trust_env = False # Proxy ayarlarını bazen bypass etmek gerekir

    # Tarih Formatı
    s_str = start.replace(day=1).strftime("%d-%m-%Y")
    e_str = end.replace(day=1).strftime("%d-%m-%Y")
    
    series = ["TP.FG.J0", code]
    
    try:
        raw_df = evds.get_data(series, startdate=s_str, enddate=e_str)
    except Exception as e:
        return None, f"Bağlantı Hatası: {str(e)}"

    if raw_df is None or raw_df.empty:
        return None, "Veri boş döndü. (TCMB veriyi girmemiş olabilir veya tarih aralığı hatalı)"

    # --- VERİ İŞLEME ---
    raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
    
    # Sütunları Tanı
    col_map = {}
    tufe_patt = "TPFGJ0"
    ufe_patt = code.replace(".", "").replace("_", "")
    
    for c in raw_df.columns:
        clean = c.replace(".", "").replace("_", "")
        if tufe_patt in clean: col_map[c] = "TÜFE"
        elif ufe_patt in clean: col_map[c] = "UFE"
        
    raw_df.rename(columns=col_map, inplace=True)
    
    if "TÜFE" not in raw_df.columns or "UFE" not in raw_df.columns:
        return None, f"Veri Eksik: '{name}' için TCMB verisi bulunamadı."
        
    # Sayısala Çevir
    raw_df["TÜFE"] = pd.to_numeric(raw_df["TÜFE"], errors='coerce')
    raw_df["UFE"] = pd.to_numeric(raw_df["UFE"], errors='coerce')
    
    # Başlangıç/Bitiş Satırlarını Al
    row_s = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == pd.Period(start, 'M')]
    row_e = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == pd.Period(end, 'M')]
    
    if row_s.empty or row_e.empty:
        return None, "Seçilen ayların birinde veri yok."
        
    s_t, e_t = row_s["TÜFE"].values[0], row_e["TÜFE"].values[0]
    s_u, e_u = row_s["UFE"].values[0], row_e["UFE"].values[0]
    
    if pd.isna(s_u) or pd.isna(e_u):
        return None, "ÜFE verisi NaN (Boş)."
        
    # Hesapla
    t_deg = ((e_t - s_t)/s_t)*100
    u_deg = ((e_u - s_u)/s_u)*100
    avg = (t_deg + u_deg)/2
    
    return {
        "start": start.strftime("%m-%Y"), "end": end.strftime("%m-%Y"),
        "t": t_deg, "u": u_deg, "avg": avg,
        "raw": raw_df, "s_t": s_t, "e_t": e_t, "s_u": s_u, "e_u": e_u
    }, None

# --- EKRAN ---
if st.button("HESAPLA"):
    with st.spinner("TAV Ağı üzerinden veri çekiliyor..."):
        res, err = get_data_secure(USER_API_KEY, s_date, e_date, sel_code, sel_name)
        
        if err:
            st.error(f"❌ {err}")
        else:
            st.success(f"Analiz Dönemi: {res['start']} -> {res['end']}")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("TÜFE Artışı", f"%{res['t']:.2f}")
            c2.metric(f"{sel_name}", f"%{res['u']:.2f}")
            c3.metric("ORTALAMA ARTIŞ", f"%{res['avg']:.2f}", delta="Sözleşme Farkı")
            
            st.divider()
            
            # Tablo
            st.subheader("📋 Detaylı Tablo")
            df_display = pd.DataFrame({
                "Endeks": ["TÜFE", sel_name, "ORTALAMA"],
                "Başlangıç Endeksi": [res["s_t"], res["s_u"], "-"],
                "Bitiş Endeksi": [res["e_t"], res["e_u"], "-"],
                "Artış (%)": [res["t"], res["u"], res["avg"]]
            })
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Grafik
            st.subheader("📈 Grafik")
            plot_df = res['raw'].rename(columns={"UFE": sel_name})
            st.plotly_chart(px.line(plot_df, x="Dönem", y=["TÜFE", sel_name], markers=True), use_container_width=True)
            
            # İndir
            csv = df_display.to_csv(index=False).encode('utf-8')
            st.download_button("📥 İndir", csv, "fiyat_farki.csv", "text/csv")
