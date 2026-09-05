import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# --- DICTIONNAIRE DE MAPPING (Identique à app.py) ---
YOUHOLDER_MAP = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana", "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple", "ADAUSDT": "cardano", "AVAXUSDT": "avalanche-2", "DOTUSDT": "polkadot",
    "LINKUSDT": "chainlink", "POLUSDT": "polygon-ecosystem-token", "LTCUSDT": "litecoin",
    "BCHUSDT": "bitcoin-cash", "UNIUSDT": "uniswap", "ATOMUSDT": "cosmos", "XLMUSDT": "stellar",
    "ETCUSDT": "ethereum-classic", "NEARUSDT": "near", "ALGOUSDT": "algorand", "ICPUSDT": "internet-computer",
    "FILUSDT": "filecoin", "APTUSDT": "aptos", "OPUSDT": "optimism", "ARBUSDT": "arbitrum",
    "LDOUSDT": "lido-dao", "INJUSDT": "injective-protocol", "TIAUSDT": "celestia", "SUIUSDT": "sui",
    "RENDERUSDT": "render-token", "PEPEUSDT": "pepe", "DOGEUSDT": "dogecoin"
}

# --- CHARGEMENT DE LA CONFIGURATION ---
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
            config = json.load(f)
            print("⚙️ Configuration 'config.json' chargée avec succès.")
            return config
    except FileNotFoundError:
        print("⚠️ 'config.json' introuvable. Utilisation des paramètres par défaut.")
        return default_config

# --- RÉCUPÉRATION DES DONNÉES DE MARCHÉ ---
def fetch_data(symbol, interval):
    coin_id = YOUHOLDER_MAP.get(symbol)
    if not coin_id:
        return pd.DataFrame()

    days_map = {"15m": "1", "1h": "7", "4h": "14", "1d": "30"}
    days = days_map.get(interval, "1")

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            prices = data.get("prices", [])
            if prices:
                df = pd.DataFrame(prices, columns=['timestamp', 'close'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['open'] = df['close'].shift(1).fillna(df['close'])
                df['high'] = df[['open', 'close']].max(axis=1)
                df['low'] = df[['open', 'close']].min(axis=1)
                return df
    except Exception as e:
        print(f"❌ Erreur lors de la récupération de {symbol} : {e}")

    return pd.DataFrame()

# --- CALCUL DES INDICATEURS ---
def calculate_indicators(df, config):
    if len(df) < config["rsi_period"]:
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

    return df

# --- BOUCLE PRINCIPALE DU BOT ---
def run_bot():
    config = load_config()
    print(f"🚀 Bot démarré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 Analyse en cours sur 30 cryptos (Unité de temps : {config['timeframe']})...\n")

    signals_found = 0

    for symbol in YOUHOLDER_MAP.keys():
        df = fetch_data(symbol, config["timeframe"])
        time.sleep(0.2)  # Pause pour éviter d'atteindre les limites de requêtes de l'API

        if df.empty or len(df) < config["rsi_period"]:
            continue

        df = calculate_indicators(df, config)

        price = df['close'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        atr = df['ATR'].iloc[-1] if not pd.isna(df['ATR'].iloc[-1]) else 0

        if pd.isna(rsi):
            continue

        # Calcul SL/TP
        if config["type_sl_tp"] == "Pourcentage Fixe":
            sl_price = price * (1 - config["stop_loss_pct"] / 100)
            tp_price = price * (1 + config["take_profit_pct"] / 100)
        else:
            sl_price = price - (atr * config["atr_mult_sl"])
            tp_price = price + (atr * config["atr_mult_tp"])

        # Analyse des opportunités
        if rsi < config["rsi_oversold"]:
            signals_found += 1
            print(f"🟢 [ACHAT] {symbol} | Prix: ${price:,.4f} | RSI: {rsi:.1f} | TP: ${tp_price:,.4f} | SL: ${sl_price:,.4f}")
        elif rsi > config["rsi_overbought"]:
            signals_found += 1
            print(f"🔴 [VENTE] {symbol} | Prix: ${price:,.4f} | RSI: {rsi:.1f} | TP: ${tp_price:,.4f} | SL: ${sl_price:,.4f}")

    if signals_found == 0:
        print("💤 Aucun signal détecté sur ce cycle.")

    print(f"\n✅ Analyse terminée. Prochain scan dans 15 minutes.")

if __name__ == "__main__":
    run_bot()

