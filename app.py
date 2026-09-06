import streamlit as st
import pandas as pd
import numpy as np
import requests
import time

st.set_page_config(page_title="Crypto Scanner Pro", layout="wide")

st.title("📊 Scanner de Trading Crypto (Top 100 Coinbase)")

# --- BARRE LATÉRALE : PARAMÈTRES ---
st.sidebar.header("⚙️ Configuration des Signaux")

timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
capital_initial = st.sidebar.number_input("Capital initial ($)", value=100.0, step=10.0)
risque_pct = st.sidebar.number_input("Risque par trade (%)", value=1.0, step=0.5)

st.sidebar.subheader("Indicateurs & Filtres")
use_ema_filter = st.sidebar.checkbox("Activer le filtre de tendance EMA 200", value=True)
rsi_period = st.sidebar.slider("Période RSI", 5, 30, 14)
rsi_oversold = st.sidebar.slider("Seuil Survente (Achat)", 10, 45, 30)
rsi_overbought = st.sidebar.slider("Seuil Surachat (Vente)", 55, 90, 70)

st.sidebar.subheader("Gestion des Risques (SL / TP)")
type_sl_tp = st.sidebar.radio("Mode de calcul SL/TP", ["Pourcentage Fixe", "Basé sur ATR"])

if type_sl_tp == "Pourcentage Fixe":
    stop_loss_pct = st.sidebar.number_input("Stop Loss (%)", value=2.0, step=0.1)
    take_profit_pct = st.sidebar.number_input("Take Profit (%)", value=6.0, step=0.1)
    atr_mult_sl, atr_mult_tp = 1.5, 3.0
else:
    atr_period = st.sidebar.slider("Période ATR", 5, 30, 14)
    atr_mult_sl = st.sidebar.number_input("Multiplicateur ATR SL", value=1.5, step=0.1)
    atr_mult_tp = st.sidebar.number_input("Multiplicateur ATR TP", value=3.0, step=0.1)
    stop_loss_pct, take_profit_pct = 1.5, 3.0

# --- LISTE DES PAIRES (TOP 100 COINBASE - ZEC INCLUS, SHIB EXCLU) ---
PAIRS_TOP_100 = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD", "LTC-USD", "BCH-USD", "UNI-USD",
    "ATOM-USD", "XLM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD", "ICP-USD", "FIL-USD", "APT-USD", "OP-USD", "ARB-USD",
    "LDO-USD", "INJ-USD", "TIA-USD", "SUI-USD", "RENDER-USD", "PEPE-USD", "DOGE-USD", "FET-USD", "AAVE-USD", "ZEC-USD",
    "STX-USD", "CRV-USD", "MKR-USD", "GRT-USD", "RNDR-USD", "SNX-USD", "THETA-USD", "QNT-USD", "FTM-USD", "FLOW-USD",
    "AXS-USD", "SAND-USD", "MANA-USD", "EGLD-USD", "CHZ-USD", "KSM-USD", "COMP-USD", "DASH-USD", "ENJ-USD", "1INCH-USD",
    "BAT-USD", "LRC-USD", "ANKR-USD", "STORJ-USD", "BAL-USD", "YFI-USD", "UMA-USD", "ZRX-USD", "KAVA-USD", "SKL-USD",
    "RLC-USD", "BAND-USD", "NMR-USD", "CVC-USD", "OXT-USD", "POLS-USD", "ACH-USD", "SPELL-USD", "API3-USD", "BLUR-USD",
    "MAGIC-USD", "GMX-USD", "OSMO-USD", "SEI-USD", "BONK-USD", "FLOKI-USD", "JUP-USD", "PYTH-USD", "STRK-USD", "WIF-USD",
    "MEME-USD", "ALT-USD", "DYM-USD", "PIXEL-USD", "PORTAL-USD", "AEVO-USD", "ENA-USD", "W-USD", "TNSR-USD", "OMNI-USD",
    "REZ-USD", "BB-USD", "NOT-USD", "IO-USD", "ZK-USD", "ZRO-USD", "RARE-USD", "GVT-USD", "POL-USD", "SUPER-USD"
]

