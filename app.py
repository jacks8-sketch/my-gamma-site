import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
from datetime import datetime, timezone

st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3):
        try:
            # Get 60d to ensure we have enough for HV and IV history
            hist = ndx.history(period="60d")
            if hist.empty: continue
            spot = hist['Close'].iloc[-1]
            
            # Historical Volatility (20-day)
            hist['returns'] = hist['Close'].pct_change()
            hv = hist['returns'].tail(20).std() * np.sqrt(252) * 100
            
            expiries = ndx.options
            if not expiries: continue
            chain = ndx.option_chain(expiries[0])
            return spot, expiries[0], chain.calls, chain.puts, hv, hist
        except:
            time.sleep(1)
    return None, None, None, None, None, None

spot, expiry, calls, puts, hv, hist = get_data()

def get_bias(calls, puts, spot, hv):
    atm_call_iv = calls.iloc[(calls['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    atm_put_iv = puts.iloc[(puts['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    avg_iv = (atm_call_iv + atm_put_iv) / 2
    skew = atm_put_iv - atm_call_iv
    
    if avg_iv > hv + 2: regime = "⚡ VOLATILE (Trend Likely)"
    elif avg_iv < hv - 2: regime = "🛡️ COMPLACENT (Mean Reversion)"
    else: regime = "⚖️ NEUTRAL"
        
    if skew > 2.0: bias = "🔴 BEARISH (Fear)"
    elif skew < -0.5: bias = "🟢 BULLISH (Demand)"
    else: bias = "🟡 NEUTRAL / CHOP"
        
    return bias, regime, avg_iv, skew

if spot:
    bias, regime, iv, skew = get_bias(
    
