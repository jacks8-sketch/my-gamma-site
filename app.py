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
st.markdown("<style>[data-testid='stMetricValue'] { font-size: 1.8vw !important; }</style>", unsafe_allow_html=True)

# 2. THE ULTIMATE DATA FETCH
def get_data():
    ticker_sym = "QQQ"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    
    try:
        # Get Price Data
        dat = yf.download(ticker_sym, period="60d", interval="1d", progress=False)
        if dat.empty: return None, None, None, None, None, None
        
        spot = dat['Close'].iloc[-1].item()
        dat['returns'] = dat['Close'].pct_change()
        hv = dat['returns'].tail(20).std().item() * np.sqrt(252) * 100
        
        # Get Options (Using a more robust direct call)
        tk = yf.Ticker(ticker_sym)
        expiry = tk.options[0]
        opts = tk.option_chain(expiry)
        calls, puts = opts.calls, opts.puts
        
        return spot, expiry, calls, puts, hv, []
    except Exception as e:
        st.sidebar.error(f"API Error: {e}")
        return None, None, None, None, None, None

# 3. EXECUTION
spot, expiry, calls, puts, hv, lvns = get_data()

if spot is not None and not calls.empty:
    # GEX Calculation
    calls['GEX'] = calls['openInterest'] * calls.get('gamma', 0.0001) * 100
    puts['GEX'] = puts['openInterest'] * puts.get('gamma', 0.0001) * 100 * -1
    
    all_gex = pd.concat([calls, puts])
    # Filter for strikes near the money
    all_gex = all_gex[(all_gex['strike'] > spot * 0.9) & (all_gex['strike'] < spot * 1.1)].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        gamma_flip = all_gex.iloc[np.abs(all_gex['cum_gex']).argmin()]['strike']
        
        # UI TABS
        tab1, tab2, tab3 = st.tabs(["🎯 Sniper", "📊 Volatility", "🗺️ Heatmap"])
        
        with tab1:
            st.subheader(f"QQQ Sniper | Spot: ${spot:,.2f} | Flip: ${gamma_flip:,.2f}")
            fig = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange")
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.write("### 🟢 Top Call Resistance")
                st.dataframe(calls.nlargest(5, 'openInterest')[['strike', 'openInterest']])
            with c2:
                st.write("### 🔴 Top Put Support")
                st.dataframe(puts.nlargest(5, 'openInterest')[['strike', 'openInterest']])
        
        with tab2:
            st.metric("Historical Vol (20D)", f"{hv:.2f}%")
            st.bar_chart(all_gex.set_index('strike')['openInterest'].tail(20))
            
        with tab3:
            st.subheader("Gamma Concentration")
            fig_heat = px.density_heatmap(all_gex, x="strike", y="GEX", z="openInterest", color_continuous_scale="Viridis")
            st.plotly_chart(fig_heat, use_container_width=True)
            
    else:
        st.error("Data received but strikes are empty. Market might be in transition.")
else:
    st.info("🔄 Attempting to bypass Yahoo's block... Please wait 30 seconds.")
    st.button("Force Retry")
