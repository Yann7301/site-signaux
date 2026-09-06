import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

PAIRS_TOP_30 = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD",
    "DOT-USD", "LINK-USD", "LTC-USD", "BCH-USD", "UNI-USD",
    "ATOM-USD", "XLM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD",
    "ICP-USD", "FIL-USD", "APT-USD", "OP-USD", "ARB-USD",
    "LDO-USD", "INJ-USD", "TIA-USD", "SUI-USD", "RENDER-USD",
    "PEPE-USD", "DOGE-USD", "FET-USD", "AAVE-USD", "SHIB-USD"
]

# --- CHARGEMENT DE LA CONFIGURATION ---
def load_config():
    # Lecture prioritaire des variables d'environnement (GitHub Actions)
    email_sender = os.getenv("EMAIL_SENDER")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_receiver = os.getenv("EMAIL_RECEIVER")

    config = {}
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        pass

    return {
        "timeframe": config.get("timeframe", "1h"),
        "capital_initial": config.get("capital_initial", 1000.0),
        "type_sl_tp": config.get("type_sl_tp", "Pourcentage Fixe"),
        "stop_loss_pct": config.get("stop_loss_pct", 1.5),
        "take_profit_pct": config.get("take_profit_pct", 3.0),
        "rsi_period": config.get("rsi_period", 14),
        "rsi_oversold": config.get("rsi_oversold", 30),
        "rsi_overbought": config.get("rsi_overbought", 70),
        "atr_period": config.get("atr_period", 14),
        "atr_mult_sl": config.get("atr_mult_sl", 1.5),
        "atr_mult_tp": config.get("atr_mult_tp", 3.0),
        "email_sender": email_sender or config.get("email_sender", ""),
        "email_password": email_password or config.get("email_password", ""),
        "email_receiver": email_receiver or config.get("email_receiver", ""),
        "smtp_server": config.get("smtp_server", "smtp.gmail.com"),
        "smtp_port": config.get("smtp_port", 587)
    }

# --- FONCTION D'ENVOI D'E-MAIL ---
def send_email(subject, body, config):
    sender = config.get("email_sender")
    password = config.get("email_password")
    receiver = config.get("email_receiver")
    smtp_server = config.get("smtp_server", "smtp.gmail.com")
    smtp_port = config.get("smtp_port", 587)

    if not sender or not password:
        print("⚠️ Configuration e-mail incomplète. Alerte non envoyée.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = receiver
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        # Suppression des espaces éventuels dans le mot de passe d'application
        clean_password = password.replace(" ", "")
        server.login(sender, clean_password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print("✉️ E-mail d'alerte envoyé avec succès !")
    except Exception as e:
        print(f"❌ Échec de l'envoi de l'e-mail : {e}")

def fetch_data(symbol, interval):
    granularity_map = {
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400
    }
    granularity = granularity_map.get(interval, 900)
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
        print(f"❌ Erreur lors de la récupération de {symbol} : {e}")

    return pd.DataFrame()

def calculate_indicators(df, config):
    if len(df) < config["rsi_period"]:
        return df

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=config["rsi_period"]).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=config["rsi_period"]).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(config["atr_period"]).mean()

    return df

def run_bot():
    config = load_config()
    print(f"🚀 Bot démarré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 Analyse Coinbase en cours sur 30 cryptos ({config['timeframe']})...\n")

    detected_signals = []

    for symbol in PAIRS_TOP_30:
        df = fetch_data(symbol, config["timeframe"])
        time.sleep(0.1)  # Petite pause pour respecter les requêtes Coinbase

        if df.empty or len(df) < config["rsi_period"]:
            continue

        df = calculate_indicators(df, config)

        price = df['close'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0

        if pd.isna(rsi):
            continue

        if config["type_sl_tp"] == "Pourcentage Fixe":
            sl_price = price * (1 - config["stop_loss_pct"] / 100)
            tp_price = price * (1 + config["take_profit_pct"] / 100)
        else:
            sl_price = price - (atr * config["atr_mult_sl"])
            tp_price = price + (atr * config["atr_mult_tp"])

        if rsi < config["rsi_oversold"]:
            msg = f"🟢 [ACHAT] {symbol} | Prix: ${price:,.4f} | RSI: {rsi:.1f} | TP: ${tp_price:,.4f} | SL: ${sl_price:,.4f}"
            print(msg)
            detected_signals.append(msg)
        elif rsi > config["rsi_overbought"]:
            msg = f"🔴 [VENTE] {symbol} | Prix: ${price:,.4f} | RSI: {rsi:.1f} | TP: ${tp_price:,.4f} | SL: ${sl_price:,.4f}"
            print(msg)
            detected_signals.append(msg)

    # --- ENVOI DES RETOURS ---
    if detected_signals:
        print(f"\n📢 {len(detected_signals)} signal(s) trouvé(s). Envoi de l'e-mail...")
        email_subject = f"🚨 {len(detected_signals)} Signal(s) Trading Détecté(s)"
        email_body = f"Bonjour,\n\nVoici les signaux détectés le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} :\n\n"
        email_body += "\n".join(detected_signals)
        email_body += "\n\nBon trading !"

        send_email(email_subject, email_body, config)
    else:
        print("\n💤 Aucun signal détecté sur ce cycle. Aucun e-mail envoyé.")


if __name__ == "__main__":
    run_bot()

