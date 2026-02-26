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

# 2. DATA & LVN CALCULATION
def get_data():
    ticker_sym = "^NDX"
    try:
        # Massive API Key: RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp
        url = f"https://api.massive.com/v1/finance/yahoo/ticker/{ticker_sym}/full?apikey=RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            spot = data['price']['regularMarketPrice']
            opt_data = data['options'][0]
            tk = yf.Ticker(ticker_sym)
            hist = tk.history(period="60d")
            return spot, opt_data['expirationDate'], pd.DataFrame(opt_data['calls']), pd.DataFrame(opt_data['puts']), hist
    except:
        pass
    return None, None, None, None, None

def calc_rev(strike, spot, lvns):
    diff = abs(spot - strike)
    base = 45 + (diff * 0.4)
    if any(abs(strike - lvn) < 40 for lvn in lvns):
        base += 15
    return round(min(99.0, base), 1)

# 3. EXECUTION
spot, expiry, calls, puts, hist = get_data()

if spot is not None and not calls.empty:
    calls.columns = [c.lower() for c in calls.columns]
    puts.columns = [c.lower() for c in puts.columns]
    
    # Calculate LVNs (Structural Reversal Nodes)
    price_bins = pd.cut(hist['Close'], bins=50)
    counts = price_bins.value_counts()
    lvns = [bin.mid for bin, count in counts.items() if count <= counts.quantile(0.15)]
    
    def clean_gamma(df):
        if 'gamma' not in df.columns: df['gamma'] = 0.0001
        df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0.0001)
        return df

    calls, puts = clean_gamma(calls), clean_gamma(puts)
    calls['gex'] = (calls['openinterest'] * calls['gamma']) * 1000
    puts['gex'] = (puts['openinterest'] * puts['gamma']) * 1000 * -1
    
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.93) & (all_gex['strike'] < spot * 1.07)].sort_values('strike')
    
    if not all_gex.empty:
        all_gex['cum_gex'] = all_gex['gex'].cumsum()
        gamma_flip = all_gex.iloc[np.abs(all_gex['cum_gex']).argmin()]['strike']
        
        # Volatility calculations
        hv = hist['Close'].pct_change().tail(20).std() * np.sqrt(252) * 100
        atm_idx = (calls['strike'] - spot).abs().argmin()
        avg_iv = calls.iloc[atm_idx]['impliedvolatility'] * 100
        skew = (puts.iloc[atm_idx]['impliedvolatility'] - calls.iloc[atm_idx]['impliedvolatility']) * 100
        
        bias = "🔴 BEARISH" if skew > 1.0 else "🟢 BULLISH"
        status = "⚡ VOLATILE" if spot < gamma_flip else "🛡️ STABLE"

        # 4. UI LAYOUT
        tab1, tab2, tab3 = st.tabs(["🎯 Gamma Sniper", "📊 IV/Bias Analysis", "🗺️ Heatmap"])
        
        with tab1:
            st.subheader(f"NDX Sniper Profile | Spot: {spot:,.2f}")
            fig = px.bar(all_gex, x='strike', y='gex', color='gex', color_continuous_scale='RdYlGn')
            fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text="FLIP")
            fig.update_layout(template="plotly_dark", height=420, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.write("### 🟢 Resistance")
                for s in calls.nlargest(3, 'openinterest')['strike'].sort_values():
                    st.success(f"{s:,.0f} | {calc_rev(s, spot, lvns)}% Rev")
            with c2:
                st.write("### 🟡 Mid-Range (LVN)")
                # 3 Mid-Range strikes near structural LVNs
                mid_strikes = sorted(lvns, key=lambda x: abs(x - spot))[1:4]
                for s in sorted(mid_strikes):
                    st.warning(f"{s:,.0f} | {calc_rev(s, spot, lvns)}% Rev")
            with c3:
                st.write("### 🔴 Support")
                for s in puts.nlargest(3, 'openinterest')['strike'].sort_values(ascending=False):
                    st.error(f"{s:,.0f} | {calc_rev(s, spot, lvns)}% Rev")
        
        with tab2:
            st.subheader("Volatility & Sentiment Profile")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Daily Bias", bias)
            col_b.metric("Gamma Flip", f"{gamma_flip:,.0f}")
            col_c.metric("Market Status", status)
            
            # Intended Vol (IV) vs Realized Vol (HV)
            fig_vol = px.bar(x=['Intended Vol (IV)', 'Historical Vol (HV)'], y=[avg_iv, hv], 
                             color=['IV', 'HV'], title="Market Expectation vs. Realized Vol")
            fig_vol.update_layout(template="plotly_dark", showlegend=False)
            st.plotly_chart(fig_vol, use_container_width=True)

            # IV Curve
            st.write("### Implied Volatility Smile")
            st.plotly_chart(px.line(all_gex, x='strike', y='impliedvolatility', template="plotly_dark"), use_container_width=True)
            
        with tab3:
            st.subheader("Gamma Liquidity Heatmap")
            st.plotly_chart(px.density_heatmap(all_gex, x="strike", y="openinterest", z="gex", color_continuous_scale="Viridis"), use_container_width=True)
else:
    st.warning("📡 Market Data Source Busy. Automatic Retry Active.")
