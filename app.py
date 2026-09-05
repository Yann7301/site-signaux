import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import resend
import requests
import streamlit as st

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Scanner Trading YouHolder", page_icon="📊", layout="wide"
)

st.title("📊 Scanner & Analyse Trading - Paires YouHolder")

# Liste des 30 cryptos majeures / plus tradées sur YouHolder
YOUHOLDER_TOP_30 = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "LINKUSDT",
    "MATICUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "UNIUSDT",
    "ATOMUSDT",
    "XLMUSDT",
    "ETCUSDT",
    "NEARUSDT",
    "ALGOUSDT",
    "ICPUSDT",
    "FILUSDT",
    "APTUSDT",
    "OPUSDT",
    "ARBUSDT",
    "LDOUSDT",
    "INJUSDT",
    "TIAUSDT",
    "SUIUSDT",
    "RNDRUSDT",
    "PEPEUSDT",
    "DOGEUSDT",
]

# ==========================================
# ⚙️ PANNEAU DE CONFIGURATION DYNAMIQUE
# ==========================================
st.sidebar.header("⚙️ Configuration Capital & Risque")

capital_initial = st.sidebar.number_input(
    "Solde / Capital YouHolder ($)", min_value=10.0, value=1000.0, step=50.0
)

risque_pct = st.sidebar.slider(
    "Risque par trade (%)", min_value=0.5, max_value=5.0, value=1.0, step=0.5
)

montant_risque = capital_initial * (risque_pct / 100)
st.sidebar.info(f"💵 Risque max par trade : **${montant_risque:.2f}**")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Niveaux TP / SL & Stratégie")

type_sl_tp = st.sidebar.selectbox(
    "Mode de calcul TP / SL", ["Pourcentage Fixe", "Dynamique (ATR)"]
)

stop_loss_pct = None
take_profit_pct = None
atr_period = 14
atr_mult_sl = None
atr_mult_tp = None

if type_sl_tp == "Pourcentage Fixe":
    stop_loss_pct = st.sidebar.slider("Stop Loss (%)", 0.5, 10.0, 2.0, 0.5)
    take_profit_pct = st.sidebar.slider("Take Profit (%)", 1.0, 20.0, 4.0, 0.5)
    rr_ratio = take_profit_pct / stop_loss_pct
    st.sidebar.caption(f"📈 Ratio Risque/Rendement (R:R) : **1:{rr_ratio:.2f}**")
else:
    atr_period = st.sidebar.number_input(
        "Période ATR", value=14, min_value=5, max_value=30
    )
    atr_mult_sl = st.sidebar.slider(
        "Multiplicateur SL (x ATR)", 1.0, 4.0, 1.5, 0.1
    )
    atr_mult_tp = st.sidebar.slider(
        "Multiplicateur TP (x ATR)", 1.0, 6.0, 3.0, 0.1
    )
    rr_ratio = atr_mult_tp / atr_mult_sl
    st.sidebar.caption(f"📈 Ratio Risque/Rendement (R:R) : **1:{rr_ratio:.2f}**")

st.sidebar.markdown("---")
st.sidebar.header("⏱️ Sélection Paire & Unité de temps")

symbol = st.sidebar.selectbox("Cryptomonnaie (YouHolder)", YOUHOLDER_TOP_30, index=0)
timeframe = st.sidebar.selectbox(
    "Unité de Temps", ["15m", "1h", "4h", "1d"], index=1
)

# --- EXPORT DE CONFIGURATION JSON ---
config_data = {
    "symbol": symbol,
    "timeframe": timeframe,
    "capital_initial": capital_initial,
    "risque_pct": risque_pct,
    "type_sl_tp": type_sl_tp,
    "stop_loss_pct": stop_loss_pct,
    "take_profit_pct": take_profit_pct,
    "atr_period": atr_period,
    "atr_mult_sl": atr_mult_sl,
    "atr_mult_tp": atr_mult_tp,
}

config_json_bytes = json.dumps(config_data, indent=4)

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Exporter pour le Bot H24")
st.sidebar.download_button(
    label="📥 Télécharger config.json",
    data=config_json_bytes,
    file_name="config.json",
    mime="application/json",
    use_container_width=True,
)


