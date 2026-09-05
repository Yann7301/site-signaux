import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

YOUHOLDER_TOP_30 = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", 
    "DOTUSDT", "LINKUSDT", "POLUSDT", "LTCUSDT", "BCHUSDT", "UNIUSDT", "ATOMUSDT", 
    "XLMUSDT", "ETCUSDT", "NEARUSDT", "ALGOUSDT", "ICPUSDT", "FILUSDT", "APTUSDT", 
    "OPUSDT", "ARBUSDT", "LDOUSDT", "INJUSDT", "TIAUSDT", "SUIUSDT", "RENDERUSDT", 
    "PEPEUSDT", "DOGEUSDT"
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

def fetch_data(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            raw_data = res.json()
            if raw_data:
                df = pd.DataFrame(raw_data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
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
    print(f"🔄 Analyse en cours sur 30 cryptos ({config['timeframe']})...\n")

    signals_found = 0

    for symbol in YOUHOLDER_TOP_30:
        df = fetch_data(symbol, config["timeframe"])

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

