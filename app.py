import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
import requests
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
st_autorefresh(interval=60000, key="datarefresh")
st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

# Custom CSS for better metric visibility
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8vw !important; }
    [data-testid="stMetricLabel"] { font-size: 1.0vw !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    </style>
    """, unsafe_allow_html=True)

# 2. DATA FETCHING (Using QQQ and Browser Emulation)
def get_data():
    try:
        # Ticker QQQ is more reliable than ^NDX for free API data
        ticker_sym = "QQQ" 
        
        # Emulate a real browser session to prevent Yahoo from blocking the app
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        })
        
        ndx = yf.Ticker(ticker_sym, session=session)
        hist_long = ndx.history(period="60d")
        
        if hist_long.empty:
            return None, None, None, None, None, None
        
        spot = hist_long['Close'].iloc[-1]
        
        # Historical Volatility
        hist_long['returns'] = hist_long['Close'].pct_change()
        hv = hist_long['returns'].tail(20).std() * np.sqrt(252) * 100
        
        # Low Volume Nodes (LVN)
        price_bins = pd.cut(hist_long['Close'], bins=50)
        node_counts = price_bins.value_counts()
        lvns = [bin.mid for bin, count in node_counts.items() if count <= node_counts.quantile(0.2)]
        
        # Options Data
        expiry = ndx.options[0]
        chain = ndx.option_chain(expiry)
        calls, puts = chain.calls, chain.puts
        
        return spot, expiry, calls, puts, hv, lvns
    except Exception as e:
        return None, None, None, None, None, None

def calc_rev(strike, spot, lvns, skew, is_support):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    if any(abs(strike - lvn) < 30 for lvn in lvns):
        base += 10
    # Adjust based on skew
    if is_support and skew > 2.0: base -= 10
    elif not is_support and skew > 2.0: base += 5
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hv, lvns = get_data()

if spot is not None and not calls.empty:
    # GEX Calculation (using 0.1 as a default gamma if missing)
    calls['GEX'] = calls['openInterest'] * calls.get('gamma', 0.1)
    puts['GEX'] = puts['openInterest'] * puts.get('gamma', 0.1) * -1
    
    # Range Filtering (5% around spot for clarity)
    active_range = (spot * 0.95, spot * 1.05)
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > active_range[0]) & (all_gex['strike'] < active_range[1])].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        flip_idx = np.abs(all_gex['cum_gex']).argmin()
        gamma_flip = all_gex.iloc[flip_idx]['strike']
        
        # Sentiment/Skew Logic
        atm_c = calls.iloc[(calls['strike'] - spot).abs().argmin()]
        atm_p = puts.iloc[(puts['strike'] - spot).abs().argmin()]
        avg_iv = (atm_c['impliedVolatility'] + atm_p['impliedVolatility']) / 2 * 100
        skew = (atm_p['impliedVolatility'] - atm_c['impliedVolatility']) * 100
        
        regime = "🛡️ COMPLACENT" if avg_iv < hv - 2 else "⚡ VOLATILE" if avg_iv > hv + 2 else "⚖️ NEUTRAL"
        bias = "🔴 BEARISH" if skew > 2.0 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"

        # 4. TABS & UI
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap", "📖 Trade Manual"])

        with tab1:
            st.subheader(f"QQQ Analysis (NDX Proxy) | Price: ${spot:,.2f}")
            fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn', title="Net Gamma Exposure per Strike")
            fig_gamma.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text=f"FLIP: {gamma_flip:,.0f}")
            fig_gamma.update_layout(template="plotly_dark", height=450)
            st.plotly_chart(fig_gamma, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("### 🟢 Resistance")
                for s in calls.nlargest(3, 'openInterest')['strike'].sort_values():
                    st.success(f"Strike {s:,.0f} | **{calc_rev(s, spot, lvns, skew, False)}% Rev**")
            with c2:
                st.write("### 🟡 Key Levels")
                st.metric("Spot Price", f"${spot:,.2f}")
                st.metric("Gamma Flip", f"${gamma_flip:,.2f}")
            with c3:
                st.write("### 🔴 Support")
                for s in puts.nlargest(3, 'openInterest')['strike'].sort_values(ascending=False):
                    st.error(f"Strike {s:,.0f} | **{calc_rev(s, spot, lvns, skew, True)}% Rev**")

        with tab2:
            st.subheader("Market Sentiment & Volatility")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Daily Bias", bias)
            col_b.metric("Volatility Regime", regime)
            col_c.metric("Put/Call Skew", f"{skew:.2f}%")
            
            fig_vol = px.bar(x=['Implied Vol (IV)', 'Historical Vol (HV)'], y=[avg_iv, hv], color=['IV', 'HV'], title="Volatility Comparison")
            fig_vol.update_layout(template="plotly_dark", showlegend=False)
            st.plotly_chart(fig_vol, use_container_width=True)

        with tab3:
            st.subheader("Structural Liquidity Heatmap")
            h_data = all_gex.copy()
            h_data['Type'] = np.where(h_data['GEX'] > 0, 'Calls', 'Puts')
            fig_heat = px.density_heatmap(h_data, x="strike", y="Type", z="openInterest", color_continuous_scale="Viridis", nbinsx=30)
            fig_heat.update_layout(template="plotly_dark", height=500)
            st.plotly_chart(fig_heat, use_container_width=True)

        with tab4:
            st.header("🎯 Trade Execution Guide")
            st.info("1. Locate the **Gamma Flip** (Orange Dash). Price below the flip is 'Short Gamma' (High Volatility).")
            st.info("2. Look for **Reversal Probability** percentages at major Open Interest strikes.")
            st.info("3. Check **Daily Bias**—if Bearish, treat resistance strikes as high-probability short entries.")

    else:
        st.error("Options data filtered out. Try again in a few minutes.")
else:
    st.warning("⚠️ Still no data. Yahoo is blocking the server connection. Please wait 10 seconds and refresh.")
