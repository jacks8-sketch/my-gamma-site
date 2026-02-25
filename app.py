import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="NDX Gamma Pro", layout="wide")

st.title("📊 NDX Gamma & Volatility Dashboard")

# 1. Fetch NDX Data
ndx = yf.Ticker("^NDX")
try:
    # Use a broader period to ensure we get data
    hist = ndx.history(period="2d")
    spot = hist['Close'].iloc[-1]
    
    # 2. Get Options Data
    expiry = ndx.options[0] 
    chain = ndx.option_chain(expiry)
    calls, puts = chain.calls, chain.puts

    # 3. Enhanced Calculation (Gamma & Theta)
    calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
    puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    # 4. Big Chart on Top
    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', 
                 title=f"NDX Gamma Profile (Exp: {expiry})",
                 labels={'strike': 'Strike Price', 'GEX': 'Gamma Exposure'},
                 color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

    st.write("---")

    # 5. Probability Logic
    closest_call_wall = calls.nlargest(1, 'GEX')['strike'].iloc[0]
    avg_theta = abs(calls['theta'].mean()) if 'theta' in calls.columns else 0
    dist = abs(spot - closest_call_wall) / spot
    
    # Probability heuristic
    rev_prob = round(max(10, min(90, (dist * 1000) + 15)), 2)
    break_prob = 100 - rev_prob

    # 6. Top Metrics & Probability
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_a:
        st.metric("NDX Spot", f"{spot:,.2f}")
    with col_b:
        st.write(f"**Break Probability:** {break_prob}% | **Reversal Probability:** {rev_prob}%")
        st.progress(break_prob / 100)
    with col_c:
        st.metric("Theta (Time Decay)", f"{avg_theta:.2f}")

    st.write("---")

    # 7. Key Strike Levels
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

except Exception as e:
    st.info("Market is likely closed or data is refreshing. Try again in a few minutes.")
