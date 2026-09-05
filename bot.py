import os
import pandas as pd
import numpy as np
import ccxt
import resend

# --- PARAMÈTRES DU BOT ---
CAPITAL_TOTAL = 1000.0  # Ton capital par défaut ($)
RISQUE_PCT = 1.0        # Pourcentage de risque par trade (1%)
SYMBOLES = ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "ADA/USD"]
TIMEFRAME = "1h"

# --- FONCTIONS TECHNIQUES ---

def charger_donnees(symbol, timeframe, limit=100):
    exchange = ccxt.coinbase()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculer_indicateurs(df):
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
    df['Bollinger_Lower'] = df['SMA20'] - (df['STD20'] * 2)
    df['Bollinger_Upper'] = df['SMA20'] + (df['STD20'] * 2)

    # ATR (14)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    return df

def analyser_signal(df):
    derniere_ligne = df.iloc[-1]
    rsi = derniere_ligne['RSI']
    macd = derniere_ligne['MACD']
    signal_macd = derniere_ligne['Signal_MACD']
    close = derniere_ligne['close']
    bollinger_lower = derniere_ligne['Bollinger_Lower']
    bollinger_upper = derniere_ligne['Bollinger_Upper']
    atr = derniere_ligne['ATR']

    signal = "NEUTRE"

    if rsi < 40 and macd > signal_macd and close <= bollinger_lower * 1.01:
        signal = "ACHAT"
        sl = close - (1.5 * atr)
        tp = close + (3.0 * atr)
    elif rsi > 60 and macd < signal_macd and close >= bollinger_upper * 0.99:
        signal = "VENTE"
        sl = close + (1.5 * atr)
        tp = close - (3.0 * atr)
    else:
        sl, tp = 0.0, 0.0

    return signal, close, sl, tp

def calculer_taille_position(capital, risque_pct, prix_entree, stop_loss):
    distance_sl_pct = abs(prix_entree - stop_loss) / prix_entree
    if distance_sl_pct == 0:
        return 0.0, 0.0
    montant_risque_usd = capital * (risque_pct / 100.0)
    position_usd = montant_risque_usd / distance_sl_pct
    return round(position_usd, 2), round(montant_risque_usd, 2)

def envoyer_email_alerte(symbol, signal_type, prix, sl, tp, pos_usd, risque_usd):
    api_key = os.getenv("RESEND_API_KEY")
    to_email = os.getenv("TO_EMAIL")

    if not api_key or not to_email:
        print("⚠️ Variables d'environnement RESEND_API_KEY ou TO_EMAIL manquantes.")
        return

    resend.api_key = api_key

    contenu_html = f"""
    <h2>🚨 Signal Crypto Automatique : {signal_type} sur {symbol}</h2>
    <p>Alerte détectée lors du scan horaire automatique.</p>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
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
    """

    resend.Emails.send({
        "from": "Scanner Crypto <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"[{signal_type}] {symbol} - Taille position : ${pos_usd:,.0f}",
        "html": contenu_html
    })
    print(f"📧 Email envoyé pour {symbol} !")

# --- EXECUTION ---
if __name__ == "__main__":
    print("🔍 Lancement du scanner automatique GitHub Actions...")
    for symbol in SYMBOLES:
        try:
            df = charger_donnees(symbol, TIMEFRAME)
            df = calculer_indicateurs(df)
            signal, prix, sl, tp = analyser_signal(df)
            
            if signal in ["ACHAT", "VENTE"]:
                print(f"🎯 Signal {signal} trouvé sur {symbol} !")
                pos_usd, risque_usd = calculer_taille_position(CAPITAL_TOTAL, RISQUE_PCT, prix, sl)
                envoyer_email_alerte(symbol, signal, prix, sl, tp, pos_usd, risque_usd)
            else:
                print(f"⚪ {symbol} : Aucun signal.")
        except Exception as e:
            print(f"❌ Erreur sur {symbol} : {e}")