# ==========================================
# 📈 DONNÉES ET CALCULS
# ==========================================
@st.cache_data(ttl=300)
def fetch_data(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(
            data,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "qav",
                "num_trades",
                "taker_base_vol",
                "taker_quote_vol",
                "ignore",
            ],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        st.error(f"Erreur de chargement des données : {e}")
        return pd.DataFrame()


df = fetch_data(symbol, timeframe)

if not df.empty:
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df["ATR"] = true_range.rolling(atr_period).mean()

    current_price = df["close"].iloc[-1]
    current_rsi = df["RSI"].iloc[-1]
    current_atr = df["ATR"].iloc[-1]

    if type_sl_tp == "Pourcentage Fixe":
        sl_price_buy = current_price * (1 - stop_loss_pct / 100)
        tp_price_buy = current_price * (1 + take_profit_pct / 100)
        sl_dist = current_price - sl_price_buy
    else:
        sl_dist = current_atr * atr_mult_sl
        sl_price_buy = current_price - sl_dist
        tp_price_buy = current_price + (current_atr * atr_mult_tp)

    position_size_crypto = montant_risque / sl_dist if sl_dist > 0 else 0
    position_size_usd = position_size_crypto * current_price

    signal = "NEUTRE"
    if current_rsi < 30:
        signal = "ACHAT (Survendu)"
    elif current_rsi > 70:
        signal = "VENTE (Suraheté)"

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Prix Actuel", f"${current_price:,.4f}")
    m2.metric("RSI (14)", f"{current_rsi:.1f}", delta=signal)
    m3.metric("Take Profit (TP)", f"${tp_price_buy:,.4f}")
    m4.metric("Stop Loss (SL)", f"${sl_price_buy:,.4f}")

    st.markdown("---")

    col_chart, col_summary = st.columns([2, 1])

    with col_chart:
        st.subheader(f"Graphique {symbol} ({timeframe})")
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df["timestamp"],
                    open=df["open"],
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    name="Prix",
                )
            ]
        )
        fig.add_hline(
            y=tp_price_buy,
            line_dash="dash",
            line_color="green",
            annotation_text="TP",
        )
        fig.add_hline(
            y=sl_price_buy,
            line_dash="dash",
            line_color="red",
            annotation_text="SL",
        )
        fig.update_layout(
            height=400,
            margin=dict(l=20, r=20, t=20, b=20),
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_summary:
        st.subheader("📋 Récapitulatif Trade YouHolder")
        st.write(f"**Capital total :** `${capital_initial:,.2f}`")
        st.write(
            f"**Risque engagé ({risque_pct}%) :** `${montant_risque:,.2f}`"
        )
        st.write(
            f"**Taille de position :** `{position_size_crypto:.4f}` unités (`${position_size_usd:,.2f}`)"
        )
        st.write(f"**Niveau TP :** `${tp_price_buy:,.4f}`")
        st.write(f"**Niveau SL :** `${sl_price_buy:,.4f}`")
        st.write(f"**Ratio R:R :** `1:{rr_ratio:.2f}`")

        st.markdown("---")

        if st.button(
            "📧 Tester l'envoi d'alerte Email", use_container_width=True
        ):
            api_key = st.secrets.get("RESEND_API_KEY")
            to_email = st.secrets.get("TO_EMAIL")

            if not api_key or not to_email:
                st.error("⚠️ Secrets RESEND_API_KEY ou TO_EMAIL manquants.")
            else:
                resend.api_key = api_key
                html_msg = f"""
                <h3>🔔 ALERTE TRADING YOUHOLDER : {symbol} ({timeframe})</h3>
                <p><b>Signal :</b> {signal}</p>
                <p><b>Prix :</b> ${current_price:,.4f}</p>
                <p><b>Take Profit :</b> ${tp_price_buy:,.4f}</p>
                <p><b>Stop Loss :</b> ${sl_price_buy:,.4f}</p>
                <p><b>Position :</b> ${position_size_usd:,.2f} (Risque ${montant_risque:,.2f})</p>
                """
                try:
                    resend.Emails.send(
                        {
                            "from": "Scanner YouHolder <onboarding@resend.dev>",
                            "to": [to_email],
                            "subject": f"🚨 SIGNAL YOUHOLDER {symbol} - {signal}",
                            "html": html_msg,
                        }
                    )
                    st.success("Email envoyé !")
                except Exception as e:
                    st.error(f"Erreur d'envoi : {e}")

