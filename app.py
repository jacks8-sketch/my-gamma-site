import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
from streamlit_autorefresh import st_autorefresh

# 1. Setup
st.set_page_config(page_title="NDX Sniper Pro", layout="wide")
st_autorefresh(interval=60000, key="datarefresh")

st.markdown("<style>[data-testid='stMetricValue'] { font-size: 1.8vw !important; }</style>", unsafe_allow_html=True)

# 2. Data Fetching Logic
def get_data():
    try:
        ndx = yf.Ticker("^NDX")
        hist = ndx.history(period="60d")
        if hist.empty: return None, None, None, None, None, None
        
        spot = hist['Close'].iloc[-1]
        hist['returns'] = hist['Close'].pct_change()
        hv = hist['returns'].tail(20).std() * np.sqrt(252) * 100
        
        # Options
        expiry = ndx.options[0]
        chain = ndx.option_chain(expiry)
        calls, puts = chain.calls, chain.puts
        
        return spot, expiry, calls, puts, hv, []
    except Exception as e:
        return None, None, None, None, None, None

# 3. Calculation Helpers
def calc_rev(strike, spot, hv):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 4. Main Execution
spot, expiry, calls, puts, hv, lvns = get_data()

if spot is not None:
    # Process Gamma
    calls['GEX'] = calls['openInterest'] * calls.get('gamma', 0.1)
    puts['GEX'] = puts['openInterest'] * puts.get('gamma', 0.1) * -1
    all_gex = pd.concat([calls, puts]).sort_values('strike')
    
    # Logic Guards
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        flip_idx = np.abs(all_gex['cum_gex']).argmin()
        gamma_flip = all_gex.iloc[flip_idx]['strike']
        
        # Metrics
        atm_c = calls.iloc[(calls['strike'] - spot).abs().argmin()]
        atm_p = puts.iloc[(puts['strike'] - spot).abs().argmin()]
        skew = (atm_p['impliedVolatility'] - atm_c['impliedVolatility']) * 100
        bias = "🔴 BEARISH" if skew > 2.0 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"

        # UI Tabs
        tab1, tab2 = st.tabs(["🎯 Sniper", "📊 Metrics"])
        with tab1:
            st.subheader(f"NDX @ {spot:,.2f} | Flip: {gamma_flip:,.0f}")
            fig = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1: st.metric("Daily Bias", bias)
            with c2: st.metric("HV (20d)", f"{hv:.2f}%")
        with tab2:
            st.write("Strike Analysis")
            st.dataframe(all_gex[['strike', 'GEX', 'openInterest']].tail(10))
    else:
        st.error("Options chain returned empty. API Throttled.")
else:
    st.warning("⚠️ Market Data Unavailable. Check API connection or Ticker symbol.")
