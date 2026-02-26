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
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    </style>
    """, unsafe_allow_html=True)

# 2. DATA ENGINE
def get_data():
    ticker_sym = "^NDX"
    # Massive API Key
    api_url = f"https://api.massive.com/v1/finance/yahoo/ticker/{ticker_sym}/full?apikey=RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp"
    
    try:
        resp = requests.get(api_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            spot = data['price']['regularMarketPrice']
            opt_data = data['options'][0]
            
            calls, puts = pd.DataFrame(opt_data['calls']), pd.DataFrame(opt_data['puts'])
            tk = yf.Ticker(ticker_sym)
            hist = tk.history(period="60d")
            return spot, calls, puts, hist
    except Exception as e:
        pass
    
    # Emergency Fallback
    try:
        tk = yf.Ticker(ticker_sym)
        hist = tk.history(period="60d")
        spot = hist['Close'].iloc[-1]
        chain = tk.option_chain(tk.options[0])
        return spot, chain.calls, chain.puts, hist
    except:
        return None, None, None, None

# Advanced Reversal Odds Algorithim (Volume, OI, Gamma, Distance)
def calc_advanced_odds(row, spot, max_oi, max_vol, max_gamma):
    # Normalize the data points (0 to 1 scale)
    oi_score = row['openinterest'] / max_oi if max_oi > 0 else 0
    vol_score = row.get('volume', 0) / max_vol if max_vol > 0 else 0
    gamma_score = row['gamma'] / max_gamma if max_gamma > 0 else 0
    
    # Distance Penalty: Levels too far away have lower immediate relevance
    dist_pct = abs(row['strike'] - spot) / spot
    dist_score = max(0, 1 - (dist_pct * 15)) 
    
    # Base Reversal Floor is 55%
    raw_score = (oi_score * 0.40) + (gamma_score * 0.35) + (vol_score * 0.15) + (dist_score * 0.10)
    
    # Scale final percentage between 55% and 98.5%
    final_pct = 55.0 + (raw_score * 43.5)
    return min(98.5, round(final_pct, 1))

# 3. EXECUTION
spot, calls, puts, hist = get_data()

if spot is not None and not calls.empty:
    # Standardize & Tag Options
    for df in [calls, puts]:
        df.columns = [c.lower().replace('_', '') for c in df.columns]
    
    calls['type'] = 'Call'
    puts['type'] = 'Put'
    
    # Clean Data & Fill Missing Greeks
    for df in [calls, puts]:
        if 'gamma' not in df.columns: df['gamma'] = 0.0001
        if 'volume' not in df.columns: df['volume'] = 0
        if 'theta' not in df.columns: df['theta'] = -0.01
        df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0.0001)
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    
    # GEX Calculation
    calls['gex'] = (calls['openinterest'] * calls['gamma']) * 1000
    puts['gex'] = (puts['openinterest'] * puts['gamma']) * 1000 * -1
    
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.94) & (all_gex['strike'] < spot * 1.06)].sort_values('strike')
    
    # Calculate True Reversal Odds
    max_oi = all_gex['openinterest'].max()
    max_vol = all_gex['volume'].max()
    max_gamma = all_gex['gamma'].max()
    all_gex['rev_odds'] = all_gex.apply(lambda r: calc_advanced_odds(r, spot, max_oi, max_vol, max_gamma), axis=1)
    
    # Separate into Zones
    res_walls = all_gex[(all_gex['type'] == 'Call') & (all_gex['strike'] > spot)].nlargest(5, 'rev_odds')
    sup_walls = all_gex[(all_gex['type'] == 'Put') & (all_gex['strike'] < spot)].nlargest(5, 'rev_odds')
    
    # Mid-Range Walls: High probability levels within 0.8% of spot price
    mid_candidates = all_gex[abs(all_gex['strike'] - spot) < (spot * 0.008)]
    mid_walls = mid_candidates[~mid_candidates['strike'].isin(res_walls['strike'].tolist() + sup_walls['strike'].tolist())].nlargest(3, 'rev_odds')
    
    # Market Metrics
    all_gex['cum_gex'] = all_gex['gex'].cumsum()
    gamma_flip = all_gex.iloc[np.abs(all_gex['cum_gex']).argmin()]['strike']
    hv = hist['Close'].pct_change().tail(20).std() * np.sqrt(252) * 100
    
    atm_idx = (calls['strike'] - spot).abs().argmin()
    avg_iv = calls.iloc[atm_idx]['impliedvolatility'] * 100
    skew = (puts.iloc[atm_idx]['impliedvolatility'] - calls.iloc[atm_idx]['impliedvolatility']) * 100
    
    bias = "🔴 BEARISH" if skew > 1.0 else "🟢 BULLISH"
    status = "⚡ VOLATILE" if spot < gamma_flip else "🛡️ STABLE"

    # 4. UI LAYOUT
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Gamma Sniper", "📊 IV/Bias Analysis", "🗺️ Heatmap", "📓 Playbook"])
    
    with tab1:
        st.subheader(f"NDX Sniper Profile | Spot: {spot:,.2f}")
        fig = px.bar(all_gex, x='strike', y='gex', color='gex', color_continuous_scale='RdYlGn')
        fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text="FLIP")
        fig.update_layout(template="plotly_dark", height=420, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("### 🟢 Resistance Walls")
            for _, row in res_walls.head(3).iterrows():
                st.success(f"{row['strike']:,.0f} | {row['rev_odds']}% Rev")
        with c2:
            st.write("### 🟡 Mid-Range Walls")
            for _, row in mid_walls.head(3).iterrows():
                st.warning(f"{row['strike']:,.0f} | {row['rev_odds']}% Rev")
        with c3:
            st.write("### 🔴 Support Walls")
            for _, row in sup_walls.head(3).iterrows():
                st.error(f"{row['strike']:,.0f} | {row['rev_odds']}% Rev")

    with tab2:
        st.subheader("Volatility & Sentiment Profile")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Daily Bias", bias)
        col_b.metric("Gamma Flip", f"{gamma_flip:,.0f}")
        col_c.metric("Market Status", status)
        
        fig_vol = px.bar(x=['Intended Vol (IV)', 'Historical Vol (HV)'], y=[avg_iv, hv], 
                         color=['IV', 'HV'], title="Intended Vol vs. Realized Vol")
        fig_vol.update_layout(template="plotly_dark", showlegend=False)
        st.plotly_chart(fig_vol, use_container_width=True)

        st.write("### Implied Volatility Curve")
        st.plotly_chart(px.line(all_gex, x='strike', y='impliedvolatility', template="plotly_dark"), use_container_width=True)
        
    with tab3:
        st.subheader("Gamma Liquidity Heatmap")
        st.caption("Top Half = Calls | Bottom Half = Puts | Brighter Color = Higher Reversal Odds")
        # Y-Axis is GEX (Positive=Calls on Top, Negative=Puts on Bottom). Color = Reversal Odds.
        fig_heat = px.scatter(all_gex, x="strike", y="gex", color="rev_odds", size="openinterest",
                              color_continuous_scale="plasma", labels={'gex': 'GEX Structure', 'rev_odds': 'Reversal %'})
        fig_heat.add_hline(y=0, line_dash="solid", line_color="white")
        fig_heat.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_heat, use_container_width=True)

    with tab4:
        st.subheader("🌅 Morning Routine & Playbook")
        st.markdown("""
        ### **Pre-Market Setup (6:30 AM)**
        1. **Check Bias & Status:** Head to the **IV/Bias Tab**. Note if the market is *Volatile* (Spot < Flip) or *Stable* (Spot > Flip). Identify the Daily Bias.
        2. **Plot the Heavy Walls:** Look at **Tab 1 (Gamma Sniper)**. Draw lines on your charting platform at the top 🟢 Resistance and 🔴 Support levels showing **>85% Reversal Odds**.
        3. **Identify Speedbumps:** Note the 🟡 Mid-Range Walls. These are high-probability intraday pivot points where price will stall.
        4. **Confirm with Heatmap:** Verify your drawn levels line up with the brightest (highest probability) nodes on the **Heatmap Tab**.

        ### **Execution Rules**
        * **Trend Days:** If market is trending hard, *do not short the first touch* of a Mid-Range Wall. Wait for the heavy Support/Resistance walls.
        * **Limit Orders:** Set limits precisely at the heavy walls where High Open Interest, Gamma, and Volume converge. 
        * **Invalidation:** If the Gamma Flip shifts dramatically intraday, reassess. 
        """)
else:
    st.error("⚠️ Failed to reach Market Data. Retrying stealth connection...")
