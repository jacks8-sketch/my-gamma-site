import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="NDX Gamma Dashboard", layout="wide")
st.title("🚀 NDX Gamma Walls & Break Probabilities")

# 1. Fetch NDX Data
ndx = yf.Ticker("^NDX")
try:
    spot = ndx.history(period="1d")['Close'].iloc[-1]
    
    # 2. Get Options (Using the nearest expiration)
    expiry = ndx.options[0] 
    chain = ndx.option_chain(expiry)
    calls, puts = chain.calls, chain.puts

    # 3. GEX Calculation (Proxy using Open Interest)
    calls['GEX'] = calls['openInterest'] * calls['strike'] * 0.1
    puts['GEX'] = puts['openInterest'] * puts['strike'] * -0.1

    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    put_wall = puts.loc[puts['GEX'].idxmin(), 'strike']

    # 4. Probability Logic
    dist_to_call = abs(spot - call_wall) / spot
    # If price is far from wall, break prob is low; if near, it increases
    break_prob = round(max(5, min(95, (1 - dist_to_call) * 100)), 2)
    rev_prob = 100 - break_prob

    # 5. Display Dashboard
    col1, col2, col3 = st.columns(3)
    col1.metric("NDX Spot", f"{spot:,.2f}")
    col2.metric("Call Wall (Resistance)", f"{call_wall:,.0f}")
    col3.metric("Put Wall (Support)", f"{put_wall:,.0f}")

    st.write(f"### 📊 Probability Analysis")
    st.write(f"**Chance of Breaking Current Wall:** {break_prob}%")
    st.progress(break_prob / 100)
    st.write(f"**Chance of Reversal/Bounce:** {rev_prob}%")

    # Chart
    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', title="Gamma Levels (0DTE/Nearest Expiry)")
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error("Market data is currently unavailable. Please check back during market hours.")