# --- RECUPERATION DES DONNEES ---
@st.cache_data(ttl=60)
def fetch_data(symbol, interval):
    granularity_map = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    granularity = granularity_map.get(interval, 3600)
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={granularity}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
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
        st.error(f"Erreur lors de la récupération de {symbol} : {e}")
    return pd.DataFrame()

# --- CALCUL DES INDICATEURS ---
def calculate_indicators(df):
    if len(df) < 200:
        return df

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    # EMA 200
    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

    return df

# --- SCAN DU MARCHE ---
if st.button("🔄 Lancer le Scan du Marché (Top 100)", type="primary"):
    buy_signals = []
    sell_signals = []
    neutral_signals = []

    progress_bar = st.progress(0)
    total_pairs = len(PAIRS_TOP_100)

    for idx, symbol in enumerate(PAIRS_TOP_100):
        df = fetch_data(symbol, timeframe)
        if not df.empty and len(df) >= 200:
            df = calculate_indicators(df)
            price = df['close'].iloc[-1]
            rsi = df['RSI'].iloc[-1]
            atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0
            ema200 = df['EMA200'].iloc[-1]

            if not pd.isna(rsi) and not pd.isna(ema200):
                is_buy = rsi < rsi_oversold and (not use_ema_filter or price > ema200)
                is_sell = rsi > rsi_overbought and (not use_ema_filter or price < ema200)

                if is_buy:
                    signal = "🟢 ACHAT"
                    if type_sl_tp == "Pourcentage Fixe":
                        sl_price = price * (1 - stop_loss_pct / 100)
                        tp_price = price * (1 + take_profit_pct / 100)
                    else:
                        sl_price = price - (atr * atr_mult_sl)
                        tp_price = price + (atr * atr_mult_tp)

                    buy_signals.append({
                        "Crypto": symbol,
                        "Prix": f"${price:,.4f}",
                        "RSI_val": rsi,
                        "RSI (14)": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Signal": signal,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

                elif is_sell:
                    signal = "🔴 VENTE"
                    if type_sl_tp == "Pourcentage Fixe":
                        sl_price = price * (1 + stop_loss_pct / 100)
                        tp_price = price * (1 - take_profit_pct / 100)
                    else:
                        sl_price = price + (atr * atr_mult_sl)
                        tp_price = price - (atr * atr_mult_tp)

                    sell_signals.append({
                        "Crypto": symbol,
                        "Prix": f"${price:,.4f}",
                        "RSI_val": rsi,
                        "RSI (14)": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Signal": signal,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

                else:
                    sl_price = price * (1 - stop_loss_pct / 100)
                    tp_price = price * (1 + take_profit_pct / 100)
                    neutral_signals.append({
                        "Crypto": symbol,
                        "Prix": f"${price:,.4f}",
                        "RSI_val": rsi,
                        "RSI (14)": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Signal": "NEUTRE",
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

        progress_bar.progress((idx + 1) / total_pairs)
        time.sleep(0.12)  # Pause anti-blocage API Coinbase

    progress_bar.empty()

    # Tri par RSI croissant (du plus petit au plus grand)
    buy_signals = sorted(buy_signals, key=lambda x: x["RSI_val"])
    sell_signals = sorted(sell_signals, key=lambda x: x["RSI_val"])
    neutral_signals = sorted(neutral_signals, key=lambda x: x["RSI_val"])

    # Fusion : Achats -> Ventes -> Neutres
    all_results = buy_signals + sell_signals + neutral_signals

    if all_results:
        res_df = pd.DataFrame(all_results).drop(columns=["RSI_val"])

        def highlight_signal(val):
            if "ACHAT" in val:
                return 'background-color: #d4edda; color: #155724; font-weight: bold;'
            elif "VENTE" in val:
                return 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
            return ''

        total_signals = len(buy_signals) + len(sell_signals)
        if total_signals > 0:
            st.success(f"🔥 {total_signals} signal/signaux actif(s) détecté(s) ({len(buy_signals)} Achats, {len(sell_signals)} Ventes)")
        else:
            st.info("Aucun signal actif pour le moment. Affichage des cryptos neutres.")

        st.dataframe(res_df.style.map(highlight_signal, subset=['Signal']), use_container_width=True, height=800)
    else:
        st.info("Aucune donnée disponible pour le moment.")

