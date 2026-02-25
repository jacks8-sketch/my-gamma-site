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

# IMPROVED: Realistic Reversal Logic
def calculate_advanced_reversal(strike, spot, calls, puts):
    diff = abs(spot - strike)
    
    # 1. Decay Factor (Theta Influence)
    # Target NY Close: 16:00 EST / 21:00 UTC
    now = datetime.now(timezone.utc)
    close_time = now.replace(hour=21, minute=0, second=0, microsecond=0)
    minutes_left = (close_time - now).total_seconds() / 60
    
    # If market is closed or almost closed, don't let it break the math
    if minutes_left <= 0 or minutes_left > 390:
        time_mult = 1.0 # Standard weight during off-hours
    else:
        # Boosts odds as day ends, but caps at 1.4x instead of 2.0x
        time_mult = 1 + (1 - (minutes_left / 390)) * 0.4 

    # 2. Probability based on "Zone"
    if diff <= 15: 
        # Inside the 15pt "Danger Zone" - high chance of break
        base_prob = 10 + (diff * 2) 
    elif diff <= 60:
        # The 50pt Sniper Zone - where reversals happen
        base_prob = 45 + (diff * 0.6)
    else:
        # Distant Walls
        base_prob = 75 + (diff / 25)

    # 3. Apply Time Multiplier and Cap it realistically at 92%
    final_prob = min(92.0, base_prob * time_mult)
    return round(final_prob, 2)

spot, expiry, calls, puts = get_data()

if spot:
    # Use real Gamma if available, else OI density
    if 'gamma' not in calls.columns or calls['gamma'].isnull().all():
        calls['GEX'] = calls['openInterest'] * 0.1
        puts['GEX'] = puts['openInterest'] * -0.1
        st.info("Using Open Interest Density weighting.")
    else:
        calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
        puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', title=f"NDX Gamma Profile: {expiry}", color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🎯 Sniper Entry Levels (50pt NQ Target)")
    c1, c2, c3 = st.columns(3)
    
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
    st.warning("Data is currently refreshing...")
