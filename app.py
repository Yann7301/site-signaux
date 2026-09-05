import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import resend

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Scanner & Analyse Trading Crypto",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Scanner & Analyse Trading Crypto")

# ==========================================
# ⚙️ PANNEAU DE CONFIGURATION DYNAMIQUE
# ==========================================
st.sidebar.header("⚙️ Configuration du Capital & Risque")

# 1. Gestion du Capital
capital_initial = st.sidebar.number_input(
    "Solde / Capital ($)", 
    min_value=10.0, 
    value=1000.0, 
    step=50.0
)

risque_pct = st.sidebar.slider(
    "Risque par trade (%)", 
    min_value=0.5, 
    max_value=5.0, 
    value=1.0, 
    step=0.5
)

montant_risque = capital_initial * (risque_pct / 100)
st.sidebar.info(f"💵 Risque max par trade : **${montant_risque:.2f}**")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Niveaux TP / SL & Stratégie")

type_sl_tp = st.sidebar.selectbox(
    "Mode de calcul TP / SL", 
    ["Pourcentage Fixe", "Dynamique (ATR)"]
)

if type_sl_tp == "Pourcentage Fixe":
    stop_loss_pct = st.sidebar.slider("Stop Loss (%)", 0.5, 10.0, 2.0, 0.5)
    take_profit_pct = st.sidebar.slider("Take Profit (%)", 1.0, 20.0, 4.0, 0.5)
    rr_ratio = take_profit_pct / stop_loss_pct
    st.sidebar.caption(f"📈 Ratio Risque/Rendement (R:R) : **1:{rr_ratio:.2f}**")
else:
    atr_period = st.sidebar.number_input("Période ATR", value=14, min_value=5, max_value=30)
    atr_mult_sl = st.sidebar.slider("Multiplicateur SL (x ATR)", 1.0, 4.0, 1.5, 0.1)
    atr_mult_tp = st.sidebar.slider("Multiplicateur TP (x ATR)", 1.0, 6.0, 3.0, 0.1)
    rr_ratio = atr_mult_tp / atr_mult_sl
    st.sidebar.caption(f"📈 Ratio Risque/Rendement (R:R) : **1:{rr_ratio:.2f}**")

st.sidebar.markdown("---")
st.sidebar.header("⏱️ Fréquence & Paire")

symbol = st.sidebar.selectbox("Paire Crypto", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"], index=0)
timeframe = st.sidebar.selectbox("Unité de Temps (Timeframe)", ["15m", "1h", "4h", "1d"], index=1)

# ==========================================
# 📈 RÉCUPÉRATION DES DONNÉES & INDICATEURS
# ==========================================

@st.cache_data(ttl=300)
def fetch_binance_data(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données Binance : {e}")
        return pd.DataFrame()

df = fetch_binance_data(symbol, timeframe)

if not df.empty:
    # Calcul RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Calcul ATR (14)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    # Prix actuel
    current_price = df['close'].iloc[-1]
    current_rsi = df['RSI'].iloc[-1]
    current_atr = df['ATR'].iloc[-1]

    # Calcul dynamique TP / SL
    if type_sl_tp == "Pourcentage Fixe":
        sl_price_buy = current_price * (1 - stop_loss_pct / 100)
        tp_price_buy = current_price * (1 + take_profit_pct / 100)
        sl_dist = current_price - sl_price_buy
    else:
        sl_dist = current_atr * atr_mult_sl
        sl_price_buy = current_price - sl_dist
        tp_price_buy = current_price + (current_atr * atr_mult_tp)

    # Calcul Position Sizing
    position_size_btc = montant_risque / sl_dist if sl_dist > 0 else 0
    position_size_usd = position_size_btc * current_price

    # Détection de signal basique
    signal = "NEUTRE"
    if current_rsi < 30:
        signal = "ACHAT (Oversold)"
    elif current_rsi > 70:
        signal = "VENTE (Overbought)"

    # ==========================================
    # 📊 AFFICHAGE DES MÉTRIQUES
    # ==========================================
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Prix Actuel", f"${current_price:,.2f}")
    m2.metric("Signal RSI", f"{current_rsi:.1f}", delta=signal)
    m3.metric("Take Profit (TP)", f"${tp_price_buy:,.2f}")
    m4.metric("Stop Loss (SL)", f"${sl_price_buy:,.2f}")

    st.markdown("---")

    col_chart, col_summary = st.columns([2, 1])

    with col_chart:
        st.subheader(f"Graphique {symbol} ({timeframe})")
        fig = go.Figure(data=[go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="Prix"
        )])
        # Lignes TP et SL
        fig.add_hline(y=tp_price_buy, line_dash="dash", line_color="green", annotation_text="TP")
        fig.add_hline(y=sl_price_buy, line_dash="dash", line_color="red", annotation_text="SL")
        fig.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_summary:
        st.subheader("📋 Récapitulatif du Trade")
        st.write(f"**Capital total :** `${capital_initial:,.2f}`")
        st.write(f"**Risque engagé ({risque_pct}%) :** `${montant_risque:,.2f}`")
        st.write(f"**Taille de position suggérée :** `{position_size_btc:.4f}` unités (`${position_size_usd:,.2f}`)")
        st.write(f"**Niveau TP :** `${tp_price_buy:,.2f}`")
        st.write(f"**Niveau SL :** `${sl_price_buy:,.2f}`")
        st.write(f"**Ratio Risque/Rendement :** `1:{rr_ratio:.2f}`")

        st.markdown("---")

        # Bouton de test d'envoi d'alerte email
        if st.button("📧 Envoyer une alerte de test par email", use_container_width=True):
            api_key = st.secrets.get("RESEND_API_KEY")
            to_email = st.secrets.get("TO_EMAIL")

            if not api_key or not to_email:
                st.error("⚠️ Secrets RESEND_API_KEY ou TO_EMAIL non configurés.")
            else:
                resend.api_key = api_key
                html_msg = f"""
                <h3>🔔 ALERTE TRADING : {symbol} ({timeframe})</h3>
                <p><b>Signal :</b> {signal}</p>
                <p><b>Prix :</b> ${current_price:,.2f}</p>
                <p><b>Take Profit :</b> ${tp_price_buy:,.2f}</p>
                <p><b>Stop Loss :</b> ${sl_price_buy:,.2f}</p>
                <p><b>Taille Position :</b> ${position_size_usd:,.2f} (Risque ${montant_risque:,.2f})</p>
                """
                try:
                    resend.Emails.send({
                        "from": "Alerte Trading <onboarding@resend.dev>",
                        "to": [to_email],
                        "subject": f"🚨 SIGNAL TRADING {symbol} - {signal}",
                        "html": html_msg
                    })
                    st.success("Email d'alerte envoyé avec succès !")
                except Exception as e:
                    st.error(f"Erreur d'envoi : {e}")

# ==========================================
# 🚀 MISE À JOUR DANS GIT
# ==========================================

