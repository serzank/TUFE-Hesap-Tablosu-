import streamlit as st
from evds import evdsAPI
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import plotly.express as px
import requests
import warnings
import ssl

# --- 1. SSL/BAĞLANTI SORUNU İÇİN KESİN ÇÖZÜM ---
# Şirket ağlarında (Proxy/Firewall) sertifika hatasını önleyen blok.
def create_insecure_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

ssl._create_default_https_context = create_insecure_ssl_context
warnings.filterwarnings('ignore')
# ------------------------------------------------

# --- KULLANICI AYARLARI ---
USER_API_KEY = "Uol1kIOQos"

# --- GENİŞ ÜRETİCİ FİYAT ENDEKSİ LİSTESİ ---
# Hem Mal (Yİ-ÜFE) hem Hizmet (H-ÜFE) sektörlerini içerir.
SECTOR_CODES = {
    "📌 Yİ-ÜFE (Genel - Sanayi)": "TP.TUFE1YI.T1", 
    "📌 H-ÜFE (Genel - Hizmet)": "TP.HUFE17.GENEL",
    
    "— TAV ÖZEL: HİZMET KALEMLERİ —": "—",
    "🛡️ Güvenlik Hizmetleri (N80)": "TP.HUFE17.80",
    "🧹 Temizlik Hizmetleri (N812)": "TP.HUFE17.812",
    "🍽️ Yemek / Catering (I56)": "TP.HUFE17.56",
    "✈️ Yer Hizmetleri & Havayolu (H51)": "TP.HUFE17.51",
    "📦 Depolama ve Lojistik (H52)": "TP.HUFE17.52",
    "💻 IT ve Bilgi Sistemleri (J62)": "TP.HUFE17.62",
    
    "— TAV ÖZEL: MALZEME & İNŞAAT —": "—",
    "🏗️ İnşaat Maliyet Endeksi (Genel)": "TP.IMS.GENEL", # Alternatif İndeks
    "⚡ Elektrik, Gaz Üretim (D)": "TP.YI-UFE.D",
    "🪨 Madencilik ve Taşocakçılığı (B)": "TP.YI-UFE.B",
}

# --- Sayfa Ayarları ---
st.set_page_config(page_title="TAV Fiyat Farkı Analizi", layout="wide")
st.title("🧮 Profesyonel Fiyat Farkı Hesaplama")
st.markdown("Seçilen tarih aralığında **TÜFE** ile belirlediğiniz **Üretici Fiyat Endeksi (ÜFE/H-ÜFE)** kalemini kıyaslar.")

# --- Sidebar ---
st.sidebar.header("1. Tarih Seçimi")
today = date.today()
default_end = today.replace(day=1) - relativedelta(months=1)
default_start = default_end - relativedelta(months=12)

start_date = st.sidebar.date_input("Başlangıç", default_start)
end_date = st.sidebar.date_input("Bitiş", default_end)

st.sidebar.markdown("---")
st.sidebar.header("2. Üretici Endeksi Seçimi")

# Listeden seçim yapma (Ayırıcı çizgileri filtreleyerek)
valid_options = [k for k in SECTOR_CODES.keys() if k != "—"]
selected_name = st.sidebar.selectbox("Endeks Türü", valid_options, index=0)
selected_code = SECTOR_CODES[selected_name]

st.sidebar.success(f"Formül: (TÜFE + {selected_name}) / 2")

