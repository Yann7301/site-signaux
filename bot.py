import pandas as pd
import numpy as np
import requests
import json
import time
import os

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier de configuration : {e}")

    return {
        "timeframe": "1h",
        "capital_initial": 100.0,
        "risque_pct": 1.0,
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
        "telegram_token": "",
        "telegram_chat_id": ""
    }

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

def calculate_indicators(df, config):
    if len(df) < 200:
        return df

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=config.get("rsi_period", 14)).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=config.get("rsi_period", 14)).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(config.get("atr_period", 14)).mean()

    df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

    return df

def send_telegram(signals, config):
    token = config.get("telegram_token") or os.getenv("TELEGRAM_TOKEN")
    chat_id = config.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Paramètres Telegram manquants (TOKEN ou CHAT_ID). Envoi ignoré.")
        return

    tf = config.get('timeframe', '1h')
    cap = config.get('capital_initial', 100.0)
    message = f"🚨 *ALERTES SCANNER CRYPTO (Top 100)* ({len(signals)})\n"
    message += f"⏱ *Timeframe :* `{tf}` | *Capital :* `${cap}`\n"
    message += "-----------------------------------\n\n"

    for s in signals:
        entry_price = s['Prix d_entree']
        crypto = s['Crypto']
        sig = s['Signal']
        rsi_val = s['RSI']
        ema_val = s['EMA 200']
        tend = s['Tendance']
        tp = s['Take Profit']
        sl = s['Stop Loss']

        message += f"🪙 *{crypto}* | {sig}\n"
        message += f"💵 *Prix d'entrée :* `{entry_price}`\n"
        message += f"📊 *RSI :* `{rsi_val}` | *EMA 200 :* `{ema_val}` ({tend})\n"
        message += f"🎯 *Take Profit :* `{tp}`\n"
        message += f"🛑 *Stop Loss :* `{sl}`\n"
        message += "-----------------------------------\n"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("Message Telegram envoyé avec succès !")
        else:
            print(f"Erreur Telegram ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"Erreur lors de l'envoi du message Telegram : {e}")

def main():
    config = load_config()
    print(f"Lancement du scan Top 100... Timeframe: {config['timeframe']} | Filtre EMA 200: {config.get('use_ema_filter', True)}")

    buy_signals = []
    sell_signals = []
    use_ema_filter = config.get("use_ema_filter", True)

    for symbol in PAIRS_TOP_100:
        df = fetch_data(symbol, config["timeframe"])
        if not df.empty and len(df) >= 200:
            df = calculate_indicators(df, config)

            price = df['close'].iloc[-1]
            rsi = df['RSI'].iloc[-1]
            atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0
            ema200 = df['EMA200'].iloc[-1]

            if not pd.isna(rsi) and not pd.isna(ema200):
                trend = "🟢 Haussière" if price > ema200 else "🔴 Baissière"

                is_buy = rsi < config.get("rsi_oversold", 30) and (not use_ema_filter or price > ema200)
                is_sell = rsi > config.get("rsi_overbought", 70) and (not use_ema_filter or price < ema200)

                if is_buy:
                    if config["type_sl_tp"] == "Pourcentage Fixe":
                        sl_price = price * (1 - config["stop_loss_pct"] / 100)
                        tp_price = price * (1 + config["take_profit_pct"] / 100)
                    else:
                        sl_price = price - (atr * config["atr_mult_sl"])
                        tp_price = price + (atr * config["atr_mult_tp"])

                    buy_signals.append({
                        "Crypto": symbol,
                        "Signal": "🟢 ACHAT",
                        "Prix d_entree": f"${price:,.4f}",
                        "RSI_val": rsi,
                        "RSI": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Tendance": trend,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

                elif is_sell:
                    if config["type_sl_tp"] == "Pourcentage Fixe":
                        sl_price = price * (1 + config["stop_loss_pct"] / 100)
                        tp_price = price * (1 - config["take_profit_pct"] / 100)
                    else:
                        sl_price = price + (atr * config["atr_mult_sl"])
                        tp_price = price - (atr * config["atr_mult_tp"])

                    sell_signals.append({
                        "Crypto": symbol,
                        "Signal": "🔴 VENTE",
                        "Prix d_entree": f"${price:,.4f}",
                        "RSI_val": rsi,
                        "RSI": round(rsi, 1),
                        "EMA 200": f"${ema200:,.4f}",
                        "Tendance": trend,
                        "Take Profit": f"${tp_price:,.4f}",
                        "Stop Loss": f"${sl_price:,.4f}"
                    })

        time.sleep(0.12)

    # Tri par RSI croissant (du plus petit au plus grand)
    buy_signals = sorted(buy_signals, key=lambda x: x["RSI_val"])
    sell_signals = sorted(sell_signals, key=lambda x: x["RSI_val"])

    all_signals = buy_signals + sell_signals

    if all_signals:
        print(f"{len(all_signals)} signal/signaux trouvé(s) ({len(buy_signals)} Achat, {len(sell_signals)} Vente). Envoi sur Telegram...")
        send_telegram(all_signals, config)
    else:
        print("Scan terminé. Aucun signal ne respecte les conditions actuelles.")

if __name__ == "__main__":
    main()

