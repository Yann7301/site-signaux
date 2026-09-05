import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import json
import time

st.set_page_config(page_title="Scanner YouHolder Multi-Paires", page_icon="📊", layout="wide")

st.title("📊 Scanner & Analyse Trading - 30 Cryptos YouHolder")

YOUHOLDER_TOP_30 = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", 
    "DOTUSDT", "LINKUSDT", "POLUSDT", "LTCUSDT", "BCHUSDT", "UNIUSDT", "ATOMUSDT", 
    "XLMUSDT", "ETCUSDT", "NEARUSDT", "ALGOUSDT", "ICPUSDT", "FILUSDT", "APTUSDT", 
    "OPUSDT", "ARBUSDT", "LDOUSDT", "INJUSDT", "TIAUSDT", "SUIUSDT", "RENDERUSDT", 
    "PEPEUSDT", "DOGEUSDT"
]

# --- PARAMÈTRES GLOBAUX ---
st.sidebar.header("⚙️ Configuration Globale")

capital_initial = st.sidebar.number_input("Capital YouHolder Total ($)", min_value=10.0, value=1000.0, step=50.0)
risque_pct = st.sidebar.slider("Risque par trade (%)", 0.5, 5.0, 1.0, 0.5)
montant_risque = capital_initial * (risque_pct / 100)
st.sidebar.info(f"💵 Risque max par trade : **${montant_risque:.2f}**")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Stratégie TP / SL")

type_sl_tp = st.sidebar.selectbox("Mode de calcul TP / SL", ["Pourcentage Fixe", "Dynamique (ATR)"])

stop_loss_pct = None
take_profit_pct = None
atr_period = 14
atr_mult_sl = None
atr_mult_tp = None

if type_sl_tp == "Pourcentage Fixe":
    stop_loss_pct = st.sidebar.slider("Stop Loss (%)", 0.5, 10.0, 1.5, 0.5)
    take_profit_pct = st.sidebar.slider("Take Profit (%)", 1.0, 20.0, 3.0, 0.5)
    rr_ratio = take_profit_pct / stop_loss_pct
    st.sidebar.caption(f"📈 Ratio R:R : **1:{rr_ratio:.2f}**")
else:
    atr_period = st.sidebar.number_input("Période ATR", value=14, min_value=5, max_value=30)
    atr_mult_sl = st.sidebar.slider("Multiplicateur SL (x ATR)", 1.0, 4.0, 1.5, 0.1)
    atr_mult_tp = st.sidebar.slider("Multiplicateur TP (x ATR)", 1.0, 6.0, 3.0, 0.1)
    rr_ratio = atr_mult_tp / atr_mult_sl
    st.sidebar.caption(f"📈 Ratio R:R : **1:{rr_ratio:.2f}**")

st.sidebar.markdown("---")
st.sidebar.header("📊 Seuils RSI")
rsi_oversold = st.sidebar.slider("Seuil Achat (Survendu)", 20, 50, 40)
rsi_overbought = st.sidebar.slider("Seuil Vente (Suracheté)", 50, 80, 60)

st.sidebar.markdown("---")
timeframe = st.sidebar.selectbox("Unité de Temps Globale", ["15m", "1h", "4h", "1d"], index=0)

config_data = {
    "timeframe": timeframe,
    "capital_initial": capital_initial,
    "risque_pct": risque_pct,
    "type_sl_tp": type_sl_tp,
    "stop_loss_pct": stop_loss_pct,
    "take_profit_pct": take_profit_pct,
    "rsi_period": 14,
    "rsi_oversold": rsi_oversold,
    "rsi_overbought": rsi_overbought,
    "atr_period": atr_period,
    "atr_mult_sl": atr_mult_sl,
    "atr_mult_tp": atr_mult_tp
}

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Exporter pour le Bot H24")
st.sidebar.download_button(
    label="📥 Télécharger config.json",
    data=json.dumps(config_data, indent=4),
    file_name="config.json",
    mime="application/json",
    use_container_width=True
)

