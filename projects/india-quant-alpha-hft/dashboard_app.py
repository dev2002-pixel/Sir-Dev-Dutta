"""Interactive quant trading + NSE/Reliance research dashboard.

Run from this directory:
    streamlit run dashboard_app.py
Market data uses Yahoo Finance via yfinance as a research proxy.
The pairs-trading panel uses deterministic synthetic sample data by default.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf

st.set_page_config(page_title="India Quant Desk", page_icon="📈", layout="wide")

BG = "#0B1220"
PANEL = "#111C2F"
GRID = "#263449"
TEXT = "#E7EEF8"
MUTED = "#93A4B8"
BLUE = "#56B4E9"
CYAN = "#39D0C8"
ORANGE = "#F4A261"
RED = "#E76F6A"
GREEN = "#55C595"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {font-family: 'Manrope', sans-serif;}
.stApp {background: #0B1220; color: #E7EEF8;}
[data-testid="stSidebar"] {background: #0E1929; border-right: 1px solid #263449;}
[data-testid="stMetric"] {background: #111C2F; border: 1px solid #263449; padding: 14px 16px; border-radius: 12px;}
[data-testid="stMetricLabel"] {color: #93A4B8;}
[data-testid="stMetricValue"] {color: #E7EEF8; font-family: 'DM Mono', monospace;}
h1,h2,h3 {letter-spacing: -0.035em;}
.hero {padding: 22px 26px; border: 1px solid #263449; border-radius: 16px;
background: linear-gradient(115deg,#14243A 0%,#101B2D 58%,#102B35 100%); margin-bottom: 18px;}
.eyebrow {color:#39D0C8; font: 500 11px 'DM Mono',monospace; letter-spacing:.16em; text-transform:uppercase;}
.hero h1 {font-size: 34px; margin: 7px 0 4px; color:#F4F7FB;}
.hero p {color:#A9B8CA; margin:0; font-size:14px;}
.section-kicker {color:#39D0C8; font:500 11px 'DM Mono',monospace; letter-spacing:.14em; text-transform:uppercase;}
.small-note {color:#93A4B8; font-size:12px;}
div[data-testid="stAlert"] {border-radius: 10px;}
.stTabs [data-baseweb="tab-list"] {gap: 8px; border-bottom:1px solid #263449;}
.stTabs [data-baseweb="tab"] {background:#111C2F; border-radius:8px 8px 0 0; padding:10px 18px;}
</style>
""", unsafe_allow_html=True)

PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Manrope, sans-serif", color=TEXT, size=11),
    margin=dict(l=12, r=12, t=42, b=12),
    hovermode="x unified",
    legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"),
)
COLORS = {"RELIANCE": CYAN, "NIFTY50": BLUE, "BANKNIFTY": ORANGE, "NIFTYENERGY": GREEN}

def polish(fig, height=340):
    fig.update_layout(**PLOT_LAYOUT, height=height)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID)
    return fig

def metric_row(items):
    cols = st.columns(len(items))
    for col, (label, value, delta) in zip(cols, items):
        col.metric(label, value, delta)

def synthetic_pair_data():
    rng = np.random.default_rng(17)
    n = 1500
    dates = pd.bdate_range("2019-01-01", periods=n)
    common = np.cumsum(rng.normal(0.00025, 0.009, n))
    spread = np.zeros(n)
    for i in range(1, n):
        spread[i] = 0.88 * spread[i - 1] + rng.normal(0, 0.006)
    return pd.DataFrame({
        "date": dates,
        "asset_a": np.exp(np.log(80.0) + 0.85 * common + spread),
        "asset_b": np.exp(np.log(100.0) + common),
    }).set_index("date")

MARKET_UNIVERSE = {
    "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "INFOSYS": "INFY.NS",
    "HDFC_BANK": "HDFCBANK.NS", "ICICI_BANK": "ICICIBANK.NS", "SBIN": "SBIN.NS",
    "AXIS_BANK": "AXISBANK.NS", "KOTAK_BANK": "KOTAKBANK.NS", "LT": "LT.NS",
    "ITC": "ITC.NS", "HINDUNILVR": "HINDUNILVR.NS", "BHARTI_AIRTEL": "BHARTIARTL.NS",
    "TATA_MOTORS": "TATAMOTORS.NS", "MARUTI": "MARUTI.NS", "SUN_PHARMA": "SUNPHARMA.NS",
    "NIFTY50": "^NSEI", "BANKNIFTY": "^NSEBANK", "NIFTYENERGY": "^CNXENERGY",
    "INDIA_VIX": "^INDIAVIX", "USDINR": "INR=X", "BRENT_CRUDE": "BZ=F",
    "WTI_CRUDE": "CL=F", "GOLD": "GC=F"
}

