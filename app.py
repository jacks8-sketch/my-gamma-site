import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
from datetime import datetime, timezone

st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8vw !important; }
    [data-testid="stMetricLabel"] { font-size: 1.0vw !important; }
    </style>
    """, unsafe_allow_html=True)

ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3):
        try:
            hist = ndx.history(period="60d")
            if hist.empty: continue
            spot = hist['Close'].iloc[-1]
            hist['returns'] = hist['Close'].pct_change()
            hv = hist['returns'].tail(20).std() * np.sqrt(252) * 100
            expiries = ndx.options
            if not expiries: continue
            chain = ndx.option_chain(expiries[0])
            return spot, expiries[0], chain.calls, chain.puts, hv, hist
        except:
            time.sleep(1)
    return None, None, None, None, None, None

spot, expiry, calls, puts, hv, hist = get_data()

def get_bias(calls, puts, spot, hv):
    atm_call_iv = calls.iloc[(calls['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    atm_put_iv = puts.iloc[(puts['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    avg_iv = (atm_call_iv + atm_put_iv) / 2
    skew = atm_put_iv - atm_call_iv
    regime = "⚡ VOLATILE (Trend)" if avg_iv > hv + 2 else "🛡️ COMPLACENT (Mean Rev)" if avg_iv < hv - 2 else "⚖️ NEUTRAL"
    bias = "🔴 BEARISH" if skew > 2.0 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"
    return bias, regime, avg_iv, skew

if spot:
    bias, regime, iv, skew = get_bias(calls, puts, spot, hv)
    tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap"])

    # Pre-calculate GEX for all tabs
    calls['GEX'] = calls['openInterest'] * (calls['gamma'] if 'gamma' in calls.columns else 0.1)
    puts['GEX'] = puts['openInterest'] * (puts['gamma'] if 'gamma' in puts.columns else 0.1) * -1

    with tab1:
        st.subheader("NDX Gamma Profile")
        all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
        fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
        fig_gamma.update_layout(template="plotly_dark", height=400, showlegend=False)
        st.plotly_chart(fig_gamma, use_container_width=True)

        def calculate_advanced_reversal(strike, spot):
            diff = abs(spot - strike)
            if diff <= 15: return round(10 + (diff * 2), 2)
            elif diff <= 60: return round(45 + (diff * 0.6), 2)
            else: return round(min(92.0, 75 + (diff / 25)), 2)

        st.subheader("Sniper Entry Levels")
        col1, col2, col3 = st.columns(3)
        top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
        top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)
        with col1:
            for s in top_c['strike'][:3]: st.success(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
        with col2:
            for s in top_c['strike'][3:6]: st.warning(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
        with col3:
            for s in top_p['strike'][:3]: st.error(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")

    with tab2:
        st.subheader("Sentiment Metrics")
        c_a, c_b, c_c = st.columns(3)
        c_a.metric("Daily Bias", bias)
        c_b.metric("Regime", regime.split('(')[0].strip(), help=regime)
        c_c.metric("IV/Put Skew", f"{skew:.2f}")
        st.info(f"**Trading Tip:** {bias} focus today. Watch the '{regime}' for volatility.")

    with tab3:
        st.subheader("Gamma Density Heatmap")
        # Create a heatmap of Open Interest vs Strike to show "Structural Walls"
        heatmap_data = pd.concat([
            calls[['strike', 'openInterest']].assign(Type='Calls'),
            puts[['strike', 'openInterest']].assign(Type='Puts')
        ])
        fig_heat = px.density_heatmap(heatmap_data, x="strike", y="Type", z="openInterest", 
                                      color_continuous_scale="Viridis", title="OI Concentration Map")
        fig_heat.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_heat, use_container_width=True)
        st.write("---")
        st.markdown("**How to read the Heatmap:** The brightest spots are the 'Hard Walls'. If the bright spot is far from current price, expect a magnet effect. If price is sitting on a bright spot, expect a battle.")

else:
    st.warning("Data is currently refreshing...")
