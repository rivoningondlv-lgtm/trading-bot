import os
import requests
import pandas as pd
import yfinance as yf

# --- CONFIGURATION (Pulling securely from GitHub Secrets) ---
SYMBOL = "GC=F"  # Gold Futures
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_alert(message):
  """Sends a notification message to your Telegram chat."""
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("[Error] Telegram credentials missing from environment variables!")
    return

  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
  try:
    response = requests.post(url, json=payload)
    if response.status_code == 200:
      print("[Telegram] Notification sent successfully!")
    else:
      print(f"[Telegram Error]: {response.text}")
  except Exception as e:
    print(f"[Telegram Exception]: {e}")


def fetch_market_data():
  """Fetches 1-Hour trend data and 15-minute execution data."""
  print("Fetching live Gold data...")
  df_1h = yf.Ticker(SYMBOL).history(period="5d", interval="60m")
  df_15m = yf.Ticker(SYMBOL).history(period="5d", interval="15m")
  return df_1h, df_15m


def check_trend_filter(df_1h):
  """Determines 1-Hour trend using 50 EMA."""
  df_1h["EMA50"] = df_1h["Close"].ewm(span=50, adjust=False).mean()
  last_close = df_1h["Close"].iloc[-1]
  last_ema = df_1h["EMA50"].iloc[-1]
  return "BULLISH" if last_close > last_ema else "BEARISH"


def calculate_support_resistance(df_15m):
  """Calculates recent Key Support & Resistance (Pivot Highs/Lows)."""
  recent_resistance = df_15m["High"].tail(20).max()
  recent_support = df_15m["Low"].tail(20).min()
  return recent_support, recent_resistance


def detect_crt_sweep(df_15m):
  """CRT Sweep: Price sweeps high/low of prior range and closes back inside."""
  prev_range_high = df_15m["High"].iloc[-3]
  prev_range_low = df_15m["Low"].iloc[-3]

  curr_high = df_15m["High"].iloc[-2]
  curr_low = df_15m["Low"].iloc[-2]
  curr_close = df_15m["Close"].iloc[-2]

  bullish_crt = (curr_low < prev_range_low) and (curr_close > prev_range_low)
  bearish_crt = (curr_high > prev_range_high) and (curr_close < prev_range_high)

  return {"bullish_crt": bullish_crt, "bearish_crt": bearish_crt}


def detect_candlestick_patterns(df):
  """Identifies Engulfing, Doji, Morning Star, and Evening Star patterns."""
  c3, c2, c1 = df.iloc[-4], df.iloc[-3], df.iloc[-2]

  body1 = abs(c1["Close"] - c1["Open"])
  range1 = c1["High"] - c1["Low"]

  is_doji = (body1 <= range1 * 0.1) if range1 > 0 else False

  is_bullish_engulfing = (
      (c2["Close"] < c2["Open"])
      and (c1["Close"] > c1["Open"])
      and (c1["Close"] >= c2["Open"])
  )
  is_bearish_engulfing = (
      (c2["Close"] > c2["Open"])
      and (c1["Close"] < c1["Open"])
      and (c1["Close"] <= c2["Open"])
  )

  is_morning_star = (
      (c3["Close"] < c3["Open"])
      and (abs(c2["Close"] - c2["Open"]) < abs(c3["Close"] - c3["Open"]) * 0.5)
      and (c1["Close"] > c1["Open"])
      and (c1["Close"] > (c3["Open"] + c3["Close"]) / 2)
  )

  is_evening_star = (
      (c3["Close"] > c3["Open"])
      and (abs(c2["Close"] - c2["Open"]) < abs(c3["Close"] - c3["Open"]) * 0.5)
      and (c1["Close"] < c1["Open"])
      and (c1["Close"] < (c3["Open"] + c3["Close"]) / 2)
  )

  return {
      "doji": is_doji,
      "bullish_engulfing": is_bullish_engulfing,
      "bearish_engulfing": is_bearish_engulfing,
      "morning_star": is_morning_star,
      "evening_star": is_evening_star,
  }


def detect_fvg(df):
  """Detects Fair Value Gaps (FVG)."""
  c1_high, c3_low = df["High"].iloc[-3], df["Low"].iloc[-1]
  c1_low, c3_high = df["Low"].iloc[-3], df["High"].iloc[-1]

  return {
      "bullish_fvg": c3_low > c1_high,
      "bearish_fvg": c1_low > c3_high,
  }


def run_bot():
  print("--- SCANNING MARKET ---")
  df_1h, df_15m = fetch_market_data()

  trend = check_trend_filter(df_1h)
  support, resistance = calculate_support_resistance(df_15m)
  crt = detect_crt_sweep(df_15m)
  patterns = detect_candlestick_patterns(df_15m)
  fvgs = detect_fvg(df_15m)

  price = df_15m["Close"].iloc[-1]
  print(
      f"Current Gold Price: ${price:.2f} | 1H Trend: {trend} | Support:"
      f" ${support:.2f} | Resistance: ${resistance:.2f}"
  )

  bullish_rejection = (
      patterns["bullish_engulfing"]
      or patterns["doji"]
      or patterns["morning_star"]
  )
  bearish_rejection = (
      patterns["bearish_engulfing"]
      or patterns["doji"]
      or patterns["evening_star"]
  )

  if trend == "BULLISH" and (fvgs["bullish_fvg"] or crt["bullish_crt"]) and bullish_rejection:
    msg = f"🚀 *BULLISH BUY SIGNAL*\nPrice: ${price:.2f}\n1H Trend: BULLISH\nSupport: ${support:.2f}\nTrigger: FVG/CRT + Rejection Pattern."
    send_telegram_alert(msg)
  elif trend == "BEARISH" and (fvgs["bearish_fvg"] or crt["bearish_crt"]) and bearish_rejection:
    msg = f"🔻 *BEARISH SELL SIGNAL*\nPrice: ${price:.2f}\n1H Trend: BEARISH\nResistance: ${resistance:.2f}\nTrigger: FVG/CRT + Rejection Pattern."
    send_telegram_alert(msg)
  else:
    print("No setup matched current strict rules on this scan.")


if __name__ == "__main__":
  run_bot()