@st.cache_data(ttl=1800, show_spinner=False)
def download_market(start_date, end_date, selected_labels=None):
    labels = list(selected_labels) if selected_labels else ["RELIANCE", "NIFTY50", "BANKNIFTY", "NIFTYENERGY"]
    symbols = {label: MARKET_UNIVERSE[label] for label in labels if label in MARKET_UNIVERSE}
    series = {}
    for label, ticker in symbols.items():
        try:
            raw = yf.download(ticker, start=start_date, end=end_date,
                              auto_adjust=True, progress=False, threads=False)
            if raw.empty:
                continue
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            series[label] = close.rename(label)
        except Exception:
            continue
    if not series:
        return pd.DataFrame()
    return pd.concat(series.values(), axis=1).sort_index().dropna(how="all")


@st.cache_data(ttl=60, show_spinner=False)
def download_intraday(period, interval):
    """Download recent intraday bars from Yahoo Finance (research proxy, not exchange feed)."""
    symbols = {"RELIANCE": "RELIANCE.NS", "NIFTY50": "^NSEI",
               "BANKNIFTY": "^NSEBANK", "NIFTYENERGY": "^CNXENERGY"}
    frames = {}
    for label, ticker in symbols.items():
        try:
            raw = yf.download(ticker, period=period, interval=interval,
                              auto_adjust=True, progress=False, threads=False)
            if raw.empty or "Close" not in raw:
                continue
            close = raw["Close"]
            volume = raw["Volume"] if "Volume" in raw else None
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            frame = pd.DataFrame({"Close": close})
            if volume is not None:
                if isinstance(volume, pd.DataFrame):
                    volume = volume.iloc[:, 0]
                frame["Volume"] = volume
            frames[label] = frame.dropna(subset=["Close"])
        except Exception:
            continue
    return frames

