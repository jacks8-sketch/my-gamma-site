import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, timezone

st.set_page_config(page_title="NDX Gamma Pro", layout="wide")
st.title("🎯 NDX Sniper: Gamma & IV Bias")

ndx = yf.Ticker("^NDX")

def get_data():
    for i in range(3):
        try:
            hist = ndx.history(period="30d") # Get 30d for HV calculation
            if hist.empty: continue
            spot = hist['Close'].iloc[-1]
            # Calculate 20-day Historical Volatility
            hist['returns'] = hist['Close'].pct_change()
            hv = hist['returns'].std() * np.sqrt(252) * 100
            
            expiries = ndx.options
            if not expiries: continue
            chain = ndx.option_chain(expiries[0])
            return spot, expiries[0], chain.calls, chain.puts, hv
        except:
            time.sleep(1)
    return None, None, None, None, None

spot, expiry, calls, puts, hv = get_data()

def get_bias(calls, puts, spot, hv):
    # Calculate Average Implied Vol (IV)
    atm_call_iv = calls.iloc[(calls['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    atm_put_iv = puts.iloc[(puts['strike'] - spot).abs().argsort()[:1]]['impliedVolatility'].iloc[0] * 100
    avg_iv = (atm_call_iv + atm_put_iv) / 2
    
    # Skew check: Are puts more expensive than calls?
    skew = atm_put_iv - atm_call_iv
    
    # Regime Logic
    if avg_iv > hv + 2:
        regime = "⚡ VOLATILE (Trend Likely)"
    elif avg_iv < hv - 2:
        regime = "🛡️ COMPLACENT (Mean Reversion)"
    else:
        regime = "⚖️ NEUTRAL"
        
    # Directional Bias
    if skew > 2.0 and spot < calls['strike'].mean():
        bias = "🔴 BEARISH (Fear Pricing In)"
        color = "inverse"
    elif skew < -0.5:
        bias = "🟢 BULLISH (Call Demand)"
    else:
        bias = "🟡 NEUTRAL / CHOP"
        
    return bias, regime, avg_iv

if spot:
    bias, regime, iv = get_bias(calls, puts, spot, hv)
    
    # --- NEW BIAS SECTION ---
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Daily Bias", bias)
    b2.metric("Market Regime", regime)
    b3.metric("Implied Vol (IV)", f"{iv:.2f}%")
    b4.metric("Historical Vol (HV)", f"{hv:.2f}%")
    
    st.write("---")

    # Gamma Profile Chart
    if 'gamma' not in calls.columns or calls['gamma'].isnull().all():
        calls['GEX'] = calls['openInterest'] * 0.1
        puts['GEX'] = puts['openInterest'] * -0.1
    else:
        calls['GEX'] = calls['openInterest'] * calls['gamma'] * (spot**2) * 0.01
        puts['GEX'] = puts['openInterest'] * puts['gamma'] * (spot**2) * -0.01

    all_gex = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    fig = px.bar(all_gex, x='strike', y='GEX', title=f"Gamma Distribution", color='GEX', color_continuous_scale='RdYlGn')
    fig.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig, use_container_width=True)

    # Reversal Logic (Sniper Entry)
    def calculate_advanced_reversal(strike, spot):
        diff = abs(spot - strike)
        if diff <= 15: return round(10 + (diff * 2), 2)
        elif diff <= 60: return round(45 + (diff * 0.6), 2)
        else: return round(min(92.0, 75 + (diff / 25)), 2)

    st.subheader("🎯 Sniper Entry Levels (50pt NQ Target)")
    c1, c2, c3 = st.columns(3)
    top_c = calls.nlargest(6, 'openInterest').sort_values('strike')
    top_p = puts.nlargest(6, 'openInterest').sort_values('strike', ascending=False)

    with c1:
        st.write("### 🟢 Resistance")
        for s in top_c['strike'][:3]:
            st.success(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
    with c2:
        st.write("### 🟡 Mid-Range")
        for s in top_c['strike'][3:6]:
            st.warning(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
    with c3:
        st.write("### 🔴 Support")
        for s in top_p['strike'][:3]:
            st.error(f"Strike {s:,.0f} | **{calculate_advanced_reversal(s, spot)}% Rev**")
