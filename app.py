import time
import json
import math
import urllib.request
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(
    page_title="Crypto Scanner Pro",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Crypto Market Scanner & Candlestick Charts")
st.caption("Analyse en temps réel via l'API Coinbase — Graphiques interactifs Candlesticks & RSI")

# ==========================================
# 2. BARRE LATÉRALE DE CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ Paramètres")

DEFAULT_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "XLM-USD", "DOGE-USD", "AVAX-USD", "LINK-USD"]
selected_symbols = st.sidebar.multiselect(
    "Cryptomonnaies à analyser :",
    options=DEFAULT_SYMBOLS + ["ADA-USD", "DOT-USD", "MATIC-USD", "NEAR-USD"],
    default=DEFAULT_SYMBOLS
)

granularity_options = {
    "15 minutes": 900,
    "1 heure": 3600,
    "4 heures": 14400,
    "1 jour": 86400
}
selected_timeframe = st.sidebar.selectbox("Unité de temps :", list(granularity_options.keys()), index=1)
granularity = granularity_options[selected_timeframe]

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Stratégie ATR")
atr_sl_mult = st.sidebar.slider("Multiplicateur Stop-Loss (ATR)", 1.0, 3.0, 1.5, 0.1)
atr_tp_mult = st.sidebar.slider("Multiplicateur Take-Profit (ATR)", 1.5, 5.0, 3.0, 0.1)

# ==========================================
# 3. CALCULS INDICATEURS (PURE PYTHON)
# ==========================================
def calculate_sma(data, period):
    if len(data) < period:
        return [0] * len(data)
    sma = []
    for i in range(len(data)):
        if i < period - 1:
            sma.append(0)
        else:
            sma.append(sum(data[i - period + 1 : i + 1]) / period)
    return sma

def calculate_ema(prices, period):
    k = 2 / (period + 1)
    ema = [prices[0]]
    for price in prices[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema

def calculate_rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi = []
    
    for i in range(period, len(prices)):
        change = prices[i] - prices[i - 1]
        gain = max(change, 0)
        loss = max(-change, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal_period=9):
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = [f - s for f, s in zip(ema_fast[slow - 1:], ema_slow[slow - 1:])]
    signal_line = calculate_ema(macd_line, signal_period)
    return macd_line[-len(signal_line):], signal_line

def calculate_bollinger(prices, period=20, std_dev=2):
    sma = calculate_sma(prices, period)
    upper_band, lower_band = [], []
    
    for i in range(len(prices)):
        if i < period - 1:
            upper_band.append(0)
            lower_band.append(0)
        else:
            slice_p = prices[i - period + 1 : i + 1]
            mean = sma[i]
            variance = sum((x - mean) ** 2 for x in slice_p) / period
            stdev = math.sqrt(variance)
            upper_band.append(mean + (std_dev * stdev))
            lower_band.append(mean - (std_dev * stdev))
            
    return upper_band, lower_band, sma

def calculate_atr(candles, period=14):
    tr_list = []
    for i in range(1, len(candles)):
        high = candles[i][2]
        low = candles[i][1]
        prev_close = candles[i - 1][4]
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        tr_list.append(max(tr1, tr2, tr3))
        
    if len(tr_list) < period:
        return 0
    
    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period
        
    return atr

# ==========================================
# 4. MOTEUR D'ANALYSE ET RÉCUPÉRATION
# ==========================================
@st.cache_data(ttl=60)
def fetch_symbol_data(symbol, gran):
    try:
        url = f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity={gran}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req) as response:
            candles = json.loads(response.read().decode())
            
        candles.reverse()
        timestamps = [pd.to_datetime(c[0], unit='s') for c in candles]
        opens = [c[3] for c in candles]
        highs = [c[2] for c in candles]
        lows = [c[1] for c in candles]
        closes = [c[4] for c in candles]
        volumes = [c[5] for c in candles]
        
        if len(closes) < 200:
            return None

        rsi_vals = calculate_rsi(closes, 14)
        macd_line, macd_signal = calculate_macd(closes)
        upper_bb, lower_bb, sma20 = calculate_bollinger(closes, 20, 2)
        sma200 = calculate_sma(closes, 200)
        vol_sma20 = calculate_sma(volumes, 20)
        current_atr = calculate_atr(candles, 14)

        price = closes[-1]
        rsi = rsi_vals[-1]
        vol = volumes[-1]
        vol_avg = vol_sma20[-1]
        
        last_macd, prev_macd = macd_line[-1], macd_line[-2]
        last_sig, prev_sig = macd_signal[-1], macd_signal[-2]
        
        is_uptrend = price > sma200[-1]
        is_downtrend = price < sma200[-1]
        volume_spike = vol > (vol_avg * 1.1)

        signal_type = "NEUTRE"
        if rsi < 38 and (prev_macd < prev_sig and last_macd > last_sig) and is_uptrend and (price <= lower_bb[-1] * 1.01) and volume_spike:
            signal_type = "ACHAT"
        elif rsi > 62 and (prev_macd > prev_sig and last_macd < last_sig) and is_downtrend and (price >= upper_bb[-1] * 0.99) and volume_spike:
            signal_type = "VENTE"

        if signal_type == "ACHAT":
            sl = price - (atr_sl_mult * current_atr)
            tp = price + (atr_tp_mult * current_atr)
        elif signal_type == "VENTE":
            sl = price + (atr_sl_mult * current_atr)
            tp = price - (atr_tp_mult * current_atr)
        else:
            sl, tp = None, None

        return {
            "summary": {
                "Paire": symbol,
                "Prix ($)": price,
                "RSI": round(rsi, 1),
                "Tendance": "🟢 Haussière" if is_uptrend else "🔴 Baissière",
                "Volume Spike": "✅ Oui" if volume_spike else "❌ Non",
                "ATR ($)": round(current_atr, 4),
                "Signal": signal_type,
                "Stop-Loss ($)": round(sl, 4) if sl else "-",
                "Take-Profit ($)": round(tp, 4) if tp else "-"
            },
            "history": {
                "timestamps": timestamps,
                "opens": opens,
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "upper_bb": upper_bb,
                "lower_bb": lower_bb,
                "sma20": sma20,
                "rsi": [None] * (len(closes) - len(rsi_vals)) + rsi_vals
            }
        }
    except Exception as e:
        st.error(f"Erreur lors du traitement de {symbol} : {e}")
        return None

