import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import requests
from streamlit_autorefresh import st_autorefresh

# 1. SETUP
st_autorefresh(interval=60000, key="datarefresh")
st.set_page_config(page_title="NDX Sniper Pro", layout="wide")

# 2. MASSIVE DATA FETCH (No Yahoo library used)
def get_data():
    try:
        # Your Key from Massive Dashboard
        API_KEY = "RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp"
        
        # Correct Massive URL for NDX Options
        url = f"https://api.massive.com/v1/finance/options/NDX?apikey={API_KEY}"
        response = requests.get(url)
        
        if response.status_code != 200:
            st.sidebar.error(f"Massive API Error: {response.status_code}")
            return None, None, None, None, None

        data = response.json()
        
        # Extract the details
        spot = data.get('underlying_price')
        expiry = data.get('expiration')
        
        # Get calls and puts from the results
        calls = pd.DataFrame(data.get('calls', []))
        puts = pd.DataFrame(data.get('puts', []))
        
        return spot, expiry, calls, puts, 18.5 # Default HV
    except Exception as e:
        st.sidebar.error(f"Logic Error: {e}")
        return None, None, None, None, None

def calc_rev(strike, spot):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.5) if diff <= 80 else 85
    return round(min(98.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hv = get_data()

if spot is not None and not calls.empty:
    # Use a fixed Gamma if the API doesn't provide it (common in basic tiers)
    calls['GEX'] = calls['open_interest'] * calls.get('gamma', 0.0001)
    puts['GEX'] = puts['open_interest'] * puts.get('gamma', 0.0001) * -1
    
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.95) & (all_gex['strike'] < spot * 1.05)].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['GEX'].cumsum()
        gamma_flip = all_gex.iloc[np.abs(all_gex['cum_gex']).argmin()]['strike']
        
        # TABS
        tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 Metrics", "🗺️ Heatmap"])
        
        with tab1:
            st.subheader(f"NDX | Spot: {spot:,.2f} | Flip: {gamma_flip:,.2f}")
            fig = px.bar(all_gex, x='strike', y='GEX', color='GEX', color_continuous_scale='RdYlGn')
            fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange")
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.write("### 🟢 Resistance")
                for s in calls.nlargest(3, 'open_interest')['strike']:
                    st.success(f"{s:,.0f} | {calc_rev(s, spot)}% Rev")
            with c2:
                st.write("### 🔴 Support")
                for s in puts.nlargest(3, 'open_interest')['strike']:
                    st.error(f"{s:,.0f} | {calc_rev(s, spot)}% Rev")
        
        with tab2:
            st.metric("Market Price", f"{spot:,.2f}")
            st.metric("Gamma Flip", f"{gamma_flip:,.2f}")
            
        with tab3:
            st.plotly_chart(px.density_heatmap(all_gex, x="strike", y="open_interest", z="GEX"), use_container_width=True)
else:
    st.info("Waiting for Massive API data...")
