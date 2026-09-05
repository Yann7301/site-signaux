import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
import ccxt
import resend

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Scanner Crypto & Position Sizing",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Scanner Crypto Multi-Indicateurs & Risk Management")

# --- BARRE LATÉRALE : PARAMÈTRES ET GESTION DU RISQUE ---
st.sidebar.header("⚙️ Gestion du Risque")
capital_total = st.sidebar.number_input("Capital Total ($)", min_value=50.0, value=1000.0, step=50.0)
risque_pct = st.sidebar.slider("Risque par trade (%)", min_value=0.5, max_value=5.0, value=1.0, step=0.5)

st.sidebar.header("🔍 Configuration du Scanner")
symboles_defaut = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD"]
symboles_choisis = st.sidebar.multiselect("Paires à scanner", symboles_defaut, default=symboles_defaut)
timeframe = st.sidebar.selectbox("Horizon de temps (Timeframe)", ["1h", "4h", "1d"], index=0)

# --- FONCTIONS TECHNIQUES & CALCULS ---

@st.cache_data(ttl=300)
def charger_donnees(symbol, timeframe, limit=100):
    """Récupère les données OHLCV depuis Coinbase via CCXT."""
    exchange = ccxt.coinbase()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculer_indicateurs(df):
    """Calcule le RSI, le MACD, les Bandes de Bollinger et l'ATR."""
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_MACD'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # Bandes de Bollinger (20, 2)
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['STD20'] = df['close'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['SMA20'] + (df['STD20'] * 2)
    df['Bollinger_Lower'] = df['SMA20'] - (df['STD20'] * 2)

    # ATR (14)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    return df

def analyser_signal(df):
    """Détecte les signaux ACHAT ou VENTE selon les indicateurs."""
    derniere_ligne = df.iloc[-1]
    
    rsi = derniere_ligne['RSI']
    macd = derniere_ligne['MACD']
    signal_macd = derniere_ligne['Signal_MACD']
    close = derniere_ligne['close']
    bollinger_lower = derniere_ligne['Bollinger_Lower']
    bollinger_upper = derniere_ligne['Bollinger_Upper']
    atr = derniere_ligne['ATR']

    signal = "NEUTRE"

    # Condition d'ACHAT : RSI survendu (< 40), croisement MACD haussier, prix proche bas Bollinger
    if rsi < 40 and macd > signal_macd and close <= bollinger_lower * 1.01:
        signal = "ACHAT"
        sl = close - (1.5 * atr)
        tp = close + (3.0 * atr)
    # Condition de VENTE : RSI suracheté (> 60), croisement MACD baissier, prix proche haut Bollinger
    elif rsi > 60 and macd < signal_macd and close >= bollinger_upper * 0.99:
        signal = "VENTE"
        sl = close + (1.5 * atr)
        tp = close - (3.0 * atr)
    else:
        sl = 0.0
        tp = 0.0

    return signal, close, sl, tp, atr

def calculer_taille_position(capital, risque_pct, prix_entree, stop_loss):
    """Calcule le montant en $ à investir pour respecter le risque choisi."""
    distance_sl_pct = abs(prix_entree - stop_loss) / prix_entree
    if distance_sl_pct == 0:
        return 0.0, 0.0
    
    montant_risque_usd = capital * (risque_pct / 100.0)
    position_usd = montant_risque_usd / distance_sl_pct
    return round(position_usd, 2), round(montant_risque_usd, 2)

def envoyer_email_alerte(symbol, signal_type, prix, sl, tp, pos_usd, risque_usd):
    """Envoie un mail formaté via l'API Resend."""
    api_key = st.secrets.get("RESEND_API_KEY")
    to_email = st.secrets.get("TO_EMAIL")

    if not api_key or not to_email:
        st.error("⚠️ Secrets RESEND_API_KEY ou TO_EMAIL manquants dans Streamlit Cloud.")
        return False

    resend.api_key = api_key

    contenu_html = f"""
    <h2>🚨 Signal Crypto : {signal_type} sur {symbol}</h2>
    <p>Un nouveau signal vient d'être identifié par le scanner.</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif;">
      <tr><td><b>Paire</b></td><td>{symbol}</td></tr>
      <tr><td><b>Signal</b></td><td><b>{signal_type}</b></td></tr>
      <tr><td><b>Prix d'entrée</b></td><td>${prix:,.2f}</td></tr>
      <tr><td><b>Stop-Loss (SL)</b></td><td>${sl:,.2f}</td></tr>
      <tr><td><b>Take-Profit (TP)</b></td><td>${tp:,.2f}</td></tr>
      <tr style="background-color: #f2f2f2;">
        <td><b>Taille de position suggérée</b></td>
        <td><b>${pos_usd:,.2f}</b></td>
      </tr>
      <tr style="background-color: #ffe6e6;">
        <td><b>Risque ($)</b></td>
        <td><b>${risque_usd:,.2f}</b></td>
      </tr>
    </table>
    <p><small>Message automatisé de ton scanner Streamlit Cloud.</small></p>
    """

    try:
        resend.Emails.send({
            "from": "Scanner Crypto <onboarding@resend.dev>",
            "to": [to_email],
            "subject": f"[{signal_type}] {symbol} - Taille position : ${pos_usd:,.0f}",
            "html": contenu_html
        })
        return True
    except Exception as e:
        st.error(f"Erreur d'envoi mail : {e}")
        return False

# --- EXÉCUTION DU SCANNER ---

if st.button("🚀 Lancer le balayage du marché"):
    resultats = []
    
    for symbol in symboles_choisis:
        try:
            df = charger_donnees(symbol, timeframe)
            df = calculer_indicateurs(df)
            signal, prix, sl, tp, atr = analyser_signal(df)
            
            if signal in ["ACHAT", "VENTE"]:
                pos_usd, risque_usd = calculer_taille_position(capital_total, risque_pct, prix, sl)
                
                # Envoi de l'alerte mail
                mail_envoye = envoyer_email_alerte(symbol, signal, prix, sl, tp, pos_usd, risque_usd)
                
                resultats.append({
                    "Paire": symbol,
                    "Signal": signal,
                    "Prix ($)": f"${prix:,.2f}",
                    "Stop-Loss ($)": f"${sl:,.2f}",
                    "Take-Profit ($)": f"${tp:,.2f}",
                    "Position ($)": f"${pos_usd:,.2f}",
                    "Risque ($)": f"${risque_usd:,.2f}",
                    "Email": "Envoyé 📧" if mail_envoye else "Échec ❌"
                })

                # Affichage graphique pour les paires avec signal
                st.subheader(f"📊 Graphique : {symbol} ({signal})")
                fig = go.Figure(data=[go.Candlestick(
                    x=df['timestamp'],
                    open=df['open'], high=df['high'],
                    low=df['low'], close=df['close'],
                    name="Prix"
                )])
                fig.add_hline(y=sl, line_dash="dash", line_color="red", annotation_text="Stop-Loss")
                fig.add_hline(y=tp, line_dash="dash", line_color="green", annotation_text="Take-Profit")
                fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=400)
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"Erreur lors de l'analyse de {symbol} : {e}")

    # Résumé des signaux
    if resultats:
        st.success(f"Détéction terminée : {len(resultats)} signal(s) trouvé(s) !")
        st.table(pd.DataFrame(resultats))
    else:
        st.info("Aucun signal fort détecté sur le marché actuellement.")

