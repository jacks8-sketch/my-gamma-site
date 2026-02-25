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

# UPDATED: 50-Point Reversal Sensitivity
def get_strike_probs(strike, current_price):
    diff = abs(current_price - strike)
    
    if diff <= 5: # Directly on the level - high risk of "slipping" through
        return 15.0
    elif diff <= 50: # Inside your 50-point target zone
        # As it gets closer to 50pts away, probability of a bounce increases
        return round(20 + (diff * 1.2), 2) 
    else: # Outside the immediate danger zone
        return round(min(95, 70 + (diff / 10)), 2)

if spot:
    if 'gamma' not in calls.columns or calls['gamma'].isnull().all():
        calls['GEX'] = calls['openInterest'] * calls['strike'] * 0.001
        puts['GEX'] = puts['openInterest'] * puts['strike'] * -0.001
        st.info("Note: Using Open Interest Proxy.")
    else:
        calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
        puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', 
                 title=f"NDX Gamma Profile (Exp: {expiry})",
                 labels={'strike': 'Strike Price', 'GEX': 'Exposure Strength'},
                 color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig, use_container_width=True)

    col_a, col_b = st.columns([1, 3])
    with col_a:
        st.metric("NDX Spot", f"{spot:,.2f}")
    with col_b:
        st.info(f"💡 REVERSAL %: Likelihood of a 50+ point bounce at this level.")

    st.write("---")

    st.subheader("🎯 Key Strike Levels & 50pt Reversal Odds")
    col1, col2, col3 = st.columns(3)
    
    top_c = calls.nlargest(6, 'GEX').sort_values('strike')
    top_p = puts.nsmallest(6, 'GEX').sort_values('strike', ascending=False)

    with col1:
        st.write("### 🟢 Call Walls")
        for val in top_c['strike'][:3]:
            rp = get_strike_probs(val, spot)
            st.success(f"Strike {val:,.0f} | **{rp}% Reversal**")
    with col2:
        st.write("### 🟡 Mid-Range")
        for val in top_c['strike'][3:6]:
            rp = get_strike_probs(val, spot)
            st.warning(f"Strike {val:,.0f} | **{rp}% Reversal**")
    with col3:
        st.write("### 🔴 Put Walls")
        for val in top_p['strike'][:3]:
            rp = get_strike_probs(val, spot)
            st.error(f"Strike {val:,.0f} | **{rp}% Reversal**")
else:
    st.warning("Data is currently refreshing. Please wait a moment.")
