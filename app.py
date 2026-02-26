import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import requests
from streamlit_autorefresh import st_autorefresh

# 1. SETUP & THEME
st_autorefresh(interval=60000, key="datarefresh")
st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8vw !important; }
    [data-testid="stMetricLabel"] { font-size: 1.0vw !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. DATA FETCHING (Using your Massive API Key)
def get_data():
    try:
        # Using your provided key to bypass all Yahoo blocks
        MASSIVE_KEY = "RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp"
        
        # We fetch via Massive's Yahoo Finance proxy
        url = f"https://api.massive.com/v1/finance/yahoo/ticker/^NDX/full?apikey={MASSIVE_KEY}"
        response = requests.get(url).json()
        
        # Extract Spot Price & History
        spot = response['price']['regularMarketPrice']
        hv = response['stats'].get('historicalVolatility', 18.5) # Fallback to 18.5 if missing
        
        # Extract Options Data
        opt_data = response['options'][0] # Front month
        expiry = opt_data['expirationDate']
        
        calls = pd.DataFrame(opt_data['calls'])
        puts = pd.DataFrame(opt_data['puts'])
        
        return spot, expiry, calls, puts, hv
    except Exception as e:
        # Log error to sidebar for debugging
        st.sidebar.error(f"Fetch Error: {e}")
        return None, None, None, None, None

def calc_rev(strike, spot, hv):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hv = get_data()

if spot is not None and not calls.empty:
    # Ensure Gamma exists (fallback to proxy if Yahoo sends 0)
    calls['gamma'] = calls['gamma'].fillna(0.0001).replace(0, 0.0001)
    puts['gamma'] = puts['gamma'].fillna(0.0001).replace(0, 0.0001)
    
    calls['GEX'] = calls['openInterest'] * calls['gamma']
    puts['GEX'] = puts['openInterest'] * puts['gamma'] * -1
    
    # Filter for the NDX Trading Range
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.94) & (all_gex['strike'] < spot * 1.06)].sort_values('strike')
    
    if not all_gex.empty:
        # Calculations
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        flip_idx = np.abs(all_gex['cum_gex']).argmin()
        gamma_flip = all_gex.iloc[flip_idx]['strike']
        
        # IV / Bias Logic
        atm_c_iv = calls.iloc[(calls['strike'] - spot).abs().argmin()]['impliedVolatility'] * 100
        atm_p_iv = puts.iloc[(puts['strike'] - spot).abs().argmin()]['impliedVolatility'] * 100
        avg_iv = (atm_c_iv + atm_p_iv) / 2
        skew = atm_p_iv - atm_c_iv
        
        regime = "🛡️ COMPLACENT" if avg_iv < hv - 2 else "⚡ VOLATILE" if avg_iv > hv + 2 else "⚖️ NEUTRAL"
        bias = "🔴 BEARISH" if skew > 1.5 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"

        # 4. UI RESTORATION (The Original Tabs)
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap", "📖 Trade Manual"])

        with tab1:
            st.subheader(f"NDX Sniper Profile | Spot: {spot:,.2f}")
            fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            fig_gamma.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text=f"FLIP: {gamma_flip:,.0f}")
            fig_gamma.update_layout(template="plotly_dark", height=420)
            st.plotly_chart(fig_gamma, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("### 🟢 Resistance")
                for s in calls.nlargest(3, 'openInterest').sort_values('strike')['strike']:
                    st.success(f"{s:,.0f} | **{calc_rev(s, spot, hv)}% Rev**")
            with c2:
                st.write("### 🟡 Levels")
                st.metric("Price", f"{spot:,.2f}")
                st.metric("Flip", f"{gamma_flip:,.2f}")
            with c3:
                st.write("### 🔴 Support")
                for s in puts.nlargest(3, 'openInterest').sort_values('strike', ascending=False)['strike']:
                    st.error(f"{s:,.0f} | **{calc_rev(s, spot, hv)}% Rev**")

        with tab2:
            st.subheader("Volatility Analysis")
            m1, m2, m3 = st.columns(3)
            m1.metric("Daily Bias", bias)
            m2.metric("Regime", regime)
            m3.metric("Skew", f"{skew:.2f}")
            st.plotly_chart(px.bar(x=['IV', 'HV'], y=[avg_iv, hv], color=['IV', 'HV'], template="plotly_dark"), use_container_width=True)

        with tab3:
            st.subheader("Structural Heatmap")
            h_data = all_gex.copy()
            h_data['Type'] = np.where(h_data['GEX'] > 0, 'Calls', 'Puts')
            fig_heat = px.density_heatmap(h_data, x="strike", y="Type", z="openInterest", color_continuous_scale="Viridis", nbinsx=40)
            fig_heat.update_layout(template="plotly_dark", height=500)
            st.plotly_chart(fig_heat, use_container_width=True)

        with tab4:
            st.header("🎯 Trade Manual")
            st.write("1. If Price > Flip, market is in 'Positive Gamma' (Stable).")
            st.write("2. High 'Rev %' at major OI strikes indicates likely price exhaustion.")

    else:
        st.error("Massive connected, but NDX data range is narrow. Refreshing...")
else:
    st.info("📡 Connecting to Massive Data Stream... Please wait 15 seconds.")
