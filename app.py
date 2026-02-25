import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time
from datetime import datetime, timezone

st.set_page_config(page_title="NDX Gamma Pro", layout="wide")
st.title("📊 NDX High-Accuracy Gamma Dashboard")

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

# 1. Advanced Probability Engine
def calculate_advanced_reversal(strike, spot, calls, puts):
    # Distance Factor
    diff = abs(spot - strike)
    
    # Time (Theta) Factor - Calculate minutes until NY Close (21:00 UTC)
    now = datetime.now(timezone.utc)
    close_time = now.replace(hour=21, minute=0, second=0, microsecond=0)
    minutes_to_close = max(1, (close_time - now).total_seconds() / 60)
    
    # Theta Intensity: Higher as day ends (max 2.0 multiplier)
    theta_boost = max(1.0, 2.0 - (minutes_to_close / 390)) 
    
    # Relative Strength (OI Cluster)
    total_oi = calls['openInterest'].sum() + puts['openInterest'].sum()
    strike_oi = calls[calls['strike'] == strike]['openInterest'].sum() + puts[puts['strike'] == strike]['openInterest'].sum()
    oi_weight = (strike_oi / (total_oi / len(calls))) * 0.5 # Relative to average
    
    # Reversal Logic: Target 50pt NQ bounce
    if diff < 10: # Inside the 'Break' danger zone
        base_prob = 15 + (diff * 2)
    elif diff <= 60: # The 50pt Reversal Sweet Spot
        base_prob = 40 + (diff * 0.8) + (oi_weight * 10)
    else: # Distant walls
        base_prob = 75 + (diff / 20)

    final_prob = min(98, base_prob * theta_boost)
    return round(final_prob, 2)

spot, expiry, calls, puts = get_data()

if spot:
    # Gamma/GEX Logic
    if 'gamma' not in calls.columns or calls['gamma'].isnull().all():
        calls['GEX'] = calls['openInterest'] * 0.1
        puts['GEX'] = puts['openInterest'] * -0.1
        st.info("Using OI Density weighting.")
    else:
        calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
        puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    # Main Chart
    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', title=f"NDX Gamma Profile: {expiry}", color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🎯 Sniper Entry Levels (50pt NQ Target)")
    c1, c2, c3 = st.columns(3)
    
    # Get top clusters
    top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
    top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)

    with c1:
        st.write("### 🟢 Resistance Walls")
        for s in top_c['strike'][:3]:
            prob = calculate_advanced_reversal(s, spot, calls, puts)
            st.success(f"Strike {s:,.0f} | **{prob}% Rev**")
    with c2:
        st.write("### 🟡 Pivot Clusters")
        for s in top_c['strike'][3:6]:
            prob = calculate_advanced_reversal(s, spot, calls, puts)
            st.warning(f"Strike {s:,.0f} | **{prob}% Rev**")
    with c3:
        st.write("### 🔴 Support Walls")
        for s in top_p['strike'][:3]:
            prob = calculate_advanced_reversal(s, spot, calls, puts)
            st.error(f"Strike {s:,.0f} | **{prob}% Rev**")
else:
    st.warning("Refreshing Data...")
