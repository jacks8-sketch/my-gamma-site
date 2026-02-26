import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import requests
import random
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
st_autorefresh(interval=60000, key="datarefresh")
st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8vw !important; }
    [data-testid="stMetricLabel"] { font-size: 1.0vw !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. STEALTH DATA FETCHING
def get_data():
    try:
        ticker_sym = "^NDX"
        
        # We rotate User-Agents to make every request look unique and human
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]
        
        session = requests.Session()
        session.headers.update({'User-Agent': random.choice(user_agents)})
        
        ndx = yf.Ticker(ticker_sym, session=session)
        
        # Get Price
        hist = ndx.history(period="60d")
        if hist.empty:
            return None, None, None, None, None
            
        spot = hist['Close'].iloc[-1]
        hist['returns'] = hist['Close'].pct_change()
        hv = hist['returns'].tail(20).std() * np.sqrt(252) * 100
        
        # Get Options
        expiry = ndx.options[0]
        chain = ndx.option_chain(expiry)
        calls, puts = chain.calls, chain.puts
        
        return spot, expiry, calls, puts, hv
    except Exception as e:
        st.sidebar.error(f"Connect Error: {e}")
        return None, None, None, None, None

def calc_rev(strike, spot, hv):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hv = get_data()

if spot is not None and not calls.empty:
    # Handle Gamma (Proxy fallback if Yahoo sends 0)
    calls['gamma_fix'] = calls['gamma'].fillna(0.0001).replace(0, 0.0001)
    puts['gamma_fix'] = puts['gamma'].fillna(0.0001).replace(0, 0.0001)
    
    calls['GEX'] = calls['openInterest'] * calls['gamma_fix']
    puts['GEX'] = puts['openInterest'] * puts['gamma_fix'] * -1
    
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.94) & (all_gex['strike'] < spot * 1.06)].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        gamma_flip = all_gex.iloc[np.abs(all_gex['cum_gex']).argmin()]['strike']
        
        # IV/Bias Logic
        atm_idx = (calls['strike'] - spot).abs().argmin()
        avg_iv = calls.iloc[atm_idx]['impliedVolatility'] * 100
        
        regime = "🛡️ COMPLACENT" if avg_iv < hv - 2 else "⚡ VOLATILE" if avg_iv > hv + 2 else "⚖️ NEUTRAL"
        bias = "🟢 BULLISH" if avg_iv < hv else "🔴 BEARISH"

        # 4. UI RESTORATION
        tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap"])

        with tab1:
            st.subheader(f"NDX Profile | Spot: {spot:,.2f}")
            fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            fig_gamma.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text=f"FLIP: {gamma_flip:,.0f}")
            fig_gamma.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_gamma, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("### 🟢 Resistance")
                for s in calls.nlargest(3, 'openInterest')['strike'].sort_values():
                    st.success(f"{s:,.0f} | **{calc_rev(s, spot, hv)}% Rev**")
            with c2:
                st.write("### 🟡 Levels")
                st.metric("Price", f"{spot:,.2f}")
                st.metric("Flip", f"{gamma_flip:,.2f}")
            with c3:
                st.write("### 🔴 Support")
                for s in puts.nlargest(3, 'openInterest')['strike'].sort_values(ascending=False):
                    st.error(f"{s:,.0f} | **{calc_rev(s, spot, hv)}% Rev**")

        with tab2:
            st.subheader("Market Sentiment")
            st.metric("Daily Bias", bias)
            st.metric("Volatility Regime", regime)
            st.plotly_chart(px.bar(x=['IV', 'HV'], y=[avg_iv, hv], color=['IV', 'HV'], template="plotly_dark"), use_container_width=True)

        with tab3:
            st.subheader("Gamma Heatmap")
            fig_heat = px.density_heatmap(all_gex, x="strike", y="openInterest", z="GEX", color_continuous_scale="Viridis")
            st.plotly_chart(fig_heat, use_container_width=True)

    else:
        st.error("Strikes received but outside trading range. Try refreshing.")
else:
    st.info("📡 The data source is currently busy. Auto-retrying in 60s...")
    if st.button("Manual Refresh"):
        st.rerun()