# --- Yardımcı Fonksiyon ---
@st.cache_data
def get_analysis_data(api_key, start, end, ufe_code, ufe_name):
    evds = evdsAPI(api_key)
    if hasattr(evds, 'session'): evds.session.verify = False

    if start >= end:
        return None, None, "Başlangıç tarihi bitişten büyük olamaz."

    # Tarih formatı
    s_str = start.replace(day=1).strftime("%d-%m-%Y")
    e_str = end.replace(day=1).strftime("%d-%m-%Y")
    
    # TÜFE ve Seçilen ÜFE'yi çek
    series = ["TP.FG.J0", ufe_code]
    
    try:
        raw_df = evds.get_data(series, startdate=s_str, enddate=e_str)
    except Exception as e:
        return None, None, f"Veri Çekme Hatası: {e}"

    if raw_df is None or raw_df.empty:
        return None, None, "TCMB veri döndürmedi (Tarih aralığı boş olabilir)."

    # Tarih işleme
    raw_df['Tarih_Dt'] = pd.to_datetime(raw_df['Tarih'], format='%Y-%m')
    raw_df.rename(columns={"Tarih": "Dönem"}, inplace=True)

    # Sütunları Tanıma (Akıllı Eşleşme)
    # Hangi sütun TÜFE, hangisi ÜFE bulmamız lazım
    col_map = {}
    tufe_pattern = "TPFGJ0"
    ufe_pattern = ufe_code.replace(".", "").replace("_", "") # Kodun temiz hali

    for col in raw_df.columns:
        clean_col = col.replace(".", "").replace("_", "")
        if tufe_pattern in clean_col:
            col_map[col] = "TÜFE"
        elif ufe_pattern in clean_col:
            col_map[col] = "SEÇİLEN_UFE"
            
    raw_df.rename(columns=col_map, inplace=True)

    # Veri var mı kontrolü
    if "TÜFE" not in raw_df.columns or "SEÇİLEN_UFE" not in raw_df.columns:
        return None, raw_df, f"Seçilen '{ufe_name}' için veri bulunamadı. (TCMB henüz girmemiş olabilir)."

    # Sayısala Çevir
    raw_df["TÜFE"] = pd.to_numeric(raw_df["TÜFE"], errors='coerce')
    raw_df["SEÇİLEN_UFE"] = pd.to_numeric(raw_df["SEÇİLEN_UFE"], errors='coerce')

    # Başlangıç ve Bitiş Değerlerini Al
    start_period = pd.Period(start, freq='M')
    end_period = pd.Period(end, freq='M')

    row_start = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == start_period]
    row_end = raw_df[raw_df['Tarih_Dt'].dt.to_period('M') == end_period]

    if row_start.empty or row_end.empty:
        return None, raw_df, "Seçilen aylardan birinde veri eksik."

    val_s_tufe = row_start["TÜFE"].values[0]
    val_e_tufe = row_end["TÜFE"].values[0]
    val_s_ufe = row_start["SEÇİLEN_UFE"].values[0]
    val_e_ufe = row_end["SEÇİLEN_UFE"].values[0]

    if pd.isna(val_s_ufe) or pd.isna(val_e_ufe):
         return None, raw_df, f"'{ufe_name}' verisi bu tarihlerde eksik (NaN)."

    # Hesaplama
    degisim_tufe = ((val_e_tufe - val_s_tufe) / val_s_tufe) * 100
    degisim_ufe = ((val_e_ufe - val_s_ufe) / val_s_ufe) * 100
    ortalama = (degisim_tufe + degisim_ufe) / 2

    summary = {
        "start_txt": start.strftime("%B %Y"),
        "end_txt": end.strftime("%B %Y"),
        "tufe_artis": degisim_tufe,
        "ufe_artis": degisim_ufe,
        "ortalama": ortalama,
        "s_tufe": val_s_tufe, "e_tufe": val_e_tufe,
        "s_ufe": val_s_ufe, "e_ufe": val_e_ufe
    }

    return summary, None, raw_df

# --- Ana Ekran ---
if st.button("HESAPLA"):
    with st.spinner("Analiz yapılıyor..."):
        summ, err, df = get_analysis_data(USER_API_KEY, start_date, end_date, selected_code, selected_name)

        if err:
            st.error(err)
            if df is not None:
                with st.expander("Ham Veri Kontrolü"):
                    st.write(df)
        elif summ:
            # Başarılı Sonuç
            st.success(f"Dönem: {summ['start_txt']} ➡️ {summ['end_txt']}")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("TÜFE Artışı", f"%{summ['tufe_artis']:.2f}")
            c2.metric("ÜFE Artışı", f"%{summ['ufe_artis']:.2f}", help=selected_name)
            c3.metric("ORTALAMA (T+Ü)/2", f"%{summ['ortalama']:.2f}", delta="Fiyat Farkı")

            st.divider()

            # Tablo
            st.subheader("📋 Hesaplama Detayı")
            table_data = {
                "Endeks Tipi": ["TÜFE (Tüketici)", selected_name, "ORTALAMA"],
                "Başlangıç Değeri": [summ["s_tufe"], summ["s_ufe"], "-"],
                "Bitiş Değeri": [summ["e_tufe"], summ["e_ufe"], "-"],
                "Artış Oranı (%)": [summ["tufe_artis"], summ["ufe_artis"], summ["ortalama"]]
            }
            df_table = pd.DataFrame(table_data)
            
            st.dataframe(
                df_table,
                column_config={
                    "Başlangıç Değeri": st.column_config.NumberColumn(format="%.2f"),
                    "Bitiş Değeri": st.column_config.NumberColumn(format="%.2f"),
                    "Artış Oranı (%)": st.column_config.NumberColumn(format="%.2f %%"),
                },
                use_container_width=True,
                hide_index=True
            )

            # Grafik
            st.subheader("📈 Trend Grafiği")
            if df is not None:
                plot_df = df.rename(columns={"SEÇİLEN_UFE": selected_name})
                st.plotly_chart(
                    px.line(plot_df, x="Dönem", y=["TÜFE", selected_name], markers=True),
                    use_container_width=True
                )
                
            # İndir
            csv = df_table.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Excel/CSV İndir", csv, "fiyat_farki.csv", "text/csv")
