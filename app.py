import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import plotly.graph_objects as go

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
    stop_loss_pct, take_profit_pct = 2.0, 6.0

# --- LISTE DES PAIRES (TOP 100 COINBASE) ---
PAIRS_TOP_100 = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD", "LTC-USD", "BCH-USD", "UNI-USD",
    "ATOM-USD", "XLM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD", "ICP-USD", "FIL-USD", "APT-USD", "OP-USD", "ARB-USD",
    "LDO-USD", "INJ-USD", "TIA-USD", "SUI-USD", "RENDER-USD", "PEPE-USD", "DOGE-USD", "FET-USD", "AAVE-USD", "ZEC-USD",
    "STX-USD", "CRV-USD", "MKR-USD", "GRT-USD", "SNX-USD", "THETA-USD", "QNT-USD", "FTM-USD", "FLOW-USD",
    "AXS-USD", "SAND-USD", "MANA-USD", "EGLD-USD", "CHZ-USD", "KSM-USD", "COMP-USD", "DASH-USD", "ENJ-USD", "1INCH-USD",
    "BAT-USD", "LRC-USD", "ANKR-USD", "STORJ-USD", "BAL-USD", "YFI-USD", "UMA-USD", "ZRX-USD", "KAVA-USD", "SKL-USD",
    "RLC-USD", "BAND-USD", "NMR-USD", "CVC-USD", "OXT-USD", "POLS-USD", "ACH-USD", "SPELL-USD", "API3-USD", "BLUR-USD",
    "MAGIC-USD", "GMX-USD", "OSMO-USD", "SEI-USD", "BONK-USD", "FLOKI-USD", "JUP-USD", "PYTH-USD", "STRK-USD", "WIF-USD",
    "MEME-USD", "ALT-USD", "DYM-USD", "PIXEL-USD", "PORTAL-USD", "AEVO-USD", "ENA-USD", "W-USD", "TNSR-USD", "OMNI-USD",
    "REZ-USD", "BB-USD", "NOT-USD", "IO-USD", "ZK-USD", "ZRO-USD", "RARE-USD", "GVT-USD", "POL-USD", "SUPER-USD"
]

# --- RÉCUPÉRATION DES DONNÉES ---
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

# --- SCAN DU MARCHÉ ---
if st.button("🔄 Lancer le Scan du Marché (Top 100)", type="primary"):
    buy_signals = []
    sell_signals = []
    neutral_signals = []

    progress_bar = st.progress(0)
    total_pairs = len(PAIRS_TOP_100)

    for idx, symbol in enumerate(PAIRS_TOP_100):
        df = fetch_data(symbol, timeframe)
        if not df.empty and len(df) >= 201:
            df = calculate_indicators(df)

            # Analyse sur la dernière bougie clôturée (index -2)
            price = df['close'].iloc[-2]
            rsi = df['RSI'].iloc[-2]
            atr = df['ATR'].iloc[-2] if not pd.isna(df['ATR'].iloc[-2]) else 0
            ema200 = df['EMA200'].iloc[-2]

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
        time.sleep(0.15)

    progress_bar.empty()

    # Tri par RSI croissant
    buy_signals = sorted(buy_signals, key=lambda x: x["RSI_val"])
    sell_signals = sorted(sell_signals, key=lambda x: x["RSI_val"])
    neutral_signals = sorted(neutral_signals, key=lambda x: x["RSI_val"])

    all_results = buy_signals + sell_signals + neutral_signals

    if all_results:
        res_df = pd.DataFrame(all_results).drop(columns=["RSI_val"])

        def style_dataframe(df):
            def highlight(row):
                val = row['Signal']
                if "ACHAT" in val:
                    return ['background-color: #d4edda; color: #155724; font-weight: bold;' if col == 'Signal' else '' for col in row.index]
                elif "VENTE" in val:
                    return ['background-color: #f8d7da; color: #721c24; font-weight: bold;' if col == 'Signal' else '' for col in row.index]
                return ['' for _ in row.index]
            return df.style.apply(highlight, axis=1)

        total_signals = len(buy_signals) + len(sell_signals)
        if total_signals > 0:
            st.success(f"🔥 {total_signals} signal/signaux actif(s) détecté(s) ({len(buy_signals)} Achats, {len(sell_signals)} Ventes)")
        else:
            st.info("Aucun signal actif pour le moment. Affichage des cryptos neutres.")

        st.dataframe(style_dataframe(res_df), use_container_width=True, height=500)
    else:
        st.info("Aucune donnée disponible pour le moment.")

# --- VOLET ROULANT & GRAPHIQUE BOUGIES ---
st.markdown("---")
st.subheader("📈 Graphique Interactif des Bougies & Signaux")

selected_pair = st.selectbox("Sélectionnez une crypto-monnaie du Top 100 :", PAIRS_TOP_100, index=0)

if selected_pair:
    chart_df = fetch_data(selected_pair, timeframe)

    if not chart_df.empty and len(chart_df) >= 201:
        chart_df = calculate_indicators(chart_df)

        # Détection des signaux historiques sur l'ensemble des bougies
        buy_signals_x = []
        buy_signals_y = []
        sell_signals_x = []
        sell_signals_y = []

        for i in range(200, len(chart_df)):
            p = chart_df['close'].iloc[i]
            r = chart_df['RSI'].iloc[i]
            e = chart_df['EMA200'].iloc[i]
            t = chart_df['timestamp'].iloc[i]

            if not pd.isna(r) and not pd.isna(e):
                if r < rsi_oversold and (not use_ema_filter or p > e):
                    buy_signals_x.append(t)
                    buy_signals_y.append(chart_df['low'].iloc[i] * 0.995)
                elif r > rsi_overbought and (not use_ema_filter or p < e):
                    sell_signals_x.append(t)
                    sell_signals_y.append(chart_df['high'].iloc[i] * 1.005)

        fig = go.Figure()

        # Graphique en bougies uniquement
        fig.add_trace(go.Candlestick(
            x=chart_df['timestamp'],
            open=chart_df['open'],
            high=chart_df['high'],
            low=chart_df['low'],
            close=chart_df['close'],
            name="Prix"
        ))

        # Affichage des signaux d'achat
        if buy_signals_x:
            fig.add_trace(go.Scatter(
                x=buy_signals_x,
                y=buy_signals_y,
                mode='markers',
                marker=dict(symbol='triangle-up', size=12, color='green'),
                name='Signal ACHAT'
            ))

        # Affichage des signaux de vente
        if sell_signals_x:
            fig.add_trace(go.Scatter(
                x=sell_signals_x,
                y=sell_signals_y,
                mode='markers',
                marker=dict(symbol='triangle-down', size=12, color='red'),
                name='Signal VENTE'
            ))

        fig.update_layout(
            title=f"Graphique {selected_pair} ({timeframe})",
            yaxis_title="Prix ($)",
            xaxis_title="Date / Heure",
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            height=650,
            margin=dict(l=20, r=20, t=50, b=20)
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"Données insuffisantes pour afficher le graphique de {selected_pair}.")