def pairs_dashboard():
    st.markdown('<div class="section-kicker">01 / strategy research</div>', unsafe_allow_html=True)
    st.subheader("Statistical arbitrage · spread & execution monitor")
    data_source = "Deterministic synthetic sample"
    st.caption(f"Data source: {data_source}. Upload a CSV with date, asset_a and asset_b columns to run the same research workflow on your own historical pair. No live orders are sent.")
    uploaded = st.sidebar.file_uploader("Optional pairs CSV", type=["csv"], help="Required columns: date, asset_a, asset_b")
    data = synthetic_pair_data()
    if uploaded is not None:
        try:
            candidate = pd.read_csv(uploaded, parse_dates=["date"])
            required = {"date", "asset_a", "asset_b"}
            if not required.issubset(candidate.columns):
                st.sidebar.error("CSV needs date, asset_a and asset_b columns.")
            else:
                candidate = candidate[["date", "asset_a", "asset_b"]].dropna().set_index("date").sort_index()
                candidate = candidate.apply(pd.to_numeric, errors="coerce").dropna()
                candidate = candidate[(candidate > 0).all(axis=1)]
                if len(candidate) >= 80:
                    data = candidate
                    data_source = "User-uploaded historical data"
                else:
                    st.sidebar.warning("Need at least 80 valid positive price rows; using sample data.")
        except Exception as exc:
            st.sidebar.error(f"Could not read CSV: {exc}")
    left, right = st.columns([1, 3])
    with left:
        lookback = st.slider("Z-score lookback", 20, 180, 60, 5)
        entry = st.slider("Entry threshold", 1.0, 3.5, 2.0, 0.1)
        exit_level = st.slider("Exit threshold", 0.1, 1.5, 0.5, 0.1)
        fee_bps = st.slider("Turnover cost (bps)", 0, 20, 5)
        st.markdown("---")
        st.markdown("**Model specification**")
        st.markdown("- Training window: first 60%")
        st.markdown("- Hedge ratio: OLS log prices")
        st.markdown("- Mean reversion: z-score spread")
        st.markdown("- Position: one-bar execution lag")
    log_a = np.log(data["asset_a"])
    log_b = np.log(data["asset_b"])
    split = int(len(data) * 0.60)
    beta = np.polyfit(log_b.iloc[:split], log_a.iloc[:split], 1)[0]
    spread = log_a - beta * log_b
    mu = spread.rolling(lookback).mean()
    sigma = spread.rolling(lookback).std()
    z = (spread - mu) / sigma.replace(0, np.nan)
    raw_pos = pd.Series(0.0, index=data.index)
    state = 0.0
    for i, score in enumerate(z):
        if not np.isfinite(score):
            raw_pos.iloc[i] = state
            continue
        if state == 0 and score >= entry:
            state = -1.0
        elif state == 0 and score <= -entry:
            state = 1.0
        elif state != 0 and abs(score) <= exit_level:
            state = 0.0
        raw_pos.iloc[i] = state
    position = raw_pos.shift(1).fillna(0.0)
    spread_ret = spread.diff().fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    strat_ret = position * spread_ret - turnover * (fee_bps / 10000.0)
    equity = np.exp(strat_ret.cumsum())
    drawdown = equity / equity.cummax() - 1.0
    ann_vol = strat_ret.std() * np.sqrt(252)
    sharpe = (strat_ret.mean() * 252 / ann_vol) if ann_vol > 0 else np.nan
    total = equity.iloc[-1] - 1
    max_dd = drawdown.min()
    metric_row([
        ("TRAINING HEDGE RATIO", f"{beta:.3f}", "OLS · log prices"),
        ("SIMULATED TOTAL RETURN", f"{total:.1%}", "after modelled turnover cost"),
        ("ANNUALISED SHARPE", f"{sharpe:.2f}" if np.isfinite(sharpe) else "—", "252-session convention"),
        ("MAX DRAWDOWN", f"{max_dd:.1%}", "peak-to-trough"),
    ])
    with right:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.08,
                            row_heights=[.72,.28], subplot_titles=("Residual spread · rolling z-score", "Position state"))
        fig.add_trace(go.Scatter(x=z.index, y=z, name="Spread z-score", line=dict(color=CYAN, width=1.6)), row=1, col=1)
        fig.add_hline(y=entry, line_dash="dash", line_color=ORANGE, row=1, col=1)
        fig.add_hline(y=-entry, line_dash="dash", line_color=ORANGE, row=1, col=1)
        fig.add_hline(y=0, line_color=GRID, row=1, col=1)
        fig.add_trace(go.Scatter(x=position.index, y=position, name="Lagged position",
                                 line=dict(color=BLUE, width=1.5), fill="tozeroy"), row=2, col=1)
        polish(fig, 520)
        st.plotly_chart(fig, use_container_width=True)
    c1, c2 = st.columns(2)
    with c1:
        f = go.Figure()
        f.add_trace(go.Scatter(x=equity.index, y=equity, name="Strategy equity", line=dict(color=CYAN, width=2)))
        f.add_trace(go.Scatter(x=equity.index, y=np.exp(spread_ret.cumsum()), name="Unhedged spread proxy",
                               line=dict(color=MUTED, width=1, dash="dot")))
        f.update_layout(title="Growth of 1.0 · simulated", yaxis_title="Portfolio value")
        st.plotly_chart(polish(f), use_container_width=True)
    with c2:
        f = go.Figure()
        f.add_trace(go.Scatter(x=drawdown.index, y=drawdown * 100, name="Drawdown",
                               line=dict(color=RED, width=1.5), fill="tozeroy"))
        f.update_layout(title="Underwater curve", yaxis_title="Drawdown (%)")
        st.plotly_chart(polish(f), use_container_width=True)
    cost_bps = (turnover * fee_bps).cumsum()
    cost_fig = go.Figure()
    cost_fig.add_trace(go.Scatter(x=cost_bps.index, y=cost_bps, name="Cumulative turnover cost",
                                  line=dict(color=ORANGE, width=1.8), fill="tozeroy"))
    cost_fig.update_layout(title="Cumulative modelled turnover cost", yaxis_title="Basis points")
    st.plotly_chart(polish(cost_fig, 280), use_container_width=True)
    st.markdown("**Execution lens**")
    st.caption("This panel models turnover costs on a daily spread series. It does not model queue priority, partial fills, latency, exchange fees, taxes, or market impact from order-book depth. Treat all metrics as illustrative, not a performance claim.")


