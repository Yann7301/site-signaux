import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from streamlit_echarts import st_echarts

st.set_page_config(page_title="Crypto Scanner Pro", layout="wide")

st.title("📊 Scanner de Trading Crypto (Top 100 Coinbase)")

# --- BARRE LATÉRALE : PARAMÈTRES ---
st.sidebar.header("⚙️ Configuration des Signaux")

timeframe = st.sidebar.selectbox("Timeframe du Scan", ["15m", "30m", "1h", "4h", "1d"], index=2)
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

# --- RÉCUPÉRATION ET AGRÉGATION DES BOUGIES ---
@st.cache_data(ttl=60)
def fetch_data(symbol, interval):
    # Map des granularités réelles Coinbase (300, 900, 3600, 86400)
    # Pour 30m, on récupère du 15m (900s) qu'on agrège.
    # Pour 4h, on récupère du 1h (3600s) qu'on agrège.
    base_granularity_map = {
        "5m": 300,
        "15m": 900,
        "30m": 900,   # Récupère du 15m
        "1h": 3600,
        "4h": 3600,   # Récupère du 1h
        "1d": 86400
    }
    
    granularity = base_granularity_map.get(interval, 3600)
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
                
                # Resampling dynamique si 30m ou 4h
                if interval in ["30m", "4h"]:
                    df.set_index('timestamp', inplace=True)
                    rule = '30min' if interval == "30m" else '4h'
                    df = df.resample(rule).agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna().reset_index()

                return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        st.error(f"Erreur lors de la récupération de {symbol} : {e}")
    return pd.DataFrame()

# --- CALCUL DES INDICATEURS ---
def calculate_indicators(df):
    if len(df) < 14:
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

    # EMA 200 (s'adapte à la longueur du DataFrame)
    ema_span = min(200, len(df))
    df['EMA200'] = df['close'].ewm(span=ema_span, adjust=False).mean()

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
        if not df.empty and len(df) >= 20:
            df = calculate_indicators(df)

            # Analyse de la dernière bougie
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
        time.sleep(0.05)

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

# --- VOLET ROULANT & GRAPHIQUE BOUGIES (ECHARTS) ---
st.markdown("---")
st.subheader("📈 Graphique Interactif des Bougies & Signaux")

col_pair, col_tf = st.columns([2, 3])

with col_pair:
    selected_pair = st.selectbox("Crypto-monnaie :", PAIRS_TOP_100, index=0)

with col_tf:
    chart_timeframe = st.radio(
        "Unité de temps du graphique :",
        ["5m", "15m", "30m", "1h", "4h", "1d"],
        index=2,
        horizontal=True
    )

if selected_pair:
    chart_df = fetch_data(selected_pair, chart_timeframe)

    if not chart_df.empty and len(chart_df) >= 20:
        chart_df = calculate_indicators(chart_df)

        # Préparation des données pour ECharts : [ouvert, ferme, bas, haut]
        dates = chart_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M').tolist()
        kline_data = chart_df[['open', 'close', 'low', 'high']].values.tolist()

        # Signaux historiques
        signals_points = []
        start_idx = max(14, len(chart_df) - 200)
        for i in range(start_idx, len(chart_df)):
            p = chart_df['close'].iloc[i]
            r = chart_df['RSI'].iloc[i]
            e = chart_df['EMA200'].iloc[i]
            date_str = dates[i]

            if not pd.isna(r) and not pd.isna(e):
                if r < rsi_oversold and (not use_ema_filter or p > e):
                    signals_points.append({
                        "name": "ACHAT",
                        "coord": [date_str, chart_df['low'].iloc[i] * 0.995],
                        "value": "🟢 ACHAT",
                        "itemStyle": {"color": "#28a745"}
                    })
                elif r > rsi_overbought and (not use_ema_filter or p < e):
                    signals_points.append({
                        "name": "VENTE",
                        "coord": [date_str, chart_df['high'].iloc[i] * 1.005],
                        "value": "🔴 VENTE",
                        "itemStyle": {"color": "#dc3545"}
                    })

        # Configuration ECharts
        option = {
            "backgroundColor": "#111827",
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"}
            },
            "grid": {
                "left": "5%",
                "right": "5%",
                "bottom": "15%",
                "top": "5%"
            },
            "xAxis": {
                "type": "category",
                "data": dates,
                "scale": True,
                "boundaryGap": False,
                "axisLine": {"onZero": False},
                "splitLine": {"show": False}
            },
            "yAxis": {
                "scale": True,
                "splitArea": {"show": True}
            },
            "dataZoom": [
                {"type": "inside", "start": 30, "end": 100},
                {"type": "slider", "start": 30, "end": 100}
            ],
            "series": [
                {
                    "name": selected_pair,
                    "type": "candlestick",
                    "data": kline_data,
                    "itemStyle": {
                        "color": "#06d6a0",
                        "color0": "#ef476f",
                        "borderColor": "#06d6a0",
                        "borderColor0": "#ef476f"
                    },
                    "markPoint": {
                        "data": signals_points,
                        "label": {"formatter": "{b}"}
                    }
                }
            ]
        }

        # Rendu du graphique
        st_echarts(options=option, height="500px")

        # --- RÉCAPITULATIF DES INFOS CLÉS (EN BAS DU GRAPHIQUE) ---
        last_price = chart_df['close'].iloc[-1]
        prev_price = chart_df['close'].iloc[-2] if len(chart_df) > 1 else last_price
        var_pct = ((last_price - prev_price) / prev_price) * 100 if prev_price != 0 else 0

        last_rsi = chart_df['RSI'].iloc[-1]
        last_ema = chart_df['EMA200'].iloc[-1]
        last_atr = chart_df['ATR'].iloc[-1]

        if last_rsi < rsi_oversold and (not use_ema_filter or last_price > last_ema):
            status = "🟢 Signal ACHAT"
        elif last_rsi > rsi_overbought and (not use_ema_filter or last_price < last_ema):
            status = "🔴 Signal VENTE"
        else:
            status = "⚪ NEUTRE"

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Prix Actuel", f"${last_price:,.4f}", f"{var_pct:+.2f}%")
        col2.metric("RSI (14)", f"{last_rsi:.1f}" if not pd.isna(last_rsi) else "N/A")
        col3.metric("EMA 200", f"${last_ema:,.4f}" if not pd.isna(last_ema) else "N/A")
        col4.metric("ATR (14)", f"${last_atr:,.4f}" if not pd.isna(last_atr) else "N/A")
        col5.metric("Statut Actuel", status)

    else:
        st.warning(f"Données insuffisantes pour afficher le graphique de {selected_pair} en {chart_timeframe}.")

