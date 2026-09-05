import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

PAIRS_TOP_30 = [
    "BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", 
    "DOT-USD", "LINK-USD", "LTC-USD", "BCH-USD", "UNI-USD", 
    "ATOM-USD", "XLM-USD", "ETC-USD", "NEAR-USD", "ALGO-USD", 
    "ICP-USD", "FIL-USD", "APT-USD", "OP-USD", "ARB-USD", 
    "LDO-USD", "INJ-USD", "TIA-USD", "SUI-USD", "RENDER-USD", 
    "PEPE-USD", "DOGE-USD", "FET-USD", "AAVE-USD", "SHIB-USD"
]

def load_config():
    default_config = {
        "timeframe": "15m",
        "capital_initial": 1000.0,
        "type_sl_tp": "Pourcentage Fixe",
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3.0,
        "rsi_period": 14,
        "rsi_oversold": 40,
        "rsi_overbought": 60,
        "atr_period": 14,
        "atr_mult_sl": 1.5,
        "atr_mult_tp": 3.0
    }
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default_config

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

    signals_found = 0

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
            signals_found += 1
            print(f"🟢 [ACHAT] {symbol} | Prix: ${price:,.4f} | RSI: {rsi:.1f} | TP: ${tp_price:,.4f} | SL: ${sl_price:,.4f}")
        elif rsi > config["rsi_overbought"]:
            signals_found += 1
            print(f"🔴 [VENTE] {symbol} | Prix: ${price:,.4f} | RSI: {rsi:.1f} | TP: ${tp_price:,.4f} | SL: ${sl_price:,.4f}")

    if signals_found == 0:
        print("💤 Aucun signal détecté sur ce cycle.")

    print(f"\n✅ Analyse terminée.")

if __name__ == "__main__":
    run_bot()

