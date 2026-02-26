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

# 2. DATA FETCHING (Restoring ^NDX with stealth headers)
def get_data():
    try:
        ticker_sym = "^NDX" 
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0 Safari/537.36'})
        
        ndx = yf.Ticker(ticker_sym, session=session)
        # Fast history fetch
        hist = ndx.history(period="60d")
        if hist.empty: return None, None, None, None, None, None
        
        spot = hist['Close'].iloc[-1]
        hist['returns'] = hist['Close'].pct_change()
        hv = hist['returns'].tail(20).std() * np.sqrt(252) * 100
        
        # Options Data
        expiry = ndx.options[0]
        chain = ndx.option_chain(expiry)
        calls, puts = chain.calls, chain.puts
        
        return spot, expiry, calls, puts, hv, []
    except:
        return None, None, None, None, None, None

def calc_rev(strike, spot, hv):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hv, lvns = get_data()

if spot is not None and not calls.empty:
    # --- GAMMA FALLBACK LOGIC ---
    # If Yahoo Gamma is 0/NaN, we use a proxy (OI * distance) so charts aren't empty
    calls['gamma_clean'] = calls['gamma'].fillna(0.0001).replace(0, 0.0001)
    puts['gamma_clean'] = puts['gamma'].fillna(0.0001).replace(0, 0.0001)
    
    calls['GEX'] = calls['openInterest'] * calls['gamma_clean']
    puts['GEX'] = puts['openInterest'] * puts['gamma_clean'] * -1
    
    all_gex = pd.concat([calls, puts])
    # Active trading range
    all_gex = all_gex[(all_gex['strike'] > spot * 0.92) & (all_gex['strike'] < spot * 1.08)].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        flip_idx = np.abs(all_gex['cum_gex']).argmin()
        gamma_flip = all_gex.iloc[flip_idx]['strike']
        
        # Sentiment Metrics
        atm_c = calls.iloc[(calls['strike'] - spot).abs().argmin()]
        atm_p = puts.iloc[(puts['strike'] - spot).abs().argmin()]
        avg_iv = (atm_c['impliedVolatility'] + atm_p['impliedVolatility']) / 2 * 100
        skew = (atm_p['impliedVolatility'] - atm_c['impliedVolatility']) * 100
        
        regime = "🛡️ COMPLACENT" if avg_iv < hv - 2 else "⚡ VOLATILE" if avg_iv > hv + 2 else "⚖️ NEUTRAL"
        bias = "🔴 BEARISH" if skew > 2.0 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"

        # 4. TABS RESTORATION (Exactly like yesterday)
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap", "📖 Trade Manual"])

        with tab1:
            st.subheader(f"NDX Sniper Profile | Spot: {spot:,.2f}")
            fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            fig_gamma.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text=f"FLIP: {gamma_flip:,.0f}")
            fig_gamma.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_gamma, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
            top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)

            with c1:
                st.write("### 🟢 Resistance")
                for s in top_c['strike'][:3]:
                    st.success(f"{s:,.0f} | **{calc_rev(s, spot, hv)}% Rev**")
            with c2:
                st.write("### 🟡 Mid-Range")
                st.metric("Current Spot", f"{spot:,.2f}")
                st.metric("Gamma Flip", f"{gamma_flip:,.2f}")
            with c3:
                st.write("### 🔴 Support")
                for s in top_p['strike'][:3]:
                    st.error(f"{s:,.0f} | **{calc_rev(s, spot, hv)}% Rev**")

        with tab2:
            st.subheader("Market Sentiment & Volatility")
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Daily Bias", bias)
            col_m2.metric("Regime", regime)
            col_m3.metric("Put Skew", f"{skew:.2f}")
            st.plotly_chart(px.bar(x=['IV', 'HV'], y=[avg_iv, hv], color=['IV', 'HV'], template="plotly_dark"), use_container_width=True)

        with tab3:
            st.subheader("Structural Liquidity Map")
            h_data = all_gex.copy()
            h_data['Type'] = np.where(h_data['GEX'] > 0, 'Calls', 'Puts')
            fig_heat = px.density_heatmap(h_data, x="strike", y="Type", z="openInterest", color_continuous_scale="Viridis", nbinsx=50)
            fig_heat.update_layout(template="plotly_dark", height=500)
            st.plotly_chart(fig_heat, use_container_width=True)

        with tab4:
            st.header("🎯 Trade Strategy")
            st.write("Monitor the orange Gamma Flip line. If spot is above, the market is 'Stable'. Below is 'Volatile'.")

    else:
        st.error("Data filtered out. Ticker might be throttled.")
else:
    st.warning("⚠️ Yahoo Finance is currently limiting requests. Retrying in 60s...")
