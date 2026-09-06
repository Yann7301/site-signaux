import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import os
import time

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Scanner Trading Coinbase RSI/ATR/EMA",
    page_icon="📈",
    layout="wide"
)

PAIRS_TOP_30 = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD",
    "DOT-USD", "LINK-USD", "LTC-USD", "BCH-USD", "UNI-USD",
    "ATOM-USD", "XLM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD",
    "ICP-USD", "FIL-USD", "APT-USD", "OP-USD", "ARB-USD",
    "LDO-USD", "INJ-USD", "TIA-USD", "SUI-USD", "RENDER-USD",
    "PEPE-USD", "DOGE-USD", "FET-USD", "AAVE-USD", "SHIB-USD"
]

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "timeframe": "1h",
        "capital_initial": 1000.0,
        "type_sl_tp": "Pourcentage Fixe",
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3.0,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "atr_period": 14,
        "atr_mult_sl": 1.5,
        "atr_mult_tp": 3.0,
        "use_ema_filter": True,
        "email_sender": "",
        "email_password": "",
        "email_receiver": "",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    }

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

@st.cache_data(ttl=60)
def fetch_data(symbol, interval):
    granularity_map = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    granularity = granularity_map.get(interval, 3600)
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={granularity}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            raw_data = res.json()
            if raw_data:
                df = pd.DataFrame(raw_data, columns=['timestamp', 'low', 'high', 'open', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
                df = df.sort_values('timestamp').reset_index(drop=True)
                cols = ['open', 'high', 'low', 'close', 'volume']
                df[cols] = df[cols].astype(float)
                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        st.error(f"Erreur pour {symbol} : {e}")
    return pd.DataFrame()

def calculate_indicators(df, config):
    if len(df) < 200:
        return df

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=config["rsi_period"]).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=config["rsi_period"]).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(config["atr_period"]).mean()

    # EMA 200
    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

    return df

# --- INTERFACE STREAMLIT ---
config = load_config()

st.title("📈 Scanner de Trading Coinbase RSI / ATR / EMA 200")
st.markdown("Filtrage dynamique de la tendance globale via EMA 200 sur le Top 30 Coinbase.")

# --- BARRE LATÉRALE ---
st.sidebar.header("⚙️ Configuration")
timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=["15m", "1h", "4h", "1d"].index(config.get("timeframe", "1h")))

st.sidebar.subheader("Indicateurs & Filtre")
use_ema_filter = st.sidebar.checkbox("Activer le filtre de tendance EMA 200", value=config.get("use_ema_filter", True))
rsi_period = st.sidebar.number_input("Période RSI", value=int(config.get("rsi_period", 14)))
rsi_oversold = st.sidebar.number_input("Seuil Survendu (Achat)", value=int(config.get("rsi_oversold", 30)))
rsi_overbought = st.sidebar.number_input("Seuil Suracheté (Vente)", value=int(config.get("rsi_overbought", 70)))

st.sidebar.subheader("Gestion des Risques (SL/TP)")
type_sl_tp = st.sidebar.radio("Mode de calcul SL/TP", ["Pourcentage Fixe", "ATR Dynamique"], index=0 if config.get("type_sl_tp") == "Pourcentage Fixe" else 1)

if type_sl_tp == "Pourcentage Fixe":
    stop_loss_pct = st.sidebar.number_input("Stop Loss (%)", value=float(config.get("stop_loss_pct", 1.5)))
    take_profit_pct = st.sidebar.number_input("Take Profit (%)", value=float(config.get("take_profit_pct", 3.0)))
    atr_mult_sl, atr_mult_tp = 1.5, 3.0
else:
    stop_loss_pct, take_profit_pct = 1.5, 3.0
    atr_period = st.sidebar.number_input("Période ATR", value=int(config.get("atr_period", 14)))
    atr_mult_sl = st.sidebar.number_input("Multiplicateur ATR SL", value=float(config.get("atr_mult_sl", 1.5)))
    atr_mult_tp = st.sidebar.number_input("Multiplicateur ATR TP", value=float(config.get("atr_mult_tp", 3.0)))

