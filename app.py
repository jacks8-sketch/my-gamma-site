import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
import time
from datetime import datetime, timezone

st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3):
        try:
            # Get 60d to ensure we have enough for HV and IV history
            hist = ndx.history(period="60d")
            if hist.empty: continue
            spot = hist['Close'].iloc[-1]
            
            # Historical Volatility (20-day)
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
    
    if avg_iv > hv + 2: regime = "⚡ VOLATILE (Trend Likely)"
    elif avg_iv < hv - 2: regime = "🛡️ COMPLACENT (Mean Reversion)"
    else: regime = "⚖️ NEUTRAL"
        
    if skew > 2.0: bias = "🔴 BEARISH (Fear)"
    elif skew < -0.5: bias = "🟢 BULLISH (Demand)"
    else: bias = "🟡 NEUTRAL / CHOP"
        
    return bias, regime, avg_iv, skew

if spot:
    bias, regime, iv, skew = get_bias(calls, puts, spot, hv)
    
    # --- TABS LAYOUT ---
    tab1, tab2 = st.tabs(["🎯 Gamma Sniper", "📊 IV & Bias Analysis"])

    with tab1:
        st.subheader("NDX Gamma Profile")
        if 'gamma' not in calls.columns or calls['gamma'].isnull().all():
            calls['GEX'] = calls['openInterest'] * 0.1
            puts['GEX'] = puts['openInterest'] * -0.1
        else:
            calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
            puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

        all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
        fig_gamma = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
        fig_gamma.update_layout(template="plotly_dark", height=400, showlegend=False)
        st.plotly_chart(fig_gamma, use_container_width=True)

        st.write("---")
        
        # Reversal Probability Logic
        def calculate_advanced_reversal(strike, spot):
            diff = abs(spot - strike)
            if diff <= 15: return round(10 + (diff * 2), 2)
            elif diff <= 60: return round(45 + (diff * 0.6), 2)
            else: return round(min(92.0, 75 + (diff / 25)), 2)

        st.subheader("Sniper Entry Levels (50pt Target)")
        col1, col2, col3 = st.columns(3)
        top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
        top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)

        with col1:
            st.write("### 🟢 Resistance")
            for s in top_c['strike'][:3]:
                st.success(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
        with col2:
            st.write("### 🟡 Mid-Range")
            for s in top_c['strike'][3:6]:
                st.warning(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
        with col3:
            st.write("### 🔴 Support")
            for s in top_p['strike'][:3]:
                st.error(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")

    with tab2:
        st.subheader("Volatility & Sentiment Dashboard")
        
        # IV vs HV Comparison Chart
        vol_data = pd.DataFrame({
            'Metric': ['Implied Vol (Forward)', 'Historical Vol (Past)'],
            'Value': [iv, hv]
        })
        fig_vol = px.bar(vol_data, x='Metric', y='Value', color='Metric', 
                         color_discrete_map={'Implied Vol (Forward)': '#00CC96', 'Historical Vol (Past)': '#636EFA'})
        fig_vol.update_layout(template="plotly_dark", height=300)
        st.plotly_chart(fig_vol, use_container_width=True)
        
        c_a, c_b, c_c = st.columns(3)
        c_a.metric("Daily Bias", bias)
        c_b.metric("Market Regime", regime)
        c_c.metric("IV/Put Skew", f"{skew:.2f}")
        
        st.write("---")
        st.info(f"**Trading Tip:** In a '{regime}' regime, look for '{bias}' entries near the Gamma Walls. If IV is much higher than HV, expect faster moves and tighter reversals.")

else:
    st.warning("Data is currently refreshing. Please wait a moment.")