def risk_dashboard():
    st.markdown('<div class="section-kicker">03 / portfolio construction & risk</div>', unsafe_allow_html=True)
    st.subheader("Portfolio risk laboratory")
    st.caption("Build a weighted basket from downloaded market proxies, inspect portfolio risk and run transparent shock scenarios. Returns are historical estimates, not forecasts.")
    with st.sidebar:
        st.markdown("### Risk lab data controls")
        risk_start = st.date_input("Risk sample start", value=pd.Timestamp("2020-01-01").date(),
                                   min_value=pd.Timestamp("2010-01-01").date(), key="risk_start")
        risk_end = st.date_input("Risk sample end (exclusive)", value=pd.Timestamp.today().date() + pd.Timedelta(days=1), key="risk_end")
        risk_assets = st.multiselect("Download assets", list(MARKET_UNIVERSE), default=["RELIANCE","NIFTY50","BANKNIFTY","TCS","HDFC_BANK"], key="risk_assets")
        risk_refresh = st.button("Refresh risk data")
    if risk_refresh:
        download_market.clear()
    prices = download_market(str(risk_start), str(risk_end), risk_assets)
    if prices.empty or len(prices.columns) < 2:
        st.warning("Not enough market series were returned. Try a different date range or refresh.")
        return
    candidates = list(prices.columns)
    defaults = [x for x in ["RELIANCE", "NIFTY50", "BANKNIFTY"] if x in candidates]
    selected = st.multiselect("Portfolio constituents", candidates, default=defaults or candidates[:2])
    if not selected:
        st.info("Select at least one asset to construct a portfolio.")
        return
    usable = prices[selected].dropna(how="all").ffill().dropna()
    returns = np.log(usable / usable.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 30:
        st.warning("At least 30 overlapping daily observations are needed for stable descriptive risk estimates.")
        return
    st.markdown("#### Portfolio weights")
    st.caption("Set raw weights below. The dashboard normalises them to 100%; short positions are not enabled in this simple long-only lab.")
    raw_weights = {}
    weight_cols = st.columns(min(4, len(selected)))
    for i, asset in enumerate(selected):
        with weight_cols[i % len(weight_cols)]:
            raw_weights[asset] = st.slider(f"{asset} weight", 0, 100, int(100/len(selected)), 5, key=f"weight_{asset}")
    weight_sum = sum(raw_weights.values())
    if weight_sum == 0:
        st.error("At least one portfolio weight must be greater than zero.")
        return
    weights = pd.Series({k:v/weight_sum for k,v in raw_weights.items()})
    st.caption("Normalised weights: " + " · ".join(f"{k} {v:.0%}" for k,v in weights.items()))
    port_ret = returns[weights.index].mul(weights, axis=1).sum(axis=1)
    equity = np.exp(port_ret.cumsum())
    drawdown = equity / equity.cummax() - 1
    rf = st.slider("Annual risk-free rate (%)", 0.0, 10.0, 4.0, 0.25) / 100
    confidence = st.selectbox("VaR / CVaR confidence", [0.90, 0.95, 0.975, 0.99], index=1, format_func=lambda x:f"{x:.1%}")
    annual_vol = port_ret.std() * np.sqrt(252)
    annual_return = port_ret.mean() * 252
    sharpe = (annual_return-rf)/annual_vol if annual_vol > 0 else np.nan
    q = port_ret.quantile(1-confidence)
    hist_var = -q
    hist_cvar = -port_ret[port_ret <= q].mean() if (port_ret <= q).any() else np.nan
    z_scores = {0.90:1.2816,0.95:1.6449,0.975:1.9600,0.99:2.3263}
    param_var = -(port_ret.mean() - z_scores[confidence]*port_ret.std())
    total_return = equity.iloc[-1]-1
    max_dd = drawdown.min()
    benchmark = returns["NIFTY50"] if "NIFTY50" in returns else None
    beta = (port_ret.cov(benchmark)/benchmark.var()) if benchmark is not None and benchmark.var()>0 else np.nan
    metric_row([
        ("PORTFOLIO RETURN",f"{total_return:.1%}",f"{len(port_ret):,} daily observations"),
        ("ANNUALISED VOLATILITY",f"{annual_vol:.1%}","daily σ × √252"),
        ("SHARPE RATIO",f"{sharpe:.2f}" if np.isfinite(sharpe) else "—",f"RF {rf:.1%}"),
        ("MAX DRAWDOWN",f"{max_dd:.1%}","peak-to-trough"),
        ("HISTORICAL VaR",f"{hist_var:.2%}",f"1-day · {confidence:.1%} confidence"),
        ("HISTORICAL CVaR",f"{hist_cvar:.2%}","mean loss beyond VaR"),
    ])
    tab1, tab2, tab3 = st.tabs(["Performance & risk","Dependence & distribution","Stress testing & data"])
    with tab1:
        p1,p2=st.columns([1.5,1])
        with p1:
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=equity.index,y=equity,name="Portfolio growth",line=dict(color=CYAN,width=2)))
            fig.update_layout(title="Growth of 1.0 · weighted portfolio",yaxis_title="Portfolio value")
            st.plotly_chart(polish(fig,330),use_container_width=True)
        with p2:
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=drawdown.index,y=drawdown*100,name="Drawdown",line=dict(color=RED),fill="tozeroy"))
            fig.update_layout(title="Portfolio drawdown",yaxis_title="Drawdown (%)")
            st.plotly_chart(polish(fig,330),use_container_width=True)
        roll_window=st.select_slider("Rolling risk window",options=[20,40,60,90,120],value=60,key="risk_roll")
        rolling_vol=port_ret.rolling(roll_window).std()*np.sqrt(252)*100
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=rolling_vol.index,y=rolling_vol,name="Annualised rolling volatility",line=dict(color=ORANGE,width=1.8)))
        fig.update_layout(title=f"{roll_window}-session rolling annualised volatility",yaxis_title="Volatility (%)")
        st.plotly_chart(polish(fig,280),use_container_width=True)
        st.metric("Parametric normal VaR",f"{param_var:.2%}",f"1-day · {confidence:.1%} confidence")
        st.caption("Parametric VaR assumes normally distributed daily portfolio returns. Historical VaR uses the empirical return quantile. Neither captures all tail, liquidity or regime risks.")
    with tab2:
        corr=returns[weights.index].corr()
        left,right=st.columns(2)
        with left:
            fig=px.imshow(corr,text_auto=".2f",zmin=-1,zmax=1,color_continuous_scale="RdBu_r",aspect="auto",title="Constituent return correlation")
            fig.update_layout(coloraxis_showscale=False)
            st.plotly_chart(polish(fig,340),use_container_width=True)
        with right:
            fig=go.Figure()
            fig.add_trace(go.Histogram(x=port_ret*100,nbinsx=50,name="Daily returns",marker_color=BLUE))
            fig.add_vline(x=-hist_var*100,line_dash="dash",line_color=ORANGE,annotation_text="Historical VaR")
            fig.update_layout(title="Portfolio daily-return distribution",xaxis_title="Daily return (%)",yaxis_title="Frequency")
            st.plotly_chart(polish(fig,340),use_container_width=True)
        st.metric("Beta vs NIFTY 50",f"{beta:.2f}" if np.isfinite(beta) else "—","descriptive full-sample estimate")
        st.dataframe(corr.style.format("{:.3f}"),use_container_width=True)
    with tab3:
        st.markdown("#### One-day deterministic shock scenarios")
        shock_cols=st.columns(min(4,len(selected)))
        shocks={}
        for i,asset in enumerate(selected):
            with shock_cols[i % len(shock_cols)]:
                shocks[asset]=st.slider(f"{asset} shock (%)",-30,10, -10 if asset=="NIFTY50" else -12,1,key=f"shock_{asset}")
        scenario_return=sum(weights[a]*shocks[a]/100 for a in selected)
        capital=st.number_input("Illustrative portfolio capital",min_value=1000.0,value=1000000.0,step=50000.0)
        loss=capital*scenario_return
        metric_row([
            ("WEIGHTED SHOCK RETURN",f"{scenario_return:.2%}","one-day static shock"),
            ("SCENARIO P&L",f"{loss:,.0f}","in portfolio currency units"),
            ("PARAMETRIC VaR",f"{capital*param_var:,.0f}","one-day estimate"),
        ])
        st.caption("Shock P&L = capital × Σ(weight × asset shock). This is a transparent linear scenario, not a full repricing or liquidity stress test.")
        export=pd.DataFrame({"portfolio_return":port_ret,"equity":equity,"drawdown":drawdown})
        st.download_button("Download portfolio risk series (CSV)",export.to_csv().encode("utf-8"),
                           file_name="india_quant_portfolio_risk.csv",mime="text/csv")
        st.download_button("Download normalised weights (CSV)",weights.rename("weight").to_csv().encode("utf-8"),
                           file_name="india_quant_portfolio_weights.csv",mime="text/csv")


