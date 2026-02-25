import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time

st.set_page_config(page_title="NDX Gamma Pro", layout="wide")
st.title("📊 NDX Gamma & Volatility Dashboard")

ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3):
        try:
            hist = ndx.history(period="2d")
            if hist.empty: continue
            spot = hist['Close'].iloc[-1]
            expiries = ndx.options
            if not expiries: continue
            chain = ndx.option_chain(expiries[0])
            return spot, expiries[0], chain.calls, chain.puts
        except:
            time.sleep(1)
    return None, None, None, None

spot, expiry, calls, puts = get_data()

if spot:
    # --- SAFETY FIX: Check if Gamma exists, if not, create a proxy ---
    if 'gamma' not in calls.columns or calls['gamma'].isnull().all():
        # Proxy Gamma: Use Open Interest as the weight
        calls['GEX'] = calls['openInterest'] * calls['strike'] * 0.001
        puts['GEX'] = puts['openInterest'] * puts['strike'] * -0.001
        st.info("Note: Using Open Interest Proxy (Real Gamma data currently unavailable from source).")
    else:
        calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
        puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    # 3. Big Chart on Top
    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', 
                 title=f"NDX Gamma Profile (Exp: {expiry})",
                 labels={'strike': 'Strike Price', 'GEX': 'Exposure Strength'},
                 color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly
