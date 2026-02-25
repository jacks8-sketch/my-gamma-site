import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
from datetime import datetime, timezone
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

ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3):
        try:
            hist_long = ndx.history(period="60d")
            if hist_long.empty: continue
            spot = hist_long['Close'].iloc[-1]
            
            # Calculate HV
            hist_long['returns'] = hist_long['Close'].pct_change()
            hv = hist_long['returns'].tail(20).std() * np.sqrt(252) * 100
            
            # Identify LVNs (Low Volume Nodes)
            price_bins = pd.cut(hist_long['Close'], bins=50)
            node_counts = price_bins.value_counts()
            lvn_threshold = node_counts.quantile(0.2)
            lvns = [bin.mid for bin, count in node_counts.items() if count <= lvn_threshold]
            
            expiries = ndx.options
            chain = ndx.option_chain(expiries[0])
            return spot, expiries[0], chain.calls, chain.puts, hv, lvns
        except:
            time.sleep(1)
    return None, None, None, None, None, None

spot, expiry, calls, puts, hv, lvns = get_data()

if spot:
    # Logic for Bias/Regime
    atm_call_iv = calls.iloc[(calls['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    atm_put_iv = puts.iloc[(puts['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    avg_iv = (atm_call_iv + atm_put_iv) / 2
    skew = atm_put_iv - atm_call_iv
    regime = "⚡ VOLATILE (Trend)" if avg_iv > hv + 2 else "🛡️ COMPLACENT (Mean Rev)" if avg_iv < hv - 2 else "⚖️ NEUTRAL"
    bias = "🔴 BEARISH" if skew > 2.0 else "🟢 BULLISH" if skew < -0.5 else "🟡 NEUTRAL"

    tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 IV Bias", "🗺️ Gamma Heatmap"])

    calls['GEX'] = calls['openInterest'] * (calls['gamma'] if 'gamma' in calls.columns else 0.1)
    puts['GEX'] = puts['openInterest'] * (puts['gamma'] if 'gamma' in puts.columns else 0.1) * -1

    with tab1:
        st.subheader(f"NDX Gamma Profile | Spot: {spot:,.2f}")
        all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
        fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
        fig_gamma.update_layout(template="plotly_dark", height=400, showlegend=False)
        st.plotly_chart(fig_gamma, use_container_width=True)

        def calculate_advanced_reversal(strike, spot, lvns):
            diff = abs(spot - strike)
            if diff <= 15: base = 10 + (diff * 2)
            elif diff <= 60: base = 45 + (diff * 0.6)
            else: base = 75 + (diff / 25)
            if any(abs(strike - lvn) < 25 for lvn in lvns): base += 8
            return round(min(96.0, base), 2)

        st.subheader("Sniper Entry Levels")
        col1, col2, col3 = st.columns(3)
        top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
        top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)
        with col1:
            for s in top_c['strike'][:3]: st.success(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot, lvns)}% Rev**")
        with col2:
            for s in top_c['strike'][3:6]: st.warning(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot, lvns)}% Rev**")
        with col3:
            for s in top_p['strike'][:3]: st.error(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot, lvns)}% Rev**")

    with tab2:
        st.subheader("Volatility Comparison")
        # RESTORED CHART: IV vs HV
        vol_df = pd.DataFrame({
            'Type': ['Implied Vol (Future)', 'Historical Vol (Past)'],
            'Value': [avg_iv, hv]
        })
        fig_vol = px.bar(vol_df, x='Type', y='Value', color='Type', 
                         color_discrete_map={'Implied Vol (Future)': '#00CC96', 'Historical Vol (Past)': '#636EFA'})
        fig_vol.update_layout(template="plotly_dark", height=350, showlegend=False)
        st.plotly_chart(fig_vol, use_container_width=True)
        
        c_a, c_b, c_c = st.columns(3)
        c_a.metric("Daily Bias", bias)
        c_b.metric("Regime", regime.split('(')[0].strip(), help=regime)
        c_c.metric("IV/Put Skew", f"{skew:.2f}")

    with tab3:
        st.subheader("Live Gamma & Volume Density Heatmap")
        h_data = pd.concat([
            calls[(calls['strike'] > spot*0.95) & (calls['strike'] < spot*1.05)][['strike', 'openInterest']].assign(Type='Calls'),
            puts[(puts['strike'] > spot*0.95) & (puts['strike'] < spot*1.05)][['strike', 'openInterest']].assign(Type='Puts')
        ])
        fig_heat = px.density_heatmap(h_data, x="strike", y="Type", z="openInterest", color_continuous_scale="Viridis")
        fig_heat.add_vline(x=spot, line_width=3, line_dash="dash", line_color="white")
        fig_heat.update_layout(template="plotly_dark", height=500, hovermode="closest")
        st.plotly_chart(fig_heat, use_container_width=True)

else:
    st.warning("Fetching Market Data...")