def fetch_data(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            raw_data = res.json()
            if raw_data:
                df = pd.DataFrame(raw_data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                cols = ['open', 'high', 'low', 'close', 'volume']
                df[cols] = df[cols].astype(float)
                
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        st.error(f"Erreur d'accès réseau pour {symbol} : {e}")

    return pd.DataFrame()

# --- 1. OPTION DE SCAN GLOBAL ---
if st.button("▶️ Lancer le Scan Complet (30 Cryptos)", type="primary", use_container_width=True):
    results = []
    progress_bar = st.progress(0)
    
    for idx, sym in enumerate(YOUHOLDER_TOP_30):
        df = fetch_data(sym, timeframe)
        
        if not df.empty and len(df) >= 14:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            df['ATR'] = true_range.rolling(atr_period).mean()

            price = df['close'].iloc[-1]
            rsi = df['RSI'].iloc[-1]
            atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0

            if type_sl_tp == "Pourcentage Fixe":
                sl_p = price * (1 - stop_loss_pct / 100)
                tp_p = price * (1 + take_profit_pct / 100)
            else:
                sl_p = price - (atr * atr_mult_sl)
                tp_p = price + (atr * atr_mult_tp)

            sig = "NEUTRE"
            if rsi < rsi_oversold:
                sig = f"🟢 ACHAT (RSI < {rsi_oversold})"
            elif rsi > rsi_overbought:
                sig = f"🔴 VENTE (RSI > {rsi_overbought})"

            results.append({
                "Crypto": sym,
                "Prix": f"${price:,.4f}",
                "RSI (14)": f"{rsi:.1f}" if not pd.isna(rsi) else "N/A",
                "Signal": sig,
                "Take Profit": f"${tp_p:,.4f}",
                "Stop Loss": f"${sl_p:,.4f}"
            })
        progress_bar.progress((idx + 1) / len(YOUHOLDER_TOP_30))

    st.success("Scan complet terminé !")
    if results:
        st.dataframe(pd.DataFrame(results), use_container_width=True)
    else:
        st.warning("Aucune donnée disponible actuellement.")

st.markdown("---")

# --- 2. EXAMEN DÉTAILLÉ D'UNE CRYPTO SÉLECTIONNÉE ---
st.subheader("🔎 Visualisation détaillée par Crypto")
selected_symbol = st.selectbox("Sélectionner une crypto à examiner", YOUHOLDER_TOP_30, index=0)

df_single = fetch_data(selected_symbol, timeframe)

if not df_single.empty and len(df_single) >= 14:
    delta = df_single['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_single['RSI'] = 100 - (100 / (1 + rs))

    high_low = df_single['high'] - df_single['low']
    high_close = np.abs(df_single['high'] - df_single['close'].shift())
    low_close = np.abs(df_single['low'] - df_single['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df_single['ATR'] = true_range.rolling(atr_period).mean()

    curr_price = df_single['close'].iloc[-1]
    curr_rsi = df_single['RSI'].iloc[-1]
    curr_atr = df_single['ATR'].iloc[-1] if not pd.isna(df_single['ATR'].iloc[-1]) else 0

    if type_sl_tp == "Pourcentage Fixe":
        sl_val = curr_price * (1 - stop_loss_pct / 100)
        tp_val = curr_price * (1 + take_profit_pct / 100)
    else:
        sl_val = curr_price - (curr_atr * atr_mult_sl)
        tp_val = curr_price + (curr_atr * atr_mult_tp)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Prix Actuel", f"${curr_price:,.4f}")
    col2.metric("RSI (14)", f"{curr_rsi:.1f}" if not pd.isna(curr_rsi) else "N/A")
    col3.metric("Take Profit Cible", f"${tp_val:,.4f}")
    col4.metric("Stop Loss Cible", f"${sl_val:,.4f}")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_single['timestamp'],
        open=df_single['open'],
        high=df_single['high'],
        low=df_single['low'],
        close=df_single['close'],
        name="Prix"
    ))
    fig.add_hline(y=tp_val, line_dash="dash", line_color="green", annotation_text="Take Profit")
    fig.add_hline(y=sl_val, line_dash="dash", line_color="red", annotation_text="Stop Loss")
    fig.update_layout(title=f"Graphique {selected_symbol} ({timeframe})", xaxis_rangeslider_visible=False, height=500)

    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Impossible de récupérer les données pour cette crypto. Réessayez dans quelques secondes.")

