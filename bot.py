import json
import os
import numpy as np
import pandas as pd
import resend
import requests

# --- 1. CHARGEMENT CONFIGURATION ---
CONFIG_FILE = "config.json"

default_config = {
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "capital_initial": 1000.0,
    "risque_pct": 1.0,
    "type_sl_tp": "Pourcentage Fixe",
    "stop_loss_pct": 2.0,
    "take_profit_pct": 4.0,
    "atr_period": 14,
    "atr_mult_sl": 1.5,
    "atr_mult_tp": 3.0,
}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        print(f"⚙️ Configuration chargée depuis {CONFIG_FILE}")
    except Exception as e:
        print(
            f"⚠️ Erreur de lecture de {CONFIG_FILE}, utilisation de la config par défaut: {e}"
        )
        config = default_config
else:
    print("ℹ️ Aucun config.json trouvé, utilisation des paramètres par défaut.")
    config = default_config

SYMBOL = config.get("symbol", "BTCUSDT")
TIMEFRAME = config.get("timeframe", "1h")
CAPITAL = config.get("capital_initial", 1000.0)
RISQUE_PCT = config.get("risque_pct", 1.0)
TYPE_SL_TP = config.get("type_sl_tp", "Pourcentage Fixe")


# --- 2. RÉCUPÉRATION DONNÉES BINANCE ---
def get_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    data = response.json()

    df = pd.DataFrame(
        data,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "qav",
            "num_trades",
            "taker_base_vol",
            "taker_quote_vol",
            "ignore",
        ],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


# --- 3. ANALYSE ET ENVOI DE SIGNAL ---
def analyze_market():
    df = get_klines(SYMBOL, TIMEFRAME)
    if df.empty:
        print("❌ Aucune donnée récupérée.")
        return

    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # ATR
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr_period = config.get("atr_period", 14)
    df["ATR"] = true_range.rolling(atr_period).mean()

    current_price = df["close"].iloc[-1]
    current_rsi = df["RSI"].iloc[-1]
    current_atr = df["ATR"].iloc[-1]

    if TYPE_SL_TP == "Pourcentage Fixe":
        sl_pct = config.get("stop_loss_pct", 2.0)
        tp_pct = config.get("take_profit_pct", 4.0)
        sl_price = current_price * (1 - sl_pct / 100)
        tp_price = current_price * (1 + tp_pct / 100)
    else:
        mult_sl = config.get("atr_mult_sl", 1.5)
        mult_tp = config.get("atr_mult_tp", 3.0)
        sl_price = current_price - (current_atr * mult_sl)
        tp_price = current_price + (current_atr * mult_tp)

    montant_risque = CAPITAL * (RISQUE_PCT / 100)
    sl_dist = current_price - sl_price
    position_size_crypto = montant_risque / sl_dist if sl_dist > 0 else 0
    position_size_usd = position_size_crypto * current_price

    signal = None
    if current_rsi < 30:
        signal = "ACHAT (Survendu)"
    elif current_rsi > 70:
        signal = "VENTE (Suraheté)"

    print(
        f"📊 Analyse YouHolder {SYMBOL} ({TIMEFRAME}) | Prix: ${current_price:,.4f} | RSI: {current_rsi:.1f}"
    )

    if signal:
        send_email_alert(
            signal,
            current_price,
            tp_price,
            sl_price,
            position_size_usd,
            montant_risque,
        )
    else:
        print("⏸️ Aucun signal sur cet intervalle.")


def send_email_alert(signal, price, tp, sl, pos_usd, risk_usd):
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("TO_EMAIL")

    if not api_key or not to_email:
        print("❌ Variables d'environnement RESEND manquantes.")
        return

    resend.api_key = api_key

    html_content = f"""
    <h2>🚨 ALERTE SIGNAL YOUHOLDER : {SYMBOL}</h2>
    <p><b>Signal :</b> {signal}</p>
    <p><b>Unité de temps :</b> {TIMEFRAME}</p>
    <p><b>Prix d'entrée :</b> ${price:,.4f}</p>
    <hr>
    <h3>🎯 Plan de Trade</h3>
    <p><b>Take Profit (TP) :</b> ${tp:,.4f}</p>
    <p><b>Stop Loss (SL) :</b> ${sl:,.4f}</p>
    <p><b>Taille de Position :</b> ${pos_usd:,.2f} (Risque engagé : ${risk_usd:,.2f})</p>
    """

    try:
        resend.Emails.send(
            {
                "from": "Bot YouHolder <onboarding@resend.dev>",
                "to": [to_email],
                "subject": f"🤖 SIGNAL YOUHOLDER {SYMBOL} - {signal}",
                "html": html_content,
            }
        )
        print("📧 Email d'alerte envoyé !")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")


if __name__ == "__main__":
    analyze_market()

