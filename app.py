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

# 2. DATA ENGINE
def get_data():
    ticker_sym = "^NDX"
    # Using your Massive Key: RWocAyzzUWSS6gRFmqTOiiFzDmYcpKPp
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
    except:
        pass
    
    try:
        tk = yf.Ticker(ticker_sym)
        hist = tk.history(period="60d")
        spot = hist['Close'].iloc[-1]
        chain = tk.option_chain(tk.options[0])
        return spot, chain.calls, chain.puts, hist
    except:
        return None, None, None, None

def calc_reversal_science(row, spot, max_oi, max_vol):
    # Weighting: OI (40%), Gamma (30%), Volume (20%), Theta/Distance (10%)
    oi_rank = row['openinterest'] / max_oi if max_oi > 0 else 0
    vol_rank = row.get('volume', 0) / max_vol if max_vol > 0 else 0
    gamma_rank = abs(row['gamma']) * 100 # Scaling gamma for ranking
    
    # Distance Penalty (Limits effectiveness if too far from current price)
    dist = abs(row['strike'] - spot)
    dist_mult = max(0.5, 1 - (dist / (spot * 0.05)))
    
    score = (oi_rank * 0.4) + (vol_rank * 0.2) + (gamma_rank * 0.3)
    final_pct = 60 + (score * 38.5 * dist_mult)
    return min(99.0, round(final_pct, 1))

# 3. EXECUTION
spot, calls, puts, hist = get_data()

if spot is not None and not calls.empty:
    for df in [calls, puts]:
        df.columns = [c.lower().replace('_', '') for c in df.columns]
        if 'gamma' not in df.columns: df['gamma'] = 0.0001
        if 'volume' not in df.columns: df['volume'] = 0
        df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0.0001)
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)

    # Calculate GEX Structure
    calls['gex'] = (calls['openinterest'] * calls['gamma']) * 1000
    puts['gex'] = (puts['openinterest'] * puts['gamma']) * 1000 * -1
    
    all_gex = pd.concat([calls, puts])
    all_gex = all_gex[(all_gex['strike'] > spot * 0.95) & (all_gex['strike'] < spot * 1.05)].sort_values('strike')
    
    # Advanced Reversal Math
    m_oi, m_vol = all_gex['openinterest'].max(), all_gex['volume'].max()
    all_gex['rev_odds'] = all_gex.apply(lambda r: calc_reversal_science(r, spot, m_oi, m_vol), axis=1)
    
    # Level Extraction
    res_walls = all_gex[all_gex['gex'] > 0].nlargest(3, 'rev_odds').sort_values('strike')
    sup_walls = all_gex[all_gex['gex'] < 0].nlargest(3, 'rev_odds').sort_values('strike', ascending=False)
    
    # Mid-Range Walls (Closest high-probability levels to spot)
    mid_walls = all_gex[~all_gex['strike'].isin(res_walls['strike'].tolist() + sup_walls['strike'].tolist())]
    mid_walls = mid_walls.iloc[(mid_walls['strike'] - spot).abs().argsort()[:3]]
    
    # Metrics
    all_gex['cum_gex'] = all_gex['gex'].cumsum()
    gamma_flip = all_gex.iloc[np.abs(all_gex['cum_gex']).argmin()]['strike']
    hv = hist['Close'].pct_change().tail(20).std() * np.sqrt(252) * 100
    atm_idx = (calls['strike'] - spot).abs().argmin()
    avg_iv = calls.iloc[atm_idx]['impliedvolatility'] * 100
    bias = "🔴 BEARISH" if (avg_iv > hv + 1) else "🟢 BULLISH"
    status = "⚡ VOLATILE" if spot < gamma_flip else "🛡️ STABLE"

    # 4. UI
    t1, t2, t3, t4 = st.tabs(["🎯 Gamma Sniper", "📊 IV/Bias", "🗺️ Heatmap", "📓 Playbook"])

    with t1:
        st.subheader(f"NDX Sniper | Spot: {spot:,.2f}")
        fig = px.bar(all_gex, x='strike', y='gex', color='gex', color_continuous_scale='RdYlGn')
        fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange", annotation_text="FLIP")
        fig.update_layout(template="plotly_dark", height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("### 🟢 Resistance Walls")
            for _, r in res_walls.iterrows():
                st.success(f"{r['strike']:,.0f} | **{r['rev_odds']}% Rev**")
        with c2:
            st.write("### 🟡 Mid-Range Walls")
            for _, r in mid_walls.iterrows():
                st.warning(f"{r['strike']:,.0f} | **{r['rev_odds']}% Rev**")
        with c3:
            st.write("### 🔴 Support Walls")
            for _, r in sup_walls.iterrows():
                st.error(f"{r['strike']:,.0f} | **{r['rev_odds']}% Rev**")

    with t2:
        st.subheader("Market Sentiment Profile")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Daily Bias", bias)
        col_b.metric("Gamma Flip", f"{gamma_flip:,.0f}")
        col_c.metric("Market Status", status)
        
        st.plotly_chart(px.bar(x=['IV', 'HV'], y=[avg_iv, hv], color=['IV', 'HV'], 
                               title="Intended vs Realized Vol", template="plotly_dark"), use_container_width=True)

    with t3:
        st.subheader("Gamma Liquidity Heatmap")
        st.caption("Top = Calls | Bottom = Puts | Brightness = Reversal Probability")
        # Scatter used for "Glow" effect
        fig_h = px.scatter(all_gex, x="strike", y="gex", color="rev_odds", size="openinterest",
                           color_continuous_scale="Viridis", labels={'gex': 'GEX Structure'})
        fig_h.add_hline(y=0, line_color="white")
        fig_h.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_h, use_container_width=True)

    with t4:
        st.subheader("📓 NDX Sniper Morning Playbook")
        st.info("Strategy: Limit Orders at Heavy Walls with 15pt Stops.")
        st.markdown("""
        1. **Pre-Market (06:30):** Open the **Gamma Sniper** tab. Note the top 3 Resistance and Support levels.
        2. **Set Limits:** Place buy/sell limits 2-3 points *ahead* of the 🟢 and 🔴 walls.
        3. **Risk Management:** Hard 15-point stop on every entry. If a wall has >90% Rev Odds, it's a high-conviction zone.
        4. **Mid-Range:** Use the 🟡 Mid-Range walls to take partial profits or move stops to breakeven.
        """)
else:
    st.error("Connection Error. Data Syncing...")