if st.sidebar.button("💾 Sauvegarder la configuration"):
    new_config = {
        "timeframe": timeframe,
        "capital_initial": config.get("capital_initial", 1000.0),
        "type_sl_tp": type_sl_tp,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "rsi_period": rsi_period,
        "rsi_oversold": rsi_oversold,
        "rsi_overbought": rsi_overbought,
        "atr_period": config.get("atr_period", 14),
        "atr_mult_sl": atr_mult_sl,
        "atr_mult_tp": atr_mult_tp,
        "use_ema_filter": use_ema_filter,
        "email_sender": config.get("email_sender", ""),
        "email_password": config.get("email_password", ""),
        "email_receiver": config.get("email_receiver", ""),
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    }
    save_config(new_config)
    st.sidebar.success("Configuration sauvegardée !")

# --- EXÉCUTION DU SCAN ---
if st.button("🚀 Lancer le Scan"):
    current_config = load_config()
    st.info(f"Analyse en cours sur 30 cryptos ({timeframe}) avec Filtre EMA 200 : {'Activé' if use_ema_filter else 'Désactivé'}...")

    results = []
    signals = []
    progress_bar = st.progress(0)

    for i, symbol in enumerate(PAIRS_TOP_30):
        df = fetch_data(symbol, timeframe)
        if not df.empty and len(df) >= 200:
            df = calculate_indicators(df, current_config)

            price = df['close'].iloc[-1]
            rsi = df['RSI'].iloc[-1]
            atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0
            ema200 = df['EMA200'].iloc[-1]

            if not pd.isna(rsi) and not pd.isna(ema200):
                if current_config["type_sl_tp"] == "Pourcentage Fixe":
                    sl_price = price * (1 - current_config["stop_loss_pct"] / 100)
                    tp_price = price * (1 + current_config["take_profit_pct"] / 100)
                else:
                    sl_price = price - (atr * current_config["atr_mult_sl"])
                    tp_price = price + (atr * current_config["atr_mult_tp"])

                signal_type = "NEUTRE"
                trend = "🟢 Haussière" if price > ema200 else "🔴 Baissière"

                # Application des conditions avec ou sans filtre EMA
                is_buy = rsi < current_config["rsi_oversold"] and (not use_ema_filter or price > ema200)
                is_sell = rsi > current_config["rsi_overbought"] and (not use_ema_filter or price < ema200)

                if is_buy:
                    signal_type = "🟢 ACHAT"
                    signals.append({
                        "Crypto": symbol,
                        "Signal": signal_type,
                        "Prix d'entrée": f"${price:,.4f}",
                        "RSI": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Tendance": trend,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })
                elif is_sell:
                    signal_type = "🔴 VENTE"
                    signals.append({
                        "Crypto": symbol,
                        "Signal": signal_type,
                        "Prix d'entrée": f"${price:,.4f}",
                        "RSI": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Tendance": trend,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

                results.append({
                    "Crypto": symbol,
                    "Prix d'entrée": f"${price:,.4f}",
                    "RSI": round(rsi, 1),
                    "EMA 200": f"${ema200:,.4f}",
                    "Tendance": trend,
                    "Signal": signal_type,
                    "Take Profit": f"${tp_price:,.4f}",
                    "Stop Loss": f"${sl_price:,.4f}"
                })

        progress_bar.progress((i + 1) / len(PAIRS_TOP_30))
        time.sleep(0.05)

    st.subheader("📢 Signaux Validés par la Tendance")
    if signals:
        st.dataframe(pd.DataFrame(signals), use_container_width=True)
    else:
        st.info("Aucun signal correspondant aux critères de tendance actuels.")

    st.subheader("📊 Tableau Général des 30 Cryptos")
    if results:
        st.dataframe(pd.DataFrame(results), use_container_width=True)