def data_explorer_dashboard():
    st.markdown('<div class="section-kicker">04 / cross-asset data terminal</div>', unsafe_allow_html=True)
    st.subheader("India & global markets · multi-asset data explorer")
    st.caption("Select equities, indices, FX, volatility and commodity proxies. Historical prices are fetched on demand; intraday availability varies by instrument.")
    c1,c2,c3=st.columns([1.2,1,1])
    with c1:
        chosen=st.multiselect("Choose instruments",list(MARKET_UNIVERSE),
            default=["RELIANCE","TCS","HDFC_BANK","NIFTY50","BANKNIFTY","INDIA_VIX","USDINR","BRENT_CRUDE"])
    with c2:
        start=st.date_input("History from",value=pd.Timestamp("2021-01-01").date(),key="explorer_start")
    with c3:
        end=st.date_input("History to (exclusive)",value=pd.Timestamp.today().date()+pd.Timedelta(days=1),key="explorer_end")
    if not chosen:
        st.info("Choose at least one instrument.")
        return
    if st.button("Fetch selected market data",type="primary"):
        download_market.clear()
    with st.spinner("Fetching selected instruments from Yahoo Finance…"):
        prices=download_market(str(start),str(end),chosen)
    if prices.empty:
        st.warning("No prices were returned. Some symbols may be unavailable or unsupported by the data provider.")
        return
    returns=np.log(prices.where(prices>0)).diff()
    valid_returns=returns.dropna(how="all")
    if valid_returns.empty:
        st.warning("The selected instruments do not have enough overlapping observations.")
        return
    latest=prices.ffill().iloc[-1]
    previous=prices.ffill().iloc[-2] if len(prices)>1 else latest
    cols=st.columns(min(4,len(prices.columns)))
    for i,name in enumerate(prices.columns):
        with cols[i%len(cols)]:
            change=(latest[name]/previous[name]-1)*100 if pd.notna(previous[name]) and previous[name]!=0 else np.nan
            st.metric(name,f"{latest[name]:,.2f}" if pd.notna(latest[name]) else "—",
                      f"{change:+.2f}% latest session" if np.isfinite(change) else "—")
    tab1,tab2,tab3=st.tabs(["Price & returns","Cross-asset relationships","Data quality & export"])
    with tab1:
        indexed=prices.div(prices.ffill().bfill().iloc[0]).mul(100)
        fig=go.Figure()
        for name in indexed.columns:
            fig.add_trace(go.Scatter(x=indexed.index,y=indexed[name],name=name,mode="lines"))
        fig.update_layout(title="Normalised price performance · start = 100",yaxis_title="Indexed level")
        st.plotly_chart(polish(fig,420),use_container_width=True)
        selected_return=st.selectbox("Return series for distribution",list(valid_returns.columns))
        fig=go.Figure()
        fig.add_trace(go.Histogram(x=valid_returns[selected_return].dropna()*100,nbinsx=50,name=selected_return))
        fig.update_layout(title=f"{selected_return} daily log-return distribution",xaxis_title="Daily log return (%)",yaxis_title="Frequency")
        st.plotly_chart(polish(fig,300),use_container_width=True)
    with tab2:
        aligned=valid_returns.dropna()
        if len(aligned)>=3 and len(aligned.columns)>=2:
            corr=aligned.corr()
            fig=px.imshow(corr,text_auto=".2f",zmin=-1,zmax=1,color_continuous_scale="RdBu_r",aspect="auto",title="Daily return correlation matrix")
            fig.update_layout(coloraxis_showscale=False)
            st.plotly_chart(polish(fig,430),use_container_width=True)
            rolling_n=st.select_slider("Rolling correlation window",options=[20,40,60,90,120],value=60,key="explorer_roll")
            pair=st.multiselect("Rolling correlation pair",list(aligned.columns),default=list(aligned.columns[:2]),max_selections=2)
            if len(pair)==2:
                rc=aligned[pair[0]].rolling(rolling_n).corr(aligned[pair[1]])
                fig=go.Figure()
                fig.add_trace(go.Scatter(x=rc.index,y=rc,name=f"{pair[0]} vs {pair[1]}",line=dict(color=CYAN,width=1.8)))
                fig.add_hline(y=0,line_color=GRID)
                fig.update_layout(title=f"{rolling_n}-session rolling correlation",yaxis=dict(range=[-1,1]))
                st.plotly_chart(polish(fig,290),use_container_width=True)
        else:
            st.info("Select at least two instruments with overlapping daily returns to view dependence.")
    with tab3:
        coverage=pd.DataFrame({
            "Ticker": [MARKET_UNIVERSE[x] for x in prices.columns],
            "First observation": [prices[x].first_valid_index() for x in prices.columns],
            "Last observation": [prices[x].last_valid_index() for x in prices.columns],
            "Valid prices": [int(prices[x].notna().sum()) for x in prices.columns],
            "Missing %": [float(prices[x].isna().mean()*100) for x in prices.columns]
        },index=prices.columns)
        st.dataframe(coverage.style.format({"Missing %":"{:.1f}%"}),use_container_width=True)
        st.download_button("Download selected prices CSV",prices.to_csv().encode("utf-8"),"india_quant_selected_prices.csv","text/csv")
        st.download_button("Download selected returns CSV",valid_returns.to_csv().encode("utf-8"),"india_quant_selected_returns.csv","text/csv")
        st.caption("Provider: Yahoo Finance via yfinance. Missing values and differing market calendars are retained; no synthetic observations are inserted.")
    st.caption("Ticker availability, history length, currency and trading calendars differ. Cross-asset comparisons are descriptive; commodity futures, FX and Indian equities are not interchangeable assets.")

