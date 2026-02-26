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

# 2. DATA FETCHING (Massive API Fix)
def get_data():
    try:
        # Using your key: RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp
        MASSIVE_KEY = "RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp"
        
        # Massive often prefers 'NDX' without the '^' for their Yahoo proxy
        url = f"https://api.massive.com/v1/finance/yahoo/ticker/NDX/full?apikey={MASSIVE_KEY}"
        response = requests.get(url)
        
        # Check if the response is actually JSON
        if response.status_code != 200:
            st.sidebar.error(f"API Access Denied: {response.status_code}")
            return None, None, None, None, None

        data = response.json()
        
        # Extract Spot Price & History
        # We navigate the JSON tree based on Massive's typical structure
        spot = data.get('price', {}).get('regularMarketPrice')
        stats = data.get('stats', {})
        hv = stats.get('historicalVolatility', 18.5)
        
        # Extract Options Data
        options_list = data.get('options', [])
        if not options_list:
            return None, None, None, None, None
            
        opt_data = options_list[0] # Monthly expiry
        expiry = opt_data.get('expirationDate')
        
        calls = pd.DataFrame(opt_data.get('calls', []))
        puts = pd.DataFrame(opt_data.get('puts', []))
        
        return spot, expiry, calls, puts, hv
    except Exception as e:
        st.sidebar.error(f"Data Error: {str(e)}")
        return None, None, None, None, None

def calc_rev(strike, spot, hv):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hv = get_data()

if spot is not None and not calls.empty:
    # Ensure Gamma exists (fallback to 0.1 proxy if missing)
    calls['gamma'] = calls.get('gamma', 0.1).fillna(0.1)
    puts['gamma'] = puts.get('gamma', 0.1).fillna(0.1)
    
    calls['GEX'] = calls['openInterest'] * calls['gamma']
    puts['GEX'] = puts['openInterest'] * puts['gamma'] * -1
    
    # Filter for the NDX Trading Range
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.94) & (all_gex['strike'] < spot * 1.06)].sort_values('strike')
    
    if not all_gex.empty:
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

        # 4. TABS
        tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap"])

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
            m1, m2 = st.columns(2)
            m1.metric("Daily Bias", bias)
            m2.metric("Regime", regime)
            st.plotly_chart(px.bar(x=['IV', 'HV'], y=[avg_iv, hv], color=['IV', 'HV'], template="plotly_dark"), use_container_width=True)

        with tab3:
            st.subheader("Structural Heatmap")
            h_data = all_gex.copy()
            h_data['Type'] = np.where(h_data['GEX'] > 0, 'Calls', 'Puts')
            fig_heat = px.density_heatmap(h_data, x="strike", y="Type", z="openInterest", color_continuous_scale="Viridis")
            st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.error("Data range too narrow. Check back in a moment.")
else:
    st.info("📡 Data source is resetting... Please wait 15 seconds.")
