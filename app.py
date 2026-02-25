import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import time

st.set_page_config(page_title="NDX Gamma Pro", layout="wide")
st.title("📊 NDX Gamma & Volatility Dashboard")

# 1. Fetch NDX Data with a retry loop
ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3): # Try 3 times
        try:
            hist = ndx.history(period="2d")
            if hist.empty: continue
            spot = hist['Close'].iloc[-1]
            
            # Get the very first available expiration
            expiries = ndx.options
            if not expiries: continue
            
            chain = ndx.option_chain(expiries[0])
            return spot, expiries[0], chain.calls, chain.puts
        except:
            time.sleep(1) # Wait a second before retrying
    return None, None, None, None

spot, expiry, calls, puts = get_data()

if spot:
    # 2. Enhanced Calculation (Gamma & Theta)
    calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
    puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    # 3. Big Chart on Top
    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', 
                 title=f"NDX Gamma Profile (Exp: {expiry})",
                 labels={'strike': 'Strike Price', 'GEX': 'Gamma Exposure'},
                 color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    st.write("---")

    # 4. Probability Logic
    closest_call_wall = calls.nlargest(1, 'GEX')['strike'].iloc[0]
    avg_theta = abs(calls['theta'].mean()) if 'theta' in calls.columns else 0
    dist = abs(spot - closest_call_wall) / spot
    
    # Probability math
    rev_prob = round(max(10, min(90, (dist * 1000) + 15)), 2)
    break_prob = 100 - rev_prob

    # 5. Top Metrics & Probability
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_a:
        st.metric("NDX Spot", f"{spot:,.2f}")
    with col_b:
        st.write(f"**Break Probability:** {break_prob}% | **Reversal Probability:** {rev_prob}%")
        st.progress(break_prob / 100)
    with col_c:
        st.metric("Theta (Time Decay)", f"{avg_theta:.2f}")

    st.write("---")

    # 6. Key Strike Levels
    st.subheader("🎯 Key Strike Levels")
    col1, col2, col3 = st.columns(3)
    
    top_c = calls.nlargest(6, 'GEX').sort_values('strike')
    top_p = puts.nsmallest(6, 'GEX').sort_values('strike', ascending=False)

    with col1:
        st.write("### 🟢 Call Walls")
        for val in top_c['strike'][:3]:
            st.success(f"Resistance: {val:,.0f}")
            
    with col2:
        st.write("### 🟡 Mid-Range")
        for val in top_c['strike'][3:6]:
            st.warning(f"Pivot: {val:,.0f}")

    with col3:
        st.write("### 🔴 Put Walls")
        for val in top_p['strike'][:3]:
            st.error(f"Support: {val:,.0f}")
else:
    st.warning("Yahoo Finance is temporarily limiting data. Please refresh the page in a few seconds.")
    if st.button("Force Refresh Data"):
        st.rerun()
