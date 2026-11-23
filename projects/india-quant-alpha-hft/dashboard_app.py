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

@st.cache_data(ttl=1800, show_spinner=False)
def download_market(start_date, end_date):
    symbols = {"RELIANCE": "RELIANCE.NS", "NIFTY50": "^NSEI",
               "BANKNIFTY": "^NSEBANK", "NIFTYENERGY": "^CNXENERGY"}
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

def pairs_dashboard():
    st.markdown('<div class="section-kicker">01 / strategy research</div>', unsafe_allow_html=True)
    st.subheader("Statistical arbitrage · spread & execution monitor")
    st.caption(f"Data source: {data_source}. Upload a CSV with date, asset_a and asset_b columns to run the same research workflow on your own historical pair. No live orders are sent.")
    uploaded = st.sidebar.file_uploader("Optional pairs CSV", type=["csv"], help="Required columns: date, asset_a, asset_b")
    data_source = "Deterministic synthetic sample"
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

def market_dashboard():
    st.markdown('<div class="section-kicker">02 / India market intelligence</div>', unsafe_allow_html=True)
    st.subheader("NSE · Reliance market-linkage terminal")
    st.caption("Compare Reliance with NIFTY 50, Bank NIFTY and NIFTY Energy. All market observations below are Yahoo Finance adjusted-price proxies.")
    with st.sidebar:
        st.markdown("### Market data controls")
        start = st.date_input("Start date", value=pd.Timestamp("2020-01-01").date(),
                              min_value=pd.Timestamp("2010-01-01").date())
        end = st.date_input("End date (exclusive)", value=pd.Timestamp.today().date() + pd.Timedelta(days=1))
        window = st.select_slider("Rolling correlation window", options=[20, 40, 60, 90, 120], value=60)
        refresh = st.button("Refresh market data")
    if refresh:
        download_market.clear()
    prices = download_market(str(start), str(end))
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
page = st.sidebar.radio("Workspace", ["Trading & HFT", "NSE × Reliance"])
st.sidebar.markdown("---")
st.sidebar.caption("DATA INTEGRITY")
st.sidebar.caption("Synthetic strategy sample · Yahoo Finance market proxy · no live execution")
if page == "Trading & HFT":
    pairs_dashboard()
else:
    market_dashboard()
st.markdown("---")
st.markdown('<div class="small-note">RESEARCH ONLY · Not investment advice · Not a live trading system · Validate with licensed exchange data before drawing market conclusions.</div>', unsafe_allow_html=True)