# ==========================================
# 5. EXECUTION ET CALCULS
# ==========================================
if st.button("🔄 Rafraîchir les données"):
    st.cache_data.clear()

results = []
signals = []
charts_data = {}

with st.spinner("Analyse du marché et génération des graphiques..."):
    for sym in selected_symbols:
        res = fetch_symbol_data(sym, granularity)
        if res:
            results.append(res["summary"])
            charts_data[sym] = res["history"]
            if res["summary"]["Signal"] in ["ACHAT", "VENTE"]:
                signals.append(res["summary"])

# ==========================================
# 6. AFFICHAGE DE L'INTERFACE
# ==========================================

# Section 1 : Alerte Signaux
if signals:
    st.subheader("🚀 Signaux Détectés")
    for sig in signals:
        st.success(f"**{sig['Paire']}** — Signal **{sig['Signal']}** détecté au prix de **${sig['Prix ($)']:,}**")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Prix d'entrée", f"${sig['Prix ($)']:,}")
        col2.metric("RSI", sig["RSI"])
        col3.metric("Stop-Loss (SL)", f"${sig['Stop-Loss ($)']:,}")
        col4.metric("Take-Profit (TP)", f"${sig['Take-Profit ($)']:,}")
        st.markdown("---")
else:
    st.info("Aucun signal d'achat ou de vente strict détecté actuellement.")

# Section 2 : Tableau global
st.subheader("📊 Vue d'ensemble du marché")
if results:
    df = pd.DataFrame(results)
    
    def highlight_signal(val):
        if val == "ACHAT":
            return 'background-color: rgba(0, 255, 0, 0.2); font-weight: bold;'
        elif val == "VENTE":
            return 'background-color: rgba(255, 0, 0, 0.2); font-weight: bold;'
        return ''

    # Utilisation de .map() au lieu de .applymap() pour compatibilité Pandas
    styled_df = df.style.map(highlight_signal, subset=['Signal'])
    st.dataframe(styled_df, use_container_width=True, height=250)

# Section 3 : Graphiques interactifs Plotly avec Chandeliers Japonais
st.subheader("📈 Graphiques détaillés (Chandeliers Japonais, Bollinger & RSI)")

if charts_data:
    target_symbol = st.selectbox("Choisir la crypto à afficher :", options=list(charts_data.keys()))
    hist = charts_data[target_symbol]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(f"Cours {target_symbol} (Chandeliers) & Bandes de Bollinger", "RSI (Relative Strength Index)"),
        row_width=[0.3, 0.7]
    )

    # 1. Candlesticks (Bougies japonaises)
    fig.add_trace(go.Candlestick(
        x=hist["timestamps"],
        open=hist["opens"],
        high=hist["highs"],
        low=hist["lows"],
        close=hist["closes"],
        name='Prix (OHLC)',
        increasing_line_color='#00E676',
        decreasing_line_color='#FF5252'
    ), row=1, col=1)

    # 2. Bandes de Bollinger
    fig.add_trace(go.Scatter(
        x=hist["timestamps"], y=hist["upper_bb"],
        mode='lines', name='Bollinger Supérieure',
        line=dict(color='rgba(255, 255, 255, 0.4)', dash='dash')
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=hist["timestamps"], y=hist["lower_bb"],
        mode='lines', name='Bollinger Inférieure',
        line=dict(color='rgba(255, 255, 255, 0.4)', dash='dash'),
        fill='tonexty', fillcolor='rgba(255, 255, 255, 0.03)'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=hist["timestamps"], y=hist["sma20"],
        mode='lines', name='SMA 20',
        line=dict(color='#FFD700', width=1)
    ), row=1, col=1)

    # 3. RSI
    fig.add_trace(go.Scatter(
        x=hist["timestamps"], y=hist["rsi"],
        mode='lines', name='RSI (14)',
        line=dict(color='#E040FB', width=2)
    ), row=2, col=1)

    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Surachat (70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Survente (30)")

    fig.update_layout(
        height=650,
        template="plotly_dark",
        margin=dict(l=20, r=20, t=40, b=20),
        hovermode="x unified",
        showlegend=False,
        xaxis_rangeslider_visible=False
    )
    
    fig.update_yaxes(title_text="Prix ($)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

    st.plotly_chart(fig, use_container_width=True)

st.caption(f"Dernière mise à jour : {time.strftime('%H:%M:%S')}")

