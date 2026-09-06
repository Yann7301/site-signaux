import pandas as pd
import numpy as np
import requests
import json
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CHARGEMENT DE LA CONFIGURATION ---
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier de configuration : {e}")
    
    # Valeurs par défaut si le fichier n'existe pas
    return {
        "timeframe": "1h",
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

PAIRS_TOP_30 = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD",
    "DOT-USD", "LINK-USD", "LTC-USD", "BCH-USD", "UNI-USD",
    "ATOM-USD", "XLM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD",
    "ICP-USD", "FIL-USD", "APT-USD", "OP-USD", "ARB-USD",
    "LDO-USD", "INJ-USD", "TIA-USD", "SUI-USD", "RENDER-USD",
    "PEPE-USD", "DOGE-USD", "FET-USD", "AAVE-USD", "SHIB-USD"
]

# --- RECUPERATION DES DONNEES ---
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
        print(f"Erreur d'extraction pour {symbol} : {e}")
    return pd.DataFrame()

# --- CALCUL DES INDICATEURS (RSI, ATR, EMA 200) ---
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

# --- ENVOI DE L'EMAIL ---
def send_email(signals, config):
    sender = config.get("email_sender") or os.getenv("EMAIL_SENDER")
    password = config.get("email_password") or os.getenv("EMAIL_PASSWORD")
    receiver = config.get("email_receiver") or os.getenv("EMAIL_RECEIVER")
    smtp_server = config.get("smtp_server", "smtp.gmail.com")
    smtp_port = config.get("smtp_port", 587)

    if not sender or not password or not receiver:
        print("Paramètres e-mail manquants. Envoi ignoré.")
        return

    msg = MIMEMultipart("alternative")
    msg['Subject'] = f"🚨 Alertes Trading Crypto ({len(signals)} opportunité(s))"
    msg['From'] = sender
    msg['To'] = receiver

    html_content = f"""
    <html>
      <body>
        <h2>Alerte Scanner Crypto (Timeframe: {config.get('timeframe', '1h')})</h2>
        <p>Voici les opportunités détectées selon la tendance EMA 200 :</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
          <tr style="background-color: #f2f2f2;">
            <th>Crypto</th>
            <th>Signal</th>
            <th>Prix d'Entrée</th>
            <th>RSI</th>
            <th>EMA 200</th>
            <th>Tendance</th>
            <th>Take Profit</th>
            <th>Stop Loss</th>
          </tr>
    """

    for s in signals:
        html_content += f"""
          <tr>
            <td><b>{s['Crypto']}</b></td>
            <td>{s['Signal']}</td>
            <td>{s['Prix d\'entrée']}</td>
            <td>{s['RSI']}</td>
            <td>{s['EMA 200']}</td>
            <td>{s['Tendance']}</td>
            <td style="color: green;">{s['Take Profit']}</td>
            <td style="color: red;">{s['Stop Loss']}</td>
          </tr>
        """

    html_content += """
        </table>
      </body>
    </html>
    """

    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print("E-mail envoyé avec succès !")
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'e-mail : {e}")

# --- EXECUTION PRINCIPALE ---
def main():
    config = load_config()
    print(f"Lancement du scan... Timeframe: {config['timeframe']} | Filtre EMA 200: {config.get('use_ema_filter', True)}")
    
    signals = []
    use_ema_filter = config.get("use_ema_filter", True)

    for symbol in PAIRS_TOP_30:
        df = fetch_data(symbol, config["timeframe"])
        if not df.empty and len(df) >= 200:
            df = calculate_indicators(df, config)

            price = df['close'].iloc[-1]
            rsi = df['RSI'].iloc[-1]
            atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0
            ema200 = df['EMA200'].iloc[-1]

            if not pd.isna(rsi) and not pd.isna(ema200):
                if config["type_sl_tp"] == "Pourcentage Fixe":
                    sl_price = price * (1 - config["stop_loss_pct"] / 100)
                    tp_price = price * (1 + config["take_profit_pct"] / 100)
                else:
                    sl_price = price - (atr * config["atr_mult_sl"])
                    tp_price = price + (atr * config["atr_mult_tp"])

                trend = "🟢 Haussière" if price > ema200 else "🔴 Baissière"

                is_buy = rsi < config["rsi_oversold"] and (not use_ema_filter or price > ema200)
                is_sell = rsi > config["rsi_overbought"] and (not use_ema_filter or price < ema200)

                if is_buy:
                    signals.append({
                        "Crypto": symbol,
                        "Signal": "🟢 ACHAT",
                        "Prix d'entrée": f"${price:,.4f}",
                        "RSI": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Tendance": trend,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })
                elif is_sell:
                    signals.append({
                        "Crypto": symbol,
                        "Signal": "🔴 VENTE",
                        "Prix d'entrée": f"${price:,.4f}",
                        "RSI": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Tendance": trend,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

    if signals:
        print(f"{len(signals)} signal/signaux trouvé(s). Envoi du rapport...")
        send_email(signals, config)
    else:
        print("Scan terminé. Aucun signal ne respecte les conditions actuelles.")

if __name__ == "__main__":
    main()

