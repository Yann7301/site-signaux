import os
import json
import requests
import pandas as pd
import numpy as np
import resend

# Liste des 30 cryptos YouHolder
YOUHOLDER_TOP_30 = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
    "LTCUSDT", "BCHUSDT", "UNIUSDT", "ATOMUSDT", "XLMUSDT",
    "ETCUSDT", "NEARUSDT", "ALGOUSDT", "ICPUSDT", "FILUSDT",
    "APTUSDT", "OPUSDT", "ARBUSDT", "LDOUSDT", "INJUSDT",
    "TIAUSDT", "SUIUSDT", "RNDRUSDT", "PEPEUSDT", "DOGEUSDT"
]

CONFIG_FILE = "config.json"

default_config = {
    "timeframe": "1h",
    "capital_initial": 1000.0,
    "risque_pct": 1.0,
    "type_sl_tp": "Pourcentage Fixe",
    "stop_loss_pct": 2.0,
    "take_profit_pct": 4.0,
    "atr_period": 14,
    "atr_mult_sl": 1.5,
    "atr_mult_tp": 3.0
}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        print(f"⚙️ Configuration chargée depuis {CONFIG_FILE}")
    except Exception as e:
        print(f"⚠️ Erreur de lecture de {CONFIG_FILE}, utilisation de la config par défaut: {e}")
        config = default_config
else:
    config = default_config

TIMEFRAME = config.get("timeframe", "1h")
CAPITAL = config.get("capital_initial", 1000.0)
RISQUE_PCT = config.get("risque_pct", 1.0)
TYPE_SL_TP = config.get("type_sl_tp", "Pourcentage Fixe")

def get_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except Exception:
        return pd.DataFrame()

def analyze_all_market():
    signals_detected = []
    montant_risque = CAPITAL * (RISQUE_PCT / 100)

    print(f"🔍 Démarrage du scan global sur {len(YOUHOLDER_TOP_30)} cryptos ({TIMEFRAME})...")

    for symbol in YOUHOLDER_TOP_30:
        df = get_klines(symbol, TIMEFRAME)
        if df.empty or len(df) < 30:
            continue

        # RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # ATR
        atr_period = config.get("atr_period", 14)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(atr_period).mean()

        current_price = df['close'].iloc[-1]
        current_rsi = df['RSI'].iloc[-1]
        current_atr = df['ATR'].iloc[-1]

        # Calcul TP/SL
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

        sl_dist = current_price - sl_price
        position_size_crypto = montant_risque / sl_dist if sl_dist > 0 else 0
        position_size_usd = position_size_crypto * current_price

        signal = None
        if current_rsi < 30:
            signal = "ACHAT (Survendu)"
        elif current_rsi > 70:
            signal = "VENTE (Suracheté)"

        if signal:
            signals_detected.append({
                "symbol": symbol,
                "signal": signal,
                "price": current_price,
                "rsi": current_rsi,
                "tp": tp_price,
                "sl": sl_price,
                "pos_usd": position_size_usd,
                "risk_usd": montant_risque
            })

    print(f"📊 Scan terminé : {len(signals_detected)} signal(aux) trouvé(s).")

    if signals_detected:
        send_summary_email(signals_detected)

def send_summary_email(signals):
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("TO_EMAIL")

    if not api_key or not to_email:
        print("❌ Secrets RESEND_API_KEY ou TO_EMAIL manquants.")
        return

    resend.api_key = api_key

    rows_html = ""
    for item in signals:
        rows_html += f"""
        <tr>
            <td style="padding:8px; border:1px solid #ddd;"><b>{item['symbol']}</b></td>
            <td style="padding:8px; border:1px solid #ddd;">{item['signal']}</td>
            <td style="padding:8px; border:1px solid #ddd;">${item['price']:,.4f}</td>
            <td style="padding:8px; border:1px solid #ddd;">${item['tp']:,.4f}</td>
            <td style="padding:8px; border:1px solid #ddd;">${item['sl']:,.4f}</td>
            <td style="padding:8px; border:1px solid #ddd;">${item['pos_usd']:,.2f}</td>
        </tr>
        """

    html_content = f"""
    <h2>🚨 SIGNAUX TRADING YOUHOLDER ({TIMEFRAME})</h2>
    <p>Le scan automatique a détecté des opportunités avec vos règles configurées :</p>
    <table style="border-collapse:collapse; width:100%;">
        <thead>
            <tr style="background-color:#f2f2f2;">
                <th style="padding:8px; border:1px solid #ddd;">Crypto</th>
                <th style="padding:8px; border:1px solid #ddd;">Signal</th>
                <th style="padding:8px; border:1px solid #ddd;">Prix</th>
                <th style="padding:8px; border:1px solid #ddd;">TP</th>
                <th style="padding:8px; border:1px solid #ddd;">SL</th>
                <th style="padding:8px; border:1px solid #ddd;">Taille Position</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    """

    try:
        resend.Emails.send({
            "from": "Scanner YouHolder <onboarding@resend.dev>",
            "to": [to_email],
            "subject": f"🤖 {len(signals)} SIGNAL(AUX) YOUHOLDER DÉTECTÉ(S)",
            "html": html_content
        })
        print("📧 Email récapitulatif envoyé avec succès !")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")

if __name__ == "__main__":
    analyze_all_market()

