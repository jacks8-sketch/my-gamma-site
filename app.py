import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
from streamlit_autorefresh import st_autorefresh

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="datarefresh")

st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8vw !important; }
    [data-testid="stMetricLabel"] { font-size: 1.0vw !important; }
    </style>
    """, unsafe_allow_html=True)

def get_data():
    try:
        ndx = yf.Ticker("^QQQ")
        hist_long = ndx.history(period="60d")
        if hist_long.empty:
            return None, None, None, None, None, None
        
        spot = hist_long['Close'].iloc[-1]
        
        # HV Calculation
        hist_long['returns'] = hist_long['Close'].pct_change()
        hv = hist_long['returns'].tail(20).std() * np.sqrt(252) * 100
        
        # LVN Calculation
        price_bins = pd.cut(hist_long['Close'], bins=50)
        node_counts = price_bins.value_counts()
        lvns = [bin.mid for bin, count in node_counts.items() if count <= node_counts.quantile(0.2)]
        
        # Options Data
        expiry = ndx.options[0]
        chain = ndx.option_chain(expiry)
        calls, puts = chain.calls, chain.puts
        
        # Clean data
        calls = calls[calls['openInterest'] > 5]
        puts = puts[puts['openInterest'] > 5]
        
        return spot, expiry, calls, puts, hv, lvns
    except Exception as e:
        return None, None, None, None, None, None

def calc_rev(strike, spot, lvns, skew, is_support):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    if any(abs(strike - lvn) < 30 for lvn in lvns):
        base += 10
    base = base - 10 if (is_support and skew > 2.0) else base + 5 if (not is_support and skew > 2.0) else base
    return round(min(98.0, base), 1)

# Execution
spot, expiry, calls, puts, hv, lvns = get_data()

if spot is not None and not calls.empty and not puts.empty:
    # GEX Calculation
    calls['GEX'] = calls['openInterest'] * calls.get('gamma', 0.1)
    puts['GEX'] = puts['openInterest'] * puts.get('gamma', 0.1) * -1
    
    active_range = (spot * 0.85, spot * 1.15)
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > active_range[0]) & (all_gex['strike'] < active_range[1])].sort_values('strike')
    
    # DATA GUARD for Gamma Flip - Prevents the argmin() crash!
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        flip_idx = np.abs(all_gex['cum_gex']).argmin()
        gamma_flip = all_gex.iloc[flip_idx]['strike']
        
        # Bias Logic
        atm_call_iv = calls.iloc[(calls['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
        atm_put_iv = puts.iloc[(puts['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
        avg_iv = (atm_call_iv + atm_put_iv) / 2
        skew = atm_put_iv - atm_call_iv
        
        regime = "🛡️ COMPLACENT" if avg_iv < hv - 2 else "⚡ VOLATILE" if avg_iv > hv + 2 else "⚖️ NEUTRAL"
        bias = "🔴 BEARISH" if skew > 2.0 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"

        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap", "📖 Trade Manual"])

        with tab1:
            st.subheader(f"NDX Profile | Spot: {spot:,.2f}")
            fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            if gamma_flip > 0:
                fig_gamma.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text=f"FLIP: {gamma_flip:,.0f}")
            fig_gamma.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_gamma, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
            top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)

            with c1:
                st.write("### 🟢 Resistance")
                for s in top_c['strike'][:3]:
                    st.success(f"{s:,.0f} | **{calc_rev(s, spot, lvns, skew, False)}% Rev**")
            with c2:
                st.write("### 🟡 Mid-Range")
                for s in top_c['strike'][3:6]:
                    st.warning(f"{s:,.0f} | **{calc_rev(s, spot, lvns, skew, False)}% Rev**")
            with c3:
                st.write("### 🔴 Support")
                for s in top_p['strike'][:3]:
                    st.error(f"{s:,.0f} | **{calc_rev(s, spot, lvns, skew, True)}% Rev**")

        with tab2:
            st.subheader("Market Sentiment & Volatility")
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("Gamma Flip", f"{gamma_flip:,.0f}")
            col_m2.metric("Daily Bias", bias)
            col_m3.metric("Regime", regime)
            col_m4.metric("Put Skew", f"{skew:.2f}")

            vol_df = pd.DataFrame({'Type': ['Implied Vol', 'Historical Vol'], 'Value': [avg_iv, hv]})
            fig_vol = px.bar(vol_df, x='Type', y='Value', color='Type')
            fig_vol.update_layout(template="plotly_dark", height=350, showlegend=False)
            st.plotly_chart(fig_vol, use_container_width=True)

        with tab3:
            st.subheader("Structural Liquidity Map")
            h_data = all_gex[(all_gex['strike'] > spot*0.97) & (all_gex['strike'] < spot*1.03)].copy()
            if not h_data.empty:
                h_data['Type'] = np.where(h_data['GEX'] > 0, 'Calls', 'Puts')
                fig_heat = px.density_heatmap(h_data, x="strike", y="Type", z="openInterest", color_continuous_scale="Viridis")
                fig_heat.add_vline(x=spot, line_width=3, line_dash="dash", line_color="white")
                fig_heat.update_layout(template="plotly_dark", height=500)
                st.plotly_chart(fig_heat, use_container_width=True)
            else:
                st.write("Insufficient data for heatmap.")

        with tab4:
            st.header("🎯 Sniper Strategy Manual")
            st.markdown("1. Monitor the Gamma Flip level.\\n2. Trade away from resistance levels.\\n3. Check IV Bias for directional confluence.")

    else:
        st.warning("Options chain data returned empty for the active range. Waiting for API refresh...")
else:
    st.warning("⚠️ Market Data Unavailable. The Yahoo Finance API might be throttled. Retrying shortly...")
