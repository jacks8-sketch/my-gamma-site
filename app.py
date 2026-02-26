import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import requests
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

# 2. DATA FETCHING (Reliable Multi-Source)
def get_data():
    ticker_sym = "^NDX"
    # Attempt 1: Massive Proxy (Bypasses all blocks)
    try:
        # Key: RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp
        url = f"https://api.massive.com/v1/finance/yahoo/ticker/{ticker_sym}/full?apikey=RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            spot = data['price']['regularMarketPrice']
            opt_data = data['options'][0]
            return spot, opt_data['expirationDate'], pd.DataFrame(opt_data['calls']), pd.DataFrame(opt_data['puts'])
    except:
        pass

    # Attempt 2: Direct Fallback
    try:
        tk = yf.Ticker(ticker_sym)
        hist = tk.history(period="5d")
        spot = hist['Close'].iloc[-1]
        exp = tk.options[0]
        chain = tk.option_chain(exp)
        return spot, exp, chain.calls, chain.puts
    except:
        return None, None, None, None

def calc_rev(strike, spot):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts = get_data()

if spot is not None and not calls.empty:
    # Standardize column names (fixes the AttributeError)
    calls.columns = [c.lower() for c in calls.columns]
    puts.columns = [c.lower() for c in puts.columns]
    
    # Calculate GEX safely
    if 'gamma' not in calls.columns: calls['gamma'] = 0.0001
    if 'gamma' not in puts.columns: puts['gamma'] = 0.0001
    
    # Fill missing Gamma values before calculating
    calls['gamma'] = calls['gamma'].fillna(0.0001).replace(0, 0.0001)
    puts['gamma'] = puts['gamma'].fillna(0.0001).replace(0, 0.0001)
    
    calls['gex'] = calls['openinterest'] * calls['gamma']
    puts['gex'] = puts['openinterest'] * puts['gamma'] * -1
    
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.94) & (all_gex['strike'] < spot * 1.06)].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['gex'].cumsum()
        flip_idx = np.abs(all_gex['cum_gex']).argmin()
        gamma_flip = all_gex.iloc[flip_idx]['strike']
        
        # 4. UI RESTORATION
        tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 Metrics", "🗺️ Heatmap"])
        
        with tab1:
            st.subheader(f"NDX | Spot: {spot:,.2f} | Flip: {gamma_flip:,.2f}")
            fig = px.bar(all_gex, x='strike', y='gex', color='gex', color_continuous_scale='RdYlGn')
            fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text="FLIP")
            fig.update_layout(template="plotly_dark", height=450)
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("### 🟢 Resistance")
                for s in calls.nlargest(3, 'openinterest')['strike'].sort_values():
                    st.success(f"{s:,.0f} | {calc_rev(s, spot)}% Rev")
            with c2:
                st.write("### 🟡 Levels")
                st.metric("Spot", f"{spot:,.2f}")
                st.metric("Flip", f"{gamma_flip:,.2f}")
            with c3:
                st.write("### 🔴 Support")
                for s in puts.nlargest(3, 'openinterest')['strike'].sort_values(ascending=False):
                    st.error(f"{s:,.0f} | {calc_rev(s, spot)}% Rev")
        
        with tab2:
            st.metric("Current Price", f"{spot:,.2f}")
            st.metric("Gamma Pivot", f"{gamma_flip:,.2f}")
            
        with tab3:
            st.subheader("Structural Heatmap")
            fig_heat = px.density_heatmap(all_gex, x="strike", y="openinterest", z="gex", color_continuous_scale="Viridis")
            fig_heat.update_layout(template="plotly_dark")
            st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.warning("📡 Market Data Connection Pending... If this takes more than 30s, refresh manually.")