def market_dashboard():
    st.markdown('<div class="section-kicker">02 / India market intelligence</div>', unsafe_allow_html=True)
    st.subheader("NSE · Reliance market-linkage terminal")
    st.caption("Compare Reliance with NIFTY 50, Bank NIFTY and NIFTY Energy. All market observations below are Yahoo Finance adjusted-price proxies.")

    st.markdown("### Live market pulse · intraday bars")
    live_col, interval_col, period_col, refresh_col = st.columns([1.15, 1, 1, 1])
    with live_col:
        live_enabled = st.toggle("Auto-refresh feed", value=True)
    with interval_col:
        intraday_interval = st.selectbox("Bar interval", ["1m", "5m", "15m", "60m"], index=1)
    period_map = {"1m": "1d", "5m": "5d", "15m": "1mo", "60m": "3mo"}
    with period_col:
        refresh_seconds = st.selectbox("Refresh cadence", [30, 60, 120, 300], index=1)
    with refresh_col:
        force_refresh = st.button("Pull latest bars", use_container_width=True)
    if live_enabled:
        st_autorefresh(interval=refresh_seconds * 1000, key="india_quant_live_refresh")
    if force_refresh:
        download_intraday.clear()
    intraday = download_intraday(period_map[intraday_interval], intraday_interval)
    available = [name for name in ["RELIANCE", "NIFTY50", "BANKNIFTY", "NIFTYENERGY"] if name in intraday and not intraday[name].empty]
    if available:
        latest_cols = st.columns(len(available))
        for col, name in zip(latest_cols, available):
            frame = intraday[name]
            last = float(frame["Close"].iloc[-1])
            previous = float(frame["Close"].iloc[-2]) if len(frame) > 1 else last
            change = (last / previous - 1) * 100 if previous else 0
            col.metric(name, f"{last:,.2f}", f"{change:+.2f}% · last bar")
        live_prices = pd.concat({name: intraday[name]["Close"].rename(name) for name in available}, axis=1)
        live_indexed = live_prices / live_prices.ffill().bfill().iloc[0] * 100
        live_fig = go.Figure()
        for name in available:
            live_fig.add_trace(go.Scatter(x=live_indexed.index, y=live_indexed[name],
                                          name=name, line=dict(color=COLORS.get(name, MUTED), width=1.8)))
        live_fig.update_layout(title=f"Intraday relative move · {intraday_interval} bars · rebased to 100",
                               yaxis_title="Indexed price")
        st.plotly_chart(polish(live_fig, 300), use_container_width=True)
        latest_stamp = max(frame.index.max() for frame in intraday.values() if not frame.empty)
        st.caption(f"Latest bar timestamp returned by provider: {latest_stamp}. Provider: Yahoo Finance. Auto-refresh: {'ON' if live_enabled else 'OFF'} · every {refresh_seconds}s.")
    else:
        st.warning("No intraday bars returned. The provider may be closed, rate-limited, or unavailable for one or more symbols. Try 5m/15m bars or refresh later.")
    st.caption("Data-integrity note: this is a periodically refreshed Yahoo Finance feed, not guaranteed real-time exchange data. Intraday history and availability vary by ticker and provider; values may be delayed, missing or revised.")
    with st.sidebar:
        st.markdown("### Market data controls")
        start = st.date_input("Start date", value=pd.Timestamp("2020-01-01").date(),
                              min_value=pd.Timestamp("2010-01-01").date())
        end = st.date_input("End date (exclusive)", value=pd.Timestamp.today().date() + pd.Timedelta(days=1))
        market_assets = st.multiselect("Market series", list(MARKET_UNIVERSE), default=["RELIANCE","NIFTY50","BANKNIFTY","NIFTYENERGY"])
        window = st.select_slider("Rolling correlation window", options=[20, 40, 60, 90, 120], value=60)
        refresh = st.button("Refresh market data")
    if refresh:
        download_market.clear()
    prices = download_market(str(start), str(end), market_assets)
    if prices.empty or "RELIANCE" not in prices or "NIFTY50" not in prices:
        st.warning("Market data could not be downloaded for the selected period. Check connectivity/ticker availability. The NSE module can also read a local prices CSV.")
        return
    returns = np.log(prices.where(prices > 0)).diff().dropna(how="all")
    markets = [c for c in ["NIFTY50", "BANKNIFTY", "NIFTYENERGY"] if c in returns]
    complete = returns[["RELIANCE"] + markets].dropna()
    if complete.empty:
        st.warning("Not enough overlapping observations for this date range.")
        return
    ril_total = (np.exp(returns["RELIANCE"].dropna().sum()) - 1) * 100
    nifty_total = (np.exp(returns["NIFTY50"].dropna().sum()) - 1) * 100
    corr = complete.corr()
    beta = {}
    for market in markets:
        fit = np.polyfit(complete["RELIANCE"], complete[market], 1)
        beta[market] = fit[0]
    metric_row([
        ("RELIANCE CUMULATIVE RETURN", f"{ril_total:.1f}%", f"selected period"),
        ("NIFTY 50 CUMULATIVE RETURN", f"{nifty_total:.1f}%", "selected period"),
        ("RELIANCE–NIFTY CORRELATION", f"{corr.loc['RELIANCE','NIFTY50']:.2f}", f"{len(complete):,} sessions"),
        ("NIFTY BETA TO RELIANCE", f"{beta.get('NIFTY50',np.nan):.2f}", "OLS descriptive estimate"),
    ])
    normalized = prices[["RELIANCE"] + markets].dropna(how="all")
    normalized = normalized / normalized.dropna().iloc[0] * 100
    f = go.Figure()
    for col in normalized.columns:
        f.add_trace(go.Scatter(x=normalized.index, y=normalized[col], name=col,
                               line=dict(color=COLORS.get(col, MUTED), width=2)))
    f.update_layout(title="Relative performance · indexed to 100", yaxis_title="Index level")
    st.plotly_chart(polish(f, 390), use_container_width=True)
    a, b = st.columns(2)
    with a:
        rolling = returns["RELIANCE"].rolling(window).corr(returns["NIFTY50"])
        f = go.Figure()
        f.add_trace(go.Scatter(x=rolling.index, y=rolling, name=f"{window}-session correlation",
                               line=dict(color=CYAN, width=1.8), fill="tozeroy"))
        f.add_hline(y=0, line_color=GRID)
        f.update_layout(title=f"Reliance ↔ NIFTY 50 · {window}-session rolling correlation",
                        yaxis=dict(title="Correlation", range=[-1,1]))
        st.plotly_chart(polish(f, 330), use_container_width=True)
    with b:
        f = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                      aspect="auto", title="Return correlation matrix")
        f.update_layout(coloraxis_showscale=False)
        st.plotly_chart(polish(f, 330), use_container_width=True)
    c, d = st.columns(2)
    with c:
        x = complete["RELIANCE"] * 100
        f = go.Figure()
        f.add_trace(go.Scatter(x=x, y=complete["NIFTY50"] * 100, mode="markers",
                               marker=dict(color=CYAN, opacity=.42, size=5), name="Daily returns"))
        line_x = np.linspace(x.min(), x.max(), 100)
        intercept = complete["NIFTY50"].mean() - beta["NIFTY50"] * complete["RELIANCE"].mean()
        f.add_trace(go.Scatter(x=line_x, y=(intercept + beta["NIFTY50"]*line_x/100)*100,
                               name=f"OLS fit · β={beta['NIFTY50']:.2f}",
                               line=dict(color=ORANGE, width=2)))
        f.update_layout(title="Daily return relationship", xaxis_title="Reliance return (%)",
                        yaxis_title="NIFTY 50 return (%)")
        st.plotly_chart(polish(f, 330), use_container_width=True)
    with d:
        rows = []
        for market in markets:
            for lag in [0,1,2,3,5]:
                pair = pd.concat([returns[market], returns["RELIANCE"].shift(lag)], axis=1).dropna()
                if len(pair) < 30:
                    continue
                slope = np.polyfit(pair.iloc[:,1], pair.iloc[:,0], 1)[0]
                rows.append({"Market":market, "Reliance lead (sessions)":lag, "OLS beta":slope})
        if rows:
            lag_df = pd.DataFrame(rows)
            f = px.line(lag_df, x="Reliance lead (sessions)", y="OLS beta", color="Market",
                        markers=True, title="Lead–lag sensitivity · descriptive OLS")
            st.plotly_chart(polish(f, 330), use_container_width=True)
        else:
            st.info("Insufficient observations for lag analysis.")
    st.markdown("**What this does — and does not — tell you**")
    st.caption("Correlation and beta describe co-movement, not causation. A lagged coefficient is not automatically tradable alpha. Mechanical NIFTY contribution requires date-matched official free-float constituent weights; no historical weight is invented in this dashboard.")
    st.dataframe(corr.style.format("{:.3f}"), use_container_width=True)

st.markdown("""
<div class="hero">
  <div class="eyebrow">DEV DUTTA · QUANTITATIVE RESEARCH LAB</div>
  <h1>INDIA QUANT DESK</h1>
  <p>Systematic strategies · execution research · NSE market structure · Reliance market linkage</p>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("## INDIA QUANT DESK")
st.sidebar.caption("Research terminal · educational build")
page = st.sidebar.radio("Workspace", ["Trading & HFT", "NSE × Reliance", "Portfolio & Risk Lab", "Multi-Asset Data Explorer"])
st.sidebar.markdown("---")
st.sidebar.caption("DATA INTEGRITY")
st.sidebar.caption("Synthetic strategy sample · Yahoo Finance market proxy · no live execution")
if page == "Trading & HFT":
    pairs_dashboard()
elif page == "NSE × Reliance":
    market_dashboard()
elif page == "Portfolio & Risk Lab":
    risk_dashboard()
else:
    data_explorer_dashboard()
st.markdown("---")
st.markdown('<div class="small-note">RESEARCH ONLY · Not investment advice · Not a live trading system · Validate with licensed exchange data before drawing market conclusions.</div>', unsafe_allow_html=True)
