"""Interactive quant trading + NSE/Reliance research dashboard.

Run from this directory:
    streamlit run dashboard_app.py
Market data uses Yahoo Finance via yfinance as a research proxy.
The pairs-trading panel uses deterministic synthetic sample data by default.
"""
from __future__ import annotations

from pathlib import Path
import io
import zipfile
import os
from datetime import datetime, timezone
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import yfinance as yf
from stochastic_astro_lab import stochastic_astro_dashboard

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
    "WTI_CRUDE": "CL=F", "GOLD": "GC=F",
    "SP500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI", "RUSSELL2000": "^RUT", "VIX": "^VIX",
    "AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA", "AMZN": "AMZN", "GOOGL": "GOOGL",
    "META": "META", "JPM": "JPM", "TSLA": "TSLA", "SPY": "SPY", "QQQ": "QQQ",
    "DXY": "DX-Y.NYB", "EURUSD": "EURUSD=X", "USDJPY": "JPY=X"
}

@st.cache_data(ttl=900, show_spinner=False)
def download_market(start_date, end_date, selected_labels=None):
    """Bulk-download Yahoo Finance adjusted closes; tolerate yfinance column layouts."""
    labels = list(selected_labels) if selected_labels else ["RELIANCE", "NIFTY50", "BANKNIFTY", "NIFTYENERGY"]
    symbols = {label: MARKET_UNIVERSE[label] for label in labels if label in MARKET_UNIVERSE}
    if not symbols:
        return pd.DataFrame()
    try:
        raw = yf.download(
            tickers=list(symbols.values()), start=start_date, end=end_date,
            auto_adjust=True, progress=False, threads=True, group_by="column",
            actions=False
        )
        if raw is None or raw.empty:
            return pd.DataFrame()
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if isinstance(close, pd.Series):
            close = close.to_frame(name=list(symbols)[0])
        elif isinstance(close.columns, pd.MultiIndex):
            close.columns = close.columns.get_level_values(-1)
        reverse = {ticker: label for label, ticker in symbols.items()}
        close = close.rename(columns=reverse)
        # Single-ticker Yahoo responses may use the ticker as the sole column.
        if len(close.columns) == 1 and close.columns[0] not in symbols:
            close.columns = [next(iter(symbols))]
        close = close[[col for col in symbols if col in close.columns]]
        close = close.apply(pd.to_numeric, errors="coerce")
        close.index = pd.to_datetime(close.index)
        if close.index.tz is not None:
            close.index = close.index.tz_localize(None)
        return close.sort_index().dropna(how="all")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def download_ohlcv(label, period_start, period_end):
    """Download one Yahoo Finance instrument's adjusted OHLCV history for charting."""
    ticker = MARKET_UNIVERSE.get(label)
    if not ticker:
        return pd.DataFrame()
    try:
        raw = yf.download(ticker, start=period_start, end=period_end,
                          auto_adjust=True, progress=False, threads=False)
        if raw is None or raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        keep = [col for col in ["Open", "High", "Low", "Close", "Volume"] if col in raw.columns]
        frame = raw[keep].copy()
        frame.index = pd.to_datetime(frame.index)
        if frame.index.tz is not None:
            frame.index = frame.index.tz_localize(None)
        return frame.sort_index().dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


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


def risk_dashboard(region="INR"):
    is_us = region == "USD"
    region_assets = (["SP500","NASDAQ","DOW","RUSSELL2000","VIX","AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","TSLA","SPY","QQQ"] if is_us else ["RELIANCE","TCS","INFOSYS","HDFC_BANK","ICICI_BANK","SBIN","AXIS_BANK","KOTAK_BANK","LT","ITC","HINDUNILVR","BHARTI_AIRTEL","TATA_MOTORS","MARUTI","SUN_PHARMA","NIFTY50","BANKNIFTY","NIFTYENERGY","INDIA_VIX"])
    st.markdown('<div class="section-kicker">03 / portfolio construction & risk</div>', unsafe_allow_html=True)
    st.subheader(f"{region} portfolio risk laboratory")
    st.caption("Build a weighted basket from downloaded market proxies, inspect portfolio risk and run transparent shock scenarios. Returns are historical estimates, not forecasts.")
    with st.sidebar:
        st.markdown("### Risk lab data controls")
        risk_start = st.date_input("Risk sample start", value=pd.Timestamp("2020-01-01").date(),
                                   min_value=pd.Timestamp("2010-01-01").date(), key=f"risk_start_{region}")
        risk_end = st.date_input("Risk sample end (exclusive)", value=pd.Timestamp.today().date() + pd.Timedelta(days=1), key=f"risk_end_{region}")
        risk_defaults = ["SP500","NASDAQ","AAPL","MSFT","NVDA"] if is_us else ["RELIANCE","NIFTY50","BANKNIFTY","TCS","HDFC_BANK"]
        risk_assets = st.multiselect(f"Download {region} assets", region_assets, default=risk_defaults, key=f"risk_assets_{region}")
        risk_refresh = st.button("Refresh risk data")
    if risk_refresh:
        download_market.clear()
    prices = download_market(str(risk_start), str(risk_end), risk_assets)
    if prices.empty or len(prices.columns) < 2:
        st.warning("Not enough market series were returned. Try a different date range or refresh.")
        return
    candidates = list(prices.columns)
    defaults = [x for x in (["SP500","NASDAQ","AAPL"] if is_us else ["RELIANCE","NIFTY50","BANKNIFTY"]) if x in candidates]
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
            raw_weights[asset] = st.slider(f"{asset} weight", 0, 100, int(100/len(selected)), 5, key=f"weight_{region}_{asset}")
    weight_sum = sum(raw_weights.values())
    if weight_sum == 0:
        st.error("At least one portfolio weight must be greater than zero.")
        return
    weights = pd.Series({k:v/weight_sum for k,v in raw_weights.items()})
    st.caption("Normalised weights: " + " · ".join(f"{k} {v:.0%}" for k,v in weights.items()))

    # INR contribution calculator: existing portfolio value + proposed new money.
    currency = "USD" if is_us else "INR"
    symbol = "$" if is_us else "₹"
    st.markdown(f"#### {currency} portfolio contribution calculator")
    st.caption(f"Model how fresh capital changes {currency} exposure and constituent weights. Only same-currency equities are eligible for the contribution calculator.")
    equity_set = ({"AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","TSLA","SPY","QQQ"} if is_us else {"RELIANCE","TCS","INFOSYS","HDFC_BANK","ICICI_BANK","SBIN","AXIS_BANK","KOTAK_BANK","LT","ITC","HINDUNILVR","BHARTI_AIRTEL","TATA_MOTORS","MARUTI","SUN_PHARMA"})
    equity_assets = [a for a in selected if a in equity_set]
    if equity_assets:
        calc_left, calc_right = st.columns(2)
        with calc_left:
            existing_capital = st.number_input(
                f"Current portfolio value ({currency})", min_value=0.0, value=1000000.0,
                step=50000.0, format="%.2f", key="contrib_existing_capital"
            )
        with calc_right:
            new_money = st.number_input(
                f"New money to invest ({currency})", min_value=0.0, value=100000.0,
                step=10000.0, format="%.2f", key="contrib_new_money"
            )
        allocation_method = st.selectbox(
            "How should the new money be allocated?",
            ["Maintain current stock weights", "Equal-weight selected stocks", "Custom allocation"],
            key="contrib_allocation_method"
        )
        if allocation_method == "Maintain current stock weights":
            equity_base = weights.reindex(equity_assets).fillna(0.0)
            allocation = equity_base / equity_base.sum() if equity_base.sum() > 0 else pd.Series(1/len(equity_assets), index=equity_assets)
        elif allocation_method == "Equal-weight selected stocks":
            allocation = pd.Series(1/len(equity_assets), index=equity_assets)
        else:
            st.caption("Set the relative split for the new contribution. These inputs are normalised to 100%.")
            custom_raw = {}
            custom_cols = st.columns(min(4, len(equity_assets)))
            for j, asset in enumerate(equity_assets):
                with custom_cols[j % len(custom_cols)]:
                    custom_raw[asset] = st.slider(
                        f"New {asset} allocation", 0, 100, int(100/len(equity_assets)),
                        5, key=f"contrib_alloc_{asset}"
                    )
            custom_total = sum(custom_raw.values())
            allocation = (pd.Series(custom_raw, dtype=float) / custom_total
                          if custom_total > 0 else pd.Series(1/len(equity_assets), index=equity_assets))
        if existing_capital + new_money <= 0:
            st.info("Enter a current portfolio value or a new investment amount to calculate post-investment weights.")
        else:
            contribution = pd.Series(0.0, index=selected)
            contribution.loc[equity_assets] = allocation * new_money
            current_values = weights * existing_capital
            post_values = current_values.add(contribution, fill_value=0.0)
            post_weights = post_values / (existing_capital + new_money)
            old_port_ret = returns[weights.index].mul(weights, axis=1).sum(axis=1)
            post_port_ret = returns[post_weights.index].mul(post_weights, axis=1).sum(axis=1)
            old_vol = old_port_ret.std() * np.sqrt(252)
            post_vol = post_port_ret.std() * np.sqrt(252)
            old_var = -old_port_ret.quantile(0.05)
            post_var = -post_port_ret.quantile(0.05)
            old_ann_return = old_port_ret.mean() * 252
            post_ann_return = post_port_ret.mean() * 252
            latest_prices = usable.iloc[-1].reindex(selected)
            calc_table = pd.DataFrame({
                "Current weight (%)": weights * 100,
                f"New money ({currency})": contribution,
                "New money allocation (%)": (contribution / new_money * 100) if new_money > 0 else 0.0,
                f"Post-investment value ({currency})": post_values,
                "Post-investment weight (%)": post_weights * 100,
                "Weight change (pp)": (post_weights - weights) * 100,
                "Latest price (provider units)": latest_prices,
                "Indicative added units": contribution / latest_prices.replace(0, np.nan)
            })
            st.markdown("**Post-investment allocation impact**")
            st.dataframe(calc_table.style.format({
                "Current weight (%)":"{:.2f}", f"New money ({currency})":symbol+"{:,.2f}",
                "New money allocation (%)":"{:.2f}", f"Post-investment value ({currency})":symbol+"{:,.2f}",
                "Post-investment weight (%)":"{:.2f}", "Weight change (pp)":"{:+.2f}",
                "Latest price (provider units)":"{:,.2f}", "Indicative added units":"{:,.2f}"
            }, na_rep="—"), use_container_width=True)
            st.markdown("**Estimated portfolio-level effect**")
            metric_row([
                ("TOTAL CAPITAL AFTER INVESTMENT", f"{symbol}{existing_capital + new_money:,.2f}", f"New contribution {symbol}{new_money:,.2f}"),
                ("ANNUALISED VOLATILITY", f"{post_vol:.2%}", f"{post_vol-old_vol:+.2%} vs current mix"),
                ("HISTORICAL 95% VaR", f"{post_var:.2%}", f"{post_var-old_var:+.2%} vs current mix"),
                ("HISTORICAL ANNUALISED RETURN", f"{post_ann_return:.2%}", f"{post_ann_return-old_ann_return:+.2%} vs current mix"),
            ])
            fig_alloc = go.Figure()
            fig_alloc.add_trace(go.Bar(name="Before", x=selected, y=weights.reindex(selected).fillna(0)*100))
            fig_alloc.add_trace(go.Bar(name="After contribution", x=selected, y=post_weights.reindex(selected).fillna(0)*100))
            fig_alloc.update_layout(title="Constituent weights · before vs after investment",
                                    yaxis_title="Portfolio weight (%)", barmode="group")
            st.plotly_chart(polish(fig_alloc, 340), use_container_width=True)
            st.download_button(
                f"Download {currency} contribution analysis (CSV)",
                calc_table.round(2).to_csv(index=True).encode("utf-8"),
                file_name=f"{region.lower()}_contribution_analysis.csv", mime="text/csv"
            )
            st.caption(f"Indicative units = {currency} allocation ÷ latest downloaded price. This is a sizing estimate, not an order; it excludes lot sizes, brokerage, taxes, slippage, liquidity and price movement. Historical risk/return estimates are not forecasts.")
    else:
        st.info("Select at least one individual equity from the selected market to use its currency-specific contribution calculator.")
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
    benchmark_name = "SP500" if is_us else "NIFTY50"
    benchmark = returns[benchmark_name] if benchmark_name in returns else None
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
        st.metric(f"Beta vs {benchmark_name}",f"{beta:.2f}" if np.isfinite(beta) else "—","descriptive full-sample estimate")
        st.dataframe(corr.style.format("{:.3f}"),use_container_width=True)
    with tab3:
        st.markdown("#### One-day deterministic shock scenarios")
        shock_cols=st.columns(min(4,len(selected)))
        shocks={}
        for i,asset in enumerate(selected):
            with shock_cols[i % len(shock_cols)]:
                shocks[asset]=st.slider(f"{asset} shock (%)",-30,10, -10 if asset=="NIFTY50" else -12,1,key=f"shock_{region}_{asset}")
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


def data_explorer_dashboard(region="INR"):
    is_us = region == "USD"
    explorer_universe = (["SP500","NASDAQ","DOW","RUSSELL2000","VIX","AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","TSLA","SPY","QQQ","DXY","EURUSD","USDJPY"] if is_us else ["RELIANCE","TCS","INFOSYS","HDFC_BANK","ICICI_BANK","SBIN","AXIS_BANK","KOTAK_BANK","LT","ITC","HINDUNILVR","BHARTI_AIRTEL","TATA_MOTORS","MARUTI","SUN_PHARMA","NIFTY50","BANKNIFTY","NIFTYENERGY","INDIA_VIX","USDINR","BRENT_CRUDE","WTI_CRUDE","GOLD"])
    st.markdown('<div class="section-kicker">04 / cross-asset data terminal</div>', unsafe_allow_html=True)
    st.subheader(f"{region} market data & analytics")
    st.caption("Yahoo Finance · adjusted daily prices · fetched on demand and cached for 15 minutes.")
    with st.container(border=True):
        c1,c2,c3=st.columns([1.4,1,1])
        with c1:
            chosen=st.multiselect(f"{region} instruments",explorer_universe,
                default=(["SP500","NASDAQ","AAPL","MSFT","NVDA","VIX","DXY"] if is_us else ["RELIANCE","TCS","HDFC_BANK","NIFTY50","BANKNIFTY","INDIA_VIX","USDINR","BRENT_CRUDE"]),key=f"explorer_assets_{region}")
        with c2:
            start=st.date_input("From",value=pd.Timestamp("2021-01-01").date(),key=f"explorer_start_{region}")
        with c3:
            end=st.date_input("To (exclusive)",value=pd.Timestamp.today().date()+pd.Timedelta(days=1),key=f"explorer_end_{region}")
        refresh=st.button("↻ Refresh Yahoo Finance data",type="primary",use_container_width=True)
    if start >= end:
        st.error("The start date must be earlier than the end date.")
        return
    if not chosen:
        st.info("Choose at least one instrument.")
        return
    if refresh:
        download_market.clear()
        download_ohlcv.clear()
    with st.spinner("Requesting market data from Yahoo Finance…"):
        prices=download_market(str(start),str(end),chosen)
    if prices.empty:
        st.warning("Yahoo Finance returned no data for this selection. Check ticker availability, date range or provider rate limits.")
        return
    available=list(prices.columns)
    if not available:
        st.warning("No selected instruments returned valid price history.")
        return
    prices=prices[available].sort_index()
    returns=np.log(prices.where(prices>0)).diff()
    latest=prices.ffill().iloc[-1]
    prev=prices.ffill().iloc[-2] if len(prices)>1 else latest
    st.markdown("#### Latest available observations")
    metric_cols=st.columns(min(4,len(available)))
    for i,name in enumerate(available):
        with metric_cols[i%len(metric_cols)]:
            change=(latest[name]/prev[name]-1)*100 if pd.notna(prev[name]) and prev[name]!=0 else np.nan
            metric_cols[i%len(metric_cols)].metric(name,f"{latest[name]:,.2f}" if pd.notna(latest[name]) else "—",
                f"{change:+.2f}% · last observation" if np.isfinite(change) else "—")
    last_stamp=prices.dropna(how="all").index[-1]
    st.caption(f"Last common dataset timestamp: {last_stamp:%Y-%m-%d} · Retrieved from Yahoo Finance on app request. Prices are not guaranteed live.")
    tab_price,tab_compare,tab_stats,tab_data=st.tabs(["Price chart","Compare & relationships","Performance & risk","Data & downloads"])
    with tab_price:
        left,right=st.columns([1.2,1])
        with left:
            chart_asset=st.selectbox("Instrument detail",available,key="detail_asset")
        with right:
            chart_style=st.selectbox("Chart type",["Candlestick","Line"],key="detail_chart")
        detail=download_ohlcv(chart_asset,str(start),str(end))
        if detail.empty:
            st.info("OHLC data is unavailable for this instrument. Showing adjusted close instead.")
            detail=pd.DataFrame({"Close":prices[chart_asset]})
        ma_fast=st.slider("Fast moving average",5,100,20,5,key="ma_fast")
        ma_slow=st.slider("Slow moving average",20,250,50,5,key="ma_slow")
        fig=go.Figure()
        if chart_style=="Candlestick" and {"Open","High","Low","Close"}.issubset(detail.columns):
            fig.add_trace(go.Candlestick(x=detail.index,open=detail["Open"],high=detail["High"],
                low=detail["Low"],close=detail["Close"],name=chart_asset))
        else:
            fig.add_trace(go.Scatter(x=detail.index,y=detail["Close"],name="Adjusted close",
                line=dict(color=CYAN,width=2)))
        fig.add_trace(go.Scatter(x=detail.index,y=detail["Close"].rolling(ma_fast).mean(),
            name=f"SMA {ma_fast}",line=dict(color=ORANGE,width=1.3)))
        fig.add_trace(go.Scatter(x=detail.index,y=detail["Close"].rolling(ma_slow).mean(),
            name=f"SMA {ma_slow}",line=dict(color=BLUE,width=1.3)))
        fig.update_layout(title=f"{chart_asset} · price and moving averages",xaxis_rangeslider_visible=False,
            yaxis_title="Adjusted price · provider currency")
        st.plotly_chart(polish(fig,440),use_container_width=True)
        if "Volume" in detail and detail["Volume"].notna().any():
            vf=go.Figure(go.Bar(x=detail.index,y=detail["Volume"],name="Volume",marker_color=BLUE))
            vf.update_layout(title=f"{chart_asset} · reported volume",yaxis_title="Volume")
            st.plotly_chart(polish(vf,220),use_container_width=True)
        else:
            st.caption("Volume is not available for this symbol.")
    with tab_compare:
        st.markdown("#### Relative performance")
        base=prices.dropna(how="all").ffill()
        rebased=base.div(base.apply(lambda s:s.dropna().iloc[0] if s.notna().any() else np.nan)).mul(100)
        fig=go.Figure()
        for name in available:
            fig.add_trace(go.Scatter(x=rebased.index,y=rebased[name],name=name,mode="lines"))
        fig.update_layout(title="Growth of 100 · rebased to each instrument's first valid observation",
            yaxis_title="Indexed value")
        st.plotly_chart(polish(fig,400),use_container_width=True)
        aligned=returns[available].dropna()
        if len(aligned)>=3 and len(available)>=2:
            corr=aligned.corr()
            left,right=st.columns(2)
            with left:
                heat=px.imshow(corr,text_auto=".2f",zmin=-1,zmax=1,color_continuous_scale="RdBu_r",
                    aspect="auto",title="Daily return correlation")
                heat.update_layout(coloraxis_showscale=False)
                st.plotly_chart(polish(heat,360),use_container_width=True)
            with right:
                pair=st.multiselect("Rolling correlation pair",available,default=available[:2],max_selections=2,key="rolling_pair")
                window=st.select_slider("Rolling window (sessions)",[20,40,60,90,120],value=60,key="rolling_window")
                if len(pair)==2:
                    rc=returns[pair[0]].rolling(window).corr(returns[pair[1]])
                    rf=go.Figure(go.Scatter(x=rc.index,y=rc,name="Rolling correlation",
                        line=dict(color=CYAN,width=1.8),fill="tozeroy"))
                    rf.update_layout(title=f"{pair[0]} vs {pair[1]} · {window}-session rolling correlation",
                        yaxis=dict(range=[-1,1]))
                    st.plotly_chart(polish(rf,330),use_container_width=True)
        else:
            st.info("Select at least two instruments with overlapping return observations for correlation analysis.")
    with tab_stats:
        st.markdown("#### Comparable historical statistics")
        aligned=returns[available].dropna(how="all")
        rows=[]
        for name in available:
            r=returns[name].dropna()
            if r.empty:
                continue
            wealth=np.exp(r.cumsum())
            dd=wealth/wealth.cummax()-1
            vol=r.std()*np.sqrt(252)
            ann_ret=np.exp(r.mean()*252)-1
            sharpe=(r.mean()*252)/vol if vol>0 else np.nan
            rows.append({"Instrument":name,"Observations":len(r),"Cumulative return":np.exp(r.sum())-1,
                "Annualised return*":ann_ret,"Annualised volatility":vol,"Sharpe (RF=0)":sharpe,
                "Max drawdown":dd.min(),"Worst day":r.min(),"Best day":r.max()})
        stats=pd.DataFrame(rows).set_index("Instrument")
        fmt={col:"{:.2%}" for col in ["Cumulative return","Annualised return*","Annualised volatility","Max drawdown","Worst day","Best day"]}
        fmt["Sharpe (RF=0)"]="{:.2f}"
        st.dataframe(stats.style.format(fmt),use_container_width=True)
        fig=px.bar(stats.reset_index(),x="Instrument",y="Annualised volatility",
            title="Annualised historical volatility · daily log returns × √252")
        st.plotly_chart(polish(fig,300),use_container_width=True)
        st.caption("*Annualised return is a geometric extrapolation of the sample mean daily log return. Sharpe shown uses a zero risk-free rate. These are descriptive sample statistics, not forecasts.")
    with tab_data:
        coverage=pd.DataFrame({
            "Yahoo ticker":[MARKET_UNIVERSE[x] for x in prices.columns],
            "First valid date":[prices[x].first_valid_index() for x in prices.columns],
            "Last valid date":[prices[x].last_valid_index() for x in prices.columns],
            "Valid observations":[int(prices[x].notna().sum()) for x in prices.columns],
            "Missing %":[float(prices[x].isna().mean()*100) for x in prices.columns]
        },index=prices.columns)
        st.dataframe(coverage.style.format({"Missing %":"{:.1f}%"}),use_container_width=True)
        st.download_button("Download adjusted prices CSV",prices.to_csv().encode("utf-8"),
            "yahoo_finance_adjusted_prices.csv","text/csv")
        st.download_button("Download daily log returns CSV",returns.to_csv().encode("utf-8"),
            "yahoo_finance_daily_log_returns.csv","text/csv")
        st.caption("Provider: Yahoo Finance via yfinance. Different market calendars, currencies, trading hours and symbol histories are not harmonised. No missing prices are synthetically filled.")
    st.caption("Research use only. Yahoo Finance is a convenience data source, not a licensed exchange feed. Verify timestamps, corporate actions and contract specifications before using results for trading.")


EQUITY_PRESETS = {
    "India · Large caps": {
        "RELIANCE":"RELIANCE.NS","TCS":"TCS.NS","INFOSYS":"INFY.NS",
        "HDFC BANK":"HDFCBANK.NS","ICICI BANK":"ICICIBANK.NS","SBI":"SBIN.NS",
        "AXIS BANK":"AXISBANK.NS","KOTAK BANK":"KOTAKBANK.NS","L&T":"LT.NS",
        "ITC":"ITC.NS","HINDUSTAN UNILEVER":"HINDUNILVR.NS",
        "BHARTI AIRTEL":"BHARTIARTL.NS","TATA MOTORS":"TATAMOTORS.NS",
        "MARUTI":"MARUTI.NS","SUN PHARMA":"SUNPHARMA.NS"
    },
    "India · Additional equities": {
        "BAJAJ FINANCE":"BAJFINANCE.NS","BAJAJ FINSERV":"BAJAJFINSV.NS",
        "ASIAN PAINTS":"ASIANPAINT.NS","TITAN":"TITAN.NS","ULTRATECH CEMENT":"ULTRACEMCO.NS",
        "WIPRO":"WIPRO.NS","HCLTECH":"HCLTECH.NS","TECH MAHINDRA":"TECHM.NS",
        "NTPC":"NTPC.NS","POWER GRID":"POWERGRID.NS","ONGC":"ONGC.NS",
        "COAL INDIA":"COALINDIA.NS","ADANI PORTS":"ADANIPORTS.NS",
        "JSW STEEL":"JSWSTEEL.NS","TATA STEEL":"TATASTEEL.NS",
        "BHARAT ELECTRONICS":"BEL.NS","TRENT":"TRENT.NS","ZOMATO":"ETERNAL.NS"
    },
    "US · Mega caps": {
        "APPLE":"AAPL","MICROSOFT":"MSFT","NVIDIA":"NVDA","AMAZON":"AMZN",
        "ALPHABET":"GOOGL","META":"META","BROADCOM":"AVGO","TESLA":"TSLA",
        "BERKSHIRE HATHAWAY":"BRK-B","JPMORGAN":"JPM","VISA":"V",
        "ELI LILLY":"LLY","WALMART":"WMT","NETFLIX":"NFLX","AMD":"AMD",
        "ORACLE":"ORCL","COSTCO":"COST","GOLDMAN SACHS":"GS"
    },
    "US · ETFs & benchmarks": {
        "S&P 500 ETF":"SPY","NASDAQ 100 ETF":"QQQ","TOTAL US MARKET":"VTI",
        "RUSSELL 2000 ETF":"IWM","SEMICONDUCTOR ETF":"SMH","FINANCIALS ETF":"XLF"
    }
}

@st.cache_data(ttl=900, show_spinner=False)
def download_equity_history(tickers, start_date, end_date, interval="1d"):
    """Bulk adjusted OHLCV history for the equity workspace."""
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return pd.DataFrame(), {}
    try:
        raw = yf.download(
            tickers=tickers, start=start_date, end=end_date, interval=interval,
            auto_adjust=True, progress=False, threads=True, group_by="column",
            actions=False, multi_level_index=True
        )
        if raw is None or raw.empty:
            return pd.DataFrame(), {}
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].copy() if "Close" in raw.columns.get_level_values(0) else pd.DataFrame()
            if isinstance(close, pd.Series):
                close = close.to_frame(name=tickers[0])
            # yfinance versions may put ticker on either level.
            if isinstance(close.columns, pd.MultiIndex):
                close.columns = close.columns.get_level_values(-1)
            if len(tickers) == 1 and close.empty:
                close = raw.xs(tickers[0], axis=1, level=-1, drop_level=True)[["Close"]].rename(columns={"Close":tickers[0]})
        else:
            close = raw[["Close"]].rename(columns={"Close":tickers[0]}) if "Close" in raw else pd.DataFrame()
        close = close[[c for c in tickers if c in close.columns]].apply(pd.to_numeric, errors="coerce")
        close.index = pd.to_datetime(close.index)
        if close.index.tz is not None:
            close.index = close.index.tz_localize(None)
        ohlcv = {}
        for ticker in tickers:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    fields = raw.xs(ticker, axis=1, level=-1, drop_level=True)
                elif len(tickers) == 1:
                    fields = raw.copy()
                else:
                    continue
                keep = [c for c in ["Open","High","Low","Close","Volume"] if c in fields.columns]
                frame = fields[keep].copy()
                frame.index = pd.to_datetime(frame.index)
                if frame.index.tz is not None:
                    frame.index = frame.index.tz_localize(None)
                ohlcv[ticker] = frame.sort_index()
            except Exception:
                continue
        return close.sort_index().dropna(how="all"), ohlcv
    except Exception:
        return pd.DataFrame(), {}

def equity_markets_dashboard(region="INR"):
    allowed_groups = ["US · Mega caps", "US · ETFs & benchmarks"] if region == "USD" else ["India · Large caps", "India · Additional equities"]
    st.markdown('<div class="section-kicker">08 / global equity research</div>', unsafe_allow_html=True)
    st.subheader(f"Equity markets · {region}")
    st.caption("Multi-stock market monitor with adjusted OHLCV history, technical indicators, relative performance and risk analytics.")
    all_presets = {}
    for group_name in allowed_groups:
        all_presets.update(EQUITY_PRESETS[group_name])
    left, mid, right = st.columns([1.25,1,1])
    with left:
        groups = st.multiselect("Universe", allowed_groups, default=allowed_groups, key=f"equity_groups_{region}")
    group_symbols = {}
    for group in groups:
        group_symbols.update(EQUITY_PRESETS[group])
    with mid:
        selected_names = st.multiselect("Stocks / ETFs", list(group_symbols), default=list(group_symbols)[:8], key=f"equity_names_{region}")
    with right:
        interval_label = st.selectbox("Bar frequency", ["Daily","Weekly"], index=0, key=f"equity_frequency_{region}")
    custom = st.text_input("Additional Yahoo tickers (comma-separated)", placeholder="e.g. ^NSEI, NVDA, 7203.T")
    tickers = [group_symbols[n] for n in selected_names]
    tickers += [x.strip().upper() for x in custom.split(",") if x.strip()]
    tickers = list(dict.fromkeys(tickers))
    date_left, date_right, refresh_col = st.columns([1,1,1])
    with date_left:
        start = st.date_input("History from", value=pd.Timestamp("2021-01-01").date(), key=f"equity_start_{region}")
    with date_right:
        end = st.date_input("History to (exclusive)", value=pd.Timestamp.today().date()+pd.Timedelta(days=1), key=f"equity_end_{region}")
    with refresh_col:
        st.write("")
        refresh = st.button("↻ Refresh equity data", type="primary", use_container_width=True)
    if start >= end:
        st.error("Start date must be earlier than end date.")
        return
    if not tickers:
        st.info("Choose at least one stock or enter a Yahoo ticker.")
        return
    if len(tickers) > 30:
        st.warning("Please limit one request to 30 tickers to keep downloads reliable.")
        return
    if refresh:
        download_equity_history.clear()
    interval = "1d" if interval_label == "Daily" else "1wk"
    with st.spinner(f"Downloading {len(tickers)} equity histories…"):
        prices, ohlcv = download_equity_history(tuple(tickers), str(start), str(end), interval)
    if prices.empty:
        st.warning("No stock prices returned. Check ticker spelling, date range or Yahoo availability.")
        return
    available = [t for t in tickers if t in prices.columns and prices[t].notna().any()]
    prices = prices[available].dropna(how="all")
    if not available:
        st.warning("No selected ticker returned usable prices.")
        return
    rets = np.log(prices.where(prices > 0)).diff()
    last = prices.ffill().iloc[-1]
    prev = prices.ffill().iloc[-2] if len(prices) > 1 else last
    st.markdown("#### Latest available observations")
    metric_cols = st.columns(min(4,len(available)))
    for i,ticker in enumerate(available):
        change = (last[ticker]/prev[ticker]-1)*100 if pd.notna(prev[ticker]) and prev[ticker] else np.nan
        metric_cols[i%len(metric_cols)].metric(ticker, f"{last[ticker]:,.2f}", f"{change:+.2f}% · last bar" if np.isfinite(change) else "—")
    st.caption(f"{len(available)} tickers returned · last observation {prices.dropna(how='all').index[-1]:%Y-%m-%d} · Yahoo Finance research data; not guaranteed live.")
    tabs = st.tabs(["Single-stock technicals","Relative performance","Risk & correlation","Raw data"])
    with tabs[0]:
        chosen = st.selectbox("Stock detail", available, key=f"equity_detail_{region}")
        detail = ohlcv.get(chosen, pd.DataFrame())
        if detail.empty or "Close" not in detail:
            st.info("OHLC data unavailable for this ticker. Using the adjusted-close series.")
            detail = pd.DataFrame({"Close":prices[chosen]})
        close = pd.to_numeric(detail["Close"],errors="coerce")
        fast = st.slider("Fast SMA",5,100,20,5,key=f"eq_sma_fast_{region}")
        slow = st.slider("Slow SMA",20,250,50,5,key=f"eq_sma_slow_{region}")
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        rs = gain / loss.replace(0,np.nan)
        rsi = 100 - 100/(1+rs)
        ema12 = close.ewm(span=12,adjust=False).mean()
        ema26 = close.ewm(span=26,adjust=False).mean()
        macd = ema12-ema26
        signal = macd.ewm(span=9,adjust=False).mean()
        midline = close.rolling(20).mean()
        band = close.rolling(20).std()*2
        price_fig = go.Figure()
        if {"Open","High","Low","Close"}.issubset(detail.columns):
            price_fig.add_trace(go.Candlestick(x=detail.index,open=detail["Open"],high=detail["High"],low=detail["Low"],close=detail["Close"],name=chosen))
        else:
            price_fig.add_trace(go.Scatter(x=close.index,y=close,name=chosen,line=dict(color=CYAN,width=1.8)))
        price_fig.add_trace(go.Scatter(x=close.index,y=close.rolling(fast).mean(),name=f"SMA {fast}",line=dict(color=ORANGE,width=1.2)))
        price_fig.add_trace(go.Scatter(x=close.index,y=close.rolling(slow).mean(),name=f"SMA {slow}",line=dict(color=BLUE,width=1.2)))
        price_fig.add_trace(go.Scatter(x=close.index,y=midline+band,name="Bollinger upper",line=dict(color=MUTED,width=1,dash="dot")))
        price_fig.add_trace(go.Scatter(x=close.index,y=midline-band,name="Bollinger lower",line=dict(color=MUTED,width=1,dash="dot"),fill="tonexty",fillcolor="rgba(147,164,184,.08)"))
        price_fig.update_layout(title=f"{chosen} · adjusted price & technical overlays",xaxis_rangeslider_visible=False)
        st.plotly_chart(polish(price_fig,450),use_container_width=True)
        indicator_a,indicator_b = st.columns(2)
        with indicator_a:
            rf=go.Figure(go.Scatter(x=rsi.index,y=rsi,name="RSI(14)",line=dict(color=CYAN)))
            rf.add_hline(y=70,line_dash="dash",line_color=RED); rf.add_hline(y=30,line_dash="dash",line_color=GREEN)
            rf.update_layout(title="Relative strength index · 14")
            st.plotly_chart(polish(rf,260),use_container_width=True)
        with indicator_b:
            mf=go.Figure()
            mf.add_trace(go.Scatter(x=macd.index,y=macd,name="MACD",line=dict(color=BLUE)))
            mf.add_trace(go.Scatter(x=signal.index,y=signal,name="Signal",line=dict(color=ORANGE)))
            mf.add_trace(go.Bar(x=(macd-signal).index,y=macd-signal,name="Histogram",opacity=.35))
            mf.update_layout(title="MACD · 12 / 26 / 9")
            st.plotly_chart(polish(mf,260),use_container_width=True)
        if "Volume" in detail and detail["Volume"].notna().any():
            vf=go.Figure(go.Bar(x=detail.index,y=detail["Volume"],name="Volume"))
            vf.update_layout(title=f"{chosen} · reported volume")
            st.plotly_chart(polish(vf,220),use_container_width=True)
    with tabs[1]:
        rebased = prices.div(prices.apply(lambda s:s.dropna().iloc[0] if s.notna().any() else np.nan)).mul(100)
        f=go.Figure()
        for ticker in available:
            f.add_trace(go.Scatter(x=rebased.index,y=rebased[ticker],name=ticker))
        f.update_layout(title="Relative performance · growth of 100",yaxis_title="Indexed value")
        st.plotly_chart(polish(f,420),use_container_width=True)
        st.caption("Cross-market comparisons are in each instrument's local quote currency; this chart does not convert INR to USD.")
    with tabs[2]:
        aligned=rets[available].dropna()
        if len(aligned)>=3:
            corr=aligned.corr()
            heat=px.imshow(corr,text_auto=".2f",zmin=-1,zmax=1,color_continuous_scale="RdBu_r",aspect="auto",title="Daily / weekly return correlation")
            heat.update_layout(coloraxis_showscale=False)
            st.plotly_chart(polish(heat,420),use_container_width=True)
        ann=rets.std()*np.sqrt(252 if interval=="1d" else 52)
        total=(prices.ffill().iloc[-1]/prices.apply(lambda s:s.dropna().iloc[0])-1)
        stats=pd.DataFrame({"Period return":total,"Annualised volatility":ann,"Mean return (annualised)":rets.mean()*(252 if interval=="1d" else 52)})
        st.dataframe(stats.style.format("{:.2%}"),use_container_width=True)
        st.caption("Volatility and annualised mean use 252 daily or 52 weekly periods. Cross-market calendars are not harmonised; estimates are descriptive.")
    with tabs[3]:
        st.dataframe(prices.tail(100),use_container_width=True)
        st.download_button("Download adjusted close prices CSV",prices.to_csv().encode("utf-8"),"equity_adjusted_prices.csv","text/csv")
        st.download_button("Download log returns CSV",rets.to_csv().encode("utf-8"),"equity_log_returns.csv","text/csv")
        detail_export = ohlcv.get(st.selectbox("OHLCV export ticker",available,key=f"eq_export_ticker_{region}"),pd.DataFrame())
        if not detail_export.empty:
            st.download_button("Download selected OHLCV CSV",detail_export.to_csv().encode("utf-8"),"equity_ohlcv.csv","text/csv")
    st.caption("Source: Yahoo Finance through yfinance. Adjusted OHLC prices include provider adjustments; volume is provider-reported. yfinance describes its interface as intended for research/personal use—review Yahoo's terms and data rights before redistribution.")

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
        market_assets = st.multiselect("India market series", ["RELIANCE","TCS","INFOSYS","HDFC_BANK","ICICI_BANK","SBIN","AXIS_BANK","KOTAK_BANK","LT","ITC","HINDUNILVR","BHARTI_AIRTEL","TATA_MOTORS","MARUTI","SUN_PHARMA","NIFTY50","BANKNIFTY","NIFTYENERGY","INDIA_VIX","USDINR","BRENT_CRUDE","WTI_CRUDE","GOLD"], default=["RELIANCE","NIFTY50","BANKNIFTY","NIFTYENERGY"])
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



@st.cache_data(ttl=300, show_spinner=False)
def yahoo_option_expiries(symbol):
    """Return expiries Yahoo exposes for a ticker; availability is provider-dependent."""
    try:
        return list(yf.Ticker(symbol).options or [])
    except Exception:
        return []

@st.cache_data(ttl=120, show_spinner=False)
def yahoo_option_chain(symbol, expiry):
    """Fetch one Yahoo option expiry. This is not an NSE-certified option-chain feed."""
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiry)
        calls, puts = chain.calls.copy(), chain.puts.copy()
        if not calls.empty:
            calls["option_type"] = "CALL"
        if not puts.empty:
            puts["option_type"] = "PUT"
        return pd.concat([calls, puts], ignore_index=True)
    except Exception:
        return pd.DataFrame()

def max_pain_from_chain(chain):
    """Calculate expiry max-pain estimate from listed OI and strikes."""
    required = {"strike", "openInterest", "option_type"}
    if chain.empty or not required.issubset(chain.columns):
        return np.nan, pd.DataFrame()
    work = chain[list(required)].copy()
    work["strike"] = pd.to_numeric(work["strike"], errors="coerce")
    work["openInterest"] = pd.to_numeric(work["openInterest"], errors="coerce").fillna(0)
    work = work.dropna(subset=["strike"])
    strikes = np.sort(work["strike"].unique())
    rows = []
    for settle in strikes:
        call_oi = work.loc[work["option_type"] == "CALL", "openInterest"]
        put_oi = work.loc[work["option_type"] == "PUT", "openInterest"]
        call_strikes = work.loc[work["option_type"] == "CALL", "strike"]
        put_strikes = work.loc[work["option_type"] == "PUT", "strike"]
        payout = ((np.maximum(settle-call_strikes, 0) * call_oi).sum()
                  + (np.maximum(put_strikes-settle, 0) * put_oi).sum())
        rows.append({"Settlement": settle, "Aggregate intrinsic payout": payout})
    curve = pd.DataFrame(rows)
    if curve.empty:
        return np.nan, curve
    return float(curve.loc[curve["Aggregate intrinsic payout"].idxmin(), "Settlement"]), curve

def normalize_nse_index_futures(raw):
    """Map NSE UDiFF and common legacy F&O bhavcopy headers to one research schema."""
    aliases = {
        "Date": ["TRADDT", "BIZDT", "DATE", "TIMESTAMP", "TRADEDATE"],
        "Symbol": ["TCKRSYMB", "SYMBOL", "UNDERLYING"],
        "InstrumentType": ["FININSTRMTP", "INSTRUMENT", "INSTRUMENTTYPE", "INSTRUMENT_TYPE"],
        "Expiry": ["XPRYDT", "EXPIRY_DT", "EXPIRY", "EXPIRYDATE"],
        "Open": ["OPNPRIC", "OPEN", "OPEN_PRICE"], "High": ["HGHPRIC", "HIGH", "HIGH_PRICE"],
        "Low": ["LWPRIC", "LOW", "LOW_PRICE"], "Close": ["CLSPRIC", "CLOSE", "CLOSE_PRICE"],
        "LastPrice": ["LASTPRIC", "LTP", "LAST_PRICE"],
        "SettlePrice": ["STTLMPRIC", "SETTLE_PR", "SETTLEPRICE", "SETTLEMENT_PRICE"],
        "Volume": ["TTLTRADGVOL", "CONTRACTS", "VOLUME", "TTL_TRD_QNTY", "NO_OF_CONTRACTS"],
        "Turnover": ["TTLTRFVAL", "TURNOVER", "TURNOVER_LAKHS"],
        "OpenInterest": ["OPNINTRST", "OPEN_INT", "OPENINTEREST", "OPEN_INTEREST", "OI"],
        "ChangeInOI": ["CHNGINOPNINTRST", "CHG_IN_OI", "CHANGE_IN_OI", "CHANGEINOI"],
        "UnderlyingValue": ["UNDRLYGPRIC", "UNDERLYING_VALUE", "UNDERLYINGVALUE"]
    }
    source = raw.copy()
    source.columns = [str(c).replace("\ufeff", "").strip() for c in source.columns]
    lookup = {''.join(ch for ch in str(c).upper() if ch.isalnum()): c for c in source.columns}
    rename = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            key = ''.join(ch for ch in candidate.upper() if ch.isalnum())
            if key in lookup:
                rename[lookup[key]] = target
                break
    frame = source.rename(columns=rename).copy()
    required = ["Date", "Symbol", "InstrumentType", "Expiry", "Close"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError("Missing required fields after header mapping: " + ", ".join(missing))
    if "InstrumentType" in frame.columns:
        inst = frame["InstrumentType"].astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
        frame = frame[inst.isin(["FUTIDX", "INDEXFUTURE", "INDEXFUTURES", "FUTUREINDEX"])]
    frame["Symbol"] = frame["Symbol"].astype(str).str.upper().str.strip()
    frame = frame[frame["Symbol"].isin(["NIFTY", "BANKNIFTY", "FINNIFTY"])].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", dayfirst=True)
    frame["Expiry"] = pd.to_datetime(frame["Expiry"], errors="coerce", dayfirst=True)
    numeric = ["Open", "High", "Low", "Close", "LastPrice", "SettlePrice", "Volume",
               "Turnover", "OpenInterest", "ChangeInOI", "UnderlyingValue"]
    for col in numeric:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col].astype(str).str.replace(",", "", regex=False), errors="coerce")
    frame = frame.dropna(subset=["Date", "Expiry", "Close"])
    frame = frame.sort_values(["Symbol", "Expiry", "Date"]).drop_duplicates(
        ["Symbol", "Expiry", "Date"], keep="last")
    frame["DaysToExpiry"] = (frame["Expiry"].dt.normalize() - frame["Date"].dt.normalize()).dt.days
    if {"SettlePrice", "UnderlyingValue"}.issubset(frame.columns):
        frame["Basis"] = frame["SettlePrice"] - frame["UnderlyingValue"]
        frame["BasisPct"] = 100 * frame["Basis"] / frame["UnderlyingValue"].replace(0, np.nan)
    frame["DailyReturnPct"] = frame.groupby(["Symbol", "Expiry"])["Close"].pct_change() * 100
    return frame.reset_index(drop=True)


def read_nse_bhavcopy_upload(uploaded_file):
    """Read either the official UDiFF ZIP containing CSV or a plain CSV upload."""
    payload = uploaded_file.getvalue()
    name = str(getattr(uploaded_file, "name", "")).lower()
    if name.endswith(".zip") or payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
            if not csv_names:
                raise ValueError("ZIP archive does not contain a CSV file.")
            chosen = max(csv_names, key=lambda n: archive.getinfo(n).file_size)
            with archive.open(chosen) as stream:
                return pd.read_csv(stream, low_memory=False), chosen
    return pd.read_csv(io.BytesIO(payload), low_memory=False), getattr(uploaded_file, "name", "uploaded.csv")



def us_market_dashboard():
    st.markdown('<div class="section-kicker">02 / United States market intelligence</div>', unsafe_allow_html=True)
    st.subheader("US markets · Wall Street market-linkage terminal")
    st.caption("US equity benchmarks, mega-cap leadership, volatility and cross-sector relationships. Quotes are in USD.")
    labels = ["SP500","NASDAQ","DOW","RUSSELL2000","VIX","AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","TSLA","SPY","QQQ"]
    a,b = st.columns(2)
    with a:
        start = st.date_input("US history from", value=pd.Timestamp("2020-01-01").date(), key="us_market_start")
    with b:
        end = st.date_input("US history to (exclusive)", value=pd.Timestamp.today().date()+pd.Timedelta(days=1), key="us_market_end")
    selected = st.multiselect("US benchmarks and stocks", labels, default=["SP500","NASDAQ","DOW","VIX","AAPL","MSFT","NVDA","SPY"], key="us_market_assets")
    refresh = st.button("Refresh US market data", type="primary")
    if start >= end:
        st.error("Start date must be earlier than end date.")
        return
    if refresh:
        download_market.clear()
    prices = download_market(str(start), str(end), selected)
    if prices.empty:
        st.warning("No US market history returned. Check provider availability or date range.")
        return
    returns = np.log(prices.where(prices > 0)).diff()
    latest = prices.ffill().iloc[-1]
    previous = prices.ffill().iloc[-2] if len(prices) > 1 else latest
    cols = st.columns(min(4, len(prices.columns)))
    for i, name in enumerate(prices.columns):
        change = (latest[name]/previous[name]-1)*100 if pd.notna(previous[name]) and previous[name] else np.nan
        cols[i % len(cols)].metric(name, "USD " + f"{latest[name]:,.2f}", f"{change:+.2f}% · last observation" if np.isfinite(change) else "—")
    st.caption(f"Latest provider observation: {prices.dropna(how='all').index[-1]:%Y-%m-%d} · USD market series · Yahoo data is not guaranteed live.")
    t1,t2,t3,t4 = st.tabs(["US benchmarks","Mega-cap leadership","Volatility & correlation","Downloads"])
    with t1:
        names = [x for x in ["SP500","NASDAQ","DOW","RUSSELL2000"] if x in prices]
        if names:
            frame = prices[names]
            indexed = frame.div(frame.apply(lambda x:x.dropna().iloc[0] if x.notna().any() else np.nan))*100
            fig = go.Figure()
            for name in names:
                fig.add_trace(go.Scatter(x=indexed.index,y=indexed[name],name=name))
            fig.update_layout(title="US benchmarks · relative performance (growth of 100)")
            st.plotly_chart(polish(fig,380),use_container_width=True)
        if "VIX" in prices:
            fig = go.Figure(go.Scatter(x=prices.index,y=prices["VIX"],name="VIX"))
            fig.update_layout(title="CBOE VIX · volatility index level")
            st.plotly_chart(polish(fig,260),use_container_width=True)
    with t2:
        names = [x for x in ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","JPM","TSLA"] if x in prices]
        if names:
            frame = prices[names]
            indexed = frame.div(frame.apply(lambda x:x.dropna().iloc[0] if x.notna().any() else np.nan))*100
            fig = go.Figure()
            for name in names:
                fig.add_trace(go.Scatter(x=indexed.index,y=indexed[name],name=name))
            fig.update_layout(title="US mega-cap leadership · growth of 100")
            st.plotly_chart(polish(fig,380),use_container_width=True)
    with t3:
        usable = returns.dropna(how="all")
        if usable.shape[1] > 1 and len(usable.dropna()) > 3:
            fig = px.imshow(usable.corr(),text_auto=".2f",zmin=-1,zmax=1,color_continuous_scale="RdBu_r",title="US daily-return correlation")
            fig.update_layout(coloraxis_showscale=False)
            st.plotly_chart(polish(fig,390),use_container_width=True)
        st.dataframe(pd.DataFrame({"Annualised return":returns.mean()*252,"Annualised volatility":returns.std()*np.sqrt(252)}).style.format("{:.2%}"),use_container_width=True)
    with t4:
        st.dataframe(prices.tail(100),use_container_width=True)
        st.download_button("Download US adjusted prices CSV",prices.to_csv().encode("utf-8"),"us_adjusted_prices_usd.csv","text/csv")
        st.download_button("Download US log returns CSV",returns.to_csv().encode("utf-8"),"us_log_returns.csv","text/csv")
    st.caption("US statistics are calculated in USD. No FX conversion or mixed-currency portfolio aggregation is performed.")


def fo_dashboard():
    st.markdown('<div class="section-kicker">05 / derivatives analytics</div>', unsafe_allow_html=True)
    st.subheader("Futures & options intelligence")
    st.caption("Yahoo Finance option-chain snapshots where supported, plus user-supplied NSE derivatives files. This workspace does not imply a licensed or complete NSE feed.")
    tab_chain, tab_futures, tab_us, tab_index_futures, tab_import = st.tabs(["India options chain", "Global commodity futures", "US derivatives · USD", "NSE index futures · daily", "NSE options import"])

    with tab_chain:
        st.markdown("#### Yahoo Finance option chain")
        fo_underlyings = {
            "Reliance": "RELIANCE.NS", "TCS": "TCS.NS", "Infosys": "INFY.NS",
            "HDFC Bank": "HDFCBANK.NS", "ICICI Bank": "ICICIBANK.NS",
            "NIFTY 50": "^NSEI", "Bank NIFTY": "^NSEBANK"
        }
        left, right = st.columns([1, 1])
        with left:
            label = st.selectbox("Underlying", list(fo_underlyings), index=0)
        symbol = fo_underlyings[label]
        with right:
            expiries = yahoo_option_expiries(symbol)
            expiry = st.selectbox("Expiration", expiries) if expiries else None
        if not expiries:
            st.warning(f"Yahoo Finance does not currently expose an option chain for {label} ({symbol}). This is common for NSE symbols. Upload an NSE option-chain / bhavcopy CSV in the NSE data import tab.")
        else:
            if st.button("Refresh option chain", key="refresh_yahoo_chain"):
                yahoo_option_chain.clear()
            chain = yahoo_option_chain(symbol, expiry)
            if chain.empty:
                st.warning("The provider returned an empty chain for this expiry. Try another expiry or upload an exchange file.")
            else:
                for col in ["openInterest", "volume", "impliedVolatility", "strike", "lastPrice", "bid", "ask"]:
                    if col not in chain:
                        chain[col] = np.nan
                calls_oi = pd.to_numeric(chain.loc[chain.option_type=="CALL","openInterest"], errors="coerce").sum()
                puts_oi = pd.to_numeric(chain.loc[chain.option_type=="PUT","openInterest"], errors="coerce").sum()
                pcr = puts_oi/calls_oi if calls_oi else np.nan
                pain, pain_curve = max_pain_from_chain(chain)
                metric_row([
                    ("CALL OPEN INTEREST", f"{calls_oi:,.0f}", "reported contracts"),
                    ("PUT OPEN INTEREST", f"{puts_oi:,.0f}", "reported contracts"),
                    ("PUT / CALL OI", f"{pcr:.2f}" if np.isfinite(pcr) else "—", "descriptive ratio"),
                    ("ESTIMATED MAX PAIN", f"{pain:,.2f}" if np.isfinite(pain) else "—", "OI-based expiry calculation"),
                ])
                view = chain[["option_type","strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility"]].copy()
                view["impliedVolatility"] = pd.to_numeric(view["impliedVolatility"], errors="coerce")*100
                st.dataframe(view.sort_values(["strike","option_type"]).style.format({
                    "strike":"{:,.2f}","lastPrice":"{:,.2f}","bid":"{:,.2f}","ask":"{:,.2f}",
                    "volume":"{:,.0f}","openInterest":"{:,.0f}","impliedVolatility":"{:.1f}%"
                }, na_rep="—"), use_container_width=True, height=420)
                oi = chain.groupby(["strike","option_type"], as_index=False)["openInterest"].sum()
                oi["openInterest"] = pd.to_numeric(oi["openInterest"], errors="coerce").fillna(0)
                fig = px.bar(oi, x="strike", y="openInterest", color="option_type", barmode="group",
                             title="Open interest by strike")
                st.plotly_chart(polish(fig, 360), use_container_width=True)
                if not pain_curve.empty:
                    fig = go.Figure(go.Scatter(x=pain_curve["Settlement"],y=pain_curve["Aggregate intrinsic payout"],
                                               mode="lines+markers",name="Aggregate payout"))
                    fig.add_vline(x=pain, line_dash="dash", line_color=ORANGE,
                                  annotation_text=f"Max pain ≈ {pain:,.2f}")
                    fig.update_layout(title="Expiry payout proxy by settlement price",
                                      xaxis_title="Hypothetical settlement", yaxis_title="OI × intrinsic value")
                    st.plotly_chart(polish(fig, 320), use_container_width=True)
                st.download_button("Download option chain CSV", chain.to_csv(index=False).encode("utf-8"),
                                   file_name=f"{symbol.replace('^','')}_{expiry}_option_chain.csv", mime="text/csv")
                st.caption("PCR and max pain are descriptive positioning summaries, not directional signals. OI is not proof of buyer/seller intent; max pain ignores hedging, exercise details, transaction costs and intraday changes.")

    with tab_futures:
        st.markdown("#### Futures price & curve monitor")
        st.caption("Yahoo continuous futures symbols are global commodity proxies; they are not individual NSE stock/index futures contracts.")
        futures_universe = {"Brent crude":"BZ=F","WTI crude":"CL=F","Gold":"GC=F","Silver":"SI=F",
                            "Natural gas":"NG=F","S&P 500 E-mini":"ES=F","10Y Treasury note":"ZN=F"}
        selected_futures = st.multiselect("Yahoo futures proxies", list(futures_universe),
                                          default=["Brent crude","WTI crude","Gold"])
        period = st.selectbox("History", ["1mo","3mo","6mo","1y","2y"], index=3)
        if selected_futures:
            rows=[]
            for name in selected_futures:
                ticker=futures_universe[name]
                try:
                    hist=yf.download(ticker, period=period, auto_adjust=False, progress=False, threads=False)
                    if isinstance(hist.columns,pd.MultiIndex):
                        hist.columns=hist.columns.get_level_values(0)
                    if not hist.empty and "Close" in hist:
                        close=hist["Close"].dropna()
                        if isinstance(close,pd.DataFrame):
                            close=close.iloc[:,0]
                        rows.append(pd.DataFrame({"Date":close.index,"Instrument":name,"Close":close.values}))
                except Exception:
                    continue
            if rows:
                fut=pd.concat(rows,ignore_index=True)
                fig=px.line(fut,x="Date",y="Close",color="Instrument",title="Continuous futures proxy prices")
                st.plotly_chart(polish(fig,390),use_container_width=True)
                st.dataframe(fut.groupby("Instrument")["Close"].agg(["last","min","max"]).style.format("{:,.2f}"),
                             use_container_width=True)
                st.download_button("Download futures history CSV",fut.to_csv(index=False).encode("utf-8"),
                                   "yahoo_continuous_futures.csv","text/csv")
            else:
                st.warning("No futures history returned. Try another contract or refresh later.")
        st.info("Continuous futures symbols are stitched provider series. They do not represent a specific expiry, tradable contract, official settlement, or roll-adjusted strategy P&L.")


    with tab_us:
        st.markdown("#### US listed options & futures · USD research")
        us_underlyings = {"Apple":"AAPL","Microsoft":"MSFT","NVIDIA":"NVDA","Amazon":"AMZN","Tesla":"TSLA","S&P 500 ETF":"SPY","Nasdaq 100 ETF":"QQQ"}
        left,right = st.columns(2)
        with left:
            us_label = st.selectbox("US option underlying", list(us_underlyings), key="us_option_underlying")
        us_symbol = us_underlyings[us_label]
        with right:
            us_expiries = yahoo_option_expiries(us_symbol)
            us_expiry = st.selectbox("US option expiry", us_expiries, key="us_option_expiry") if us_expiries else None
        if not us_expiries:
            st.info(f"No US option expiry is currently returned for {us_symbol}. Try another underlying or refresh later.")
        else:
            if st.button("Refresh US option chain", key="refresh_us_option_chain"):
                yahoo_option_chain.clear()
            us_chain = yahoo_option_chain(us_symbol, us_expiry)
            if us_chain.empty:
                st.warning("The provider returned an empty US option chain for this expiry.")
            else:
                for col in ["openInterest","volume","impliedVolatility","strike","lastPrice","bid","ask"]:
                    if col not in us_chain:
                        us_chain[col] = np.nan
                call_oi = pd.to_numeric(us_chain.loc[us_chain.option_type=="CALL","openInterest"],errors="coerce").sum()
                put_oi = pd.to_numeric(us_chain.loc[us_chain.option_type=="PUT","openInterest"],errors="coerce").sum()
                pcr = put_oi/call_oi if call_oi else np.nan
                pain, curve = max_pain_from_chain(us_chain)
                metric_row([("CALL OI",f"{call_oi:,.0f}","provider reported"),("PUT OI",f"{put_oi:,.0f}","provider reported"),("PUT / CALL OI",f"{pcr:.2f}" if np.isfinite(pcr) else "—","descriptive"),("EST. MAX PAIN",f"{pain:,.2f}" if np.isfinite(pain) else "—","OI-based estimate")])
                view = us_chain[["option_type","strike","lastPrice","bid","ask","volume","openInterest","impliedVolatility"]].copy()
                view["impliedVolatility"] = pd.to_numeric(view["impliedVolatility"],errors="coerce")*100
                st.dataframe(view.sort_values(["strike","option_type"]).style.format({"strike":"{:,.2f}","lastPrice":"{:,.2f}","bid":"{:,.2f}","ask":"{:,.2f}","volume":"{:,.0f}","openInterest":"{:,.0f}","impliedVolatility":"{:.2f}%"},na_rep="—"),use_container_width=True,height=400)
                st.download_button("Download US options chain CSV",us_chain.to_csv(index=False).encode("utf-8"),f"{us_symbol}_{us_expiry}_options_usd.csv","text/csv")
        st.markdown("#### US index & Treasury futures proxies")
        us_futures = {"E-mini S&P 500":"ES=F","E-mini Nasdaq 100":"NQ=F","E-mini Dow":"YM=F","Russell 2000":"RTY=F","10Y Treasury note":"ZN=F","30Y Treasury bond":"ZB=F"}
        chosen_us_futures = st.multiselect("US futures contracts",list(us_futures),default=["E-mini S&P 500","E-mini Nasdaq 100","10Y Treasury note"],key="us_futures_symbols")
        us_period = st.selectbox("US futures history",["1mo","3mo","6mo","1y","2y"],index=3,key="us_futures_period")
        if chosen_us_futures:
            us_rows=[]
            for label in chosen_us_futures:
                try:
                    frame=yf.download(us_futures[label],period=us_period,auto_adjust=False,progress=False,threads=False)
                    if isinstance(frame.columns,pd.MultiIndex):
                        frame.columns=frame.columns.get_level_values(0)
                    if not frame.empty and "Close" in frame:
                        series=frame["Close"]
                        if isinstance(series,pd.DataFrame): series=series.iloc[:,0]
                        us_rows.append(pd.DataFrame({"Date":series.index,"Contract":label,"Close":series.values}))
                except Exception:
                    continue
            if us_rows:
                us_data=pd.concat(us_rows,ignore_index=True)
                fig=px.line(us_data,x="Date",y="Close",color="Contract",title="US index & Treasury futures · provider continuous proxies")
                st.plotly_chart(polish(fig,360),use_container_width=True)
                st.download_button("Download US futures history CSV",us_data.to_csv(index=False).encode("utf-8"),"us_futures_history_usd.csv","text/csv")
            else:
                st.warning("No US futures history returned for the selected contracts.")
        st.caption("Yahoo option chains and continuous futures are provider snapshots/proxies, not CME/OPRA direct feeds, official settlement prices or guaranteed real-time data. Futures contract multipliers, tick values, expiry and roll conventions must be verified independently.")

    with tab_index_futures:
        st.markdown("#### NSE index futures · UDiFF daily bhavcopy")
        st.caption("Upload the official F&O UDiFF Common Bhavcopy Final ZIP, or its extracted CSV. The parser maps UDiFF fields and common legacy headers, then retains FUTIDX contracts for NIFTY, BANKNIFTY and FINNIFTY.")
        st.markdown("**Expected source:** NSE All Reports → F&O → UDiFF Common Bhavcopy Final (ZIP).")
        st.markdown("[Open NSE official derivatives reports](https://www.nseindia.com/all-reports-derivatives)")
        st.download_button("Download normalized CSV schema template",
            pd.DataFrame(columns=["Date","Symbol","InstrumentType","Expiry","Open","High","Low","Close",
                "LastPrice","SettlePrice","Volume","Turnover","OpenInterest","ChangeInOI","UnderlyingValue"]
            ).to_csv(index=False).encode("utf-8"),
            file_name="nse_index_futures_normalized_template.csv", mime="text/csv",
            key="download_index_futures_template")
        index_file = st.file_uploader("Upload NSE F&O UDiFF ZIP or CSV", type=["zip","csv"], key="nse_index_futures_bhavcopy")
        if index_file is not None:
            try:
                raw_index, source_name = read_nse_bhavcopy_upload(index_file)
                index_fut = normalize_nse_index_futures(raw_index)
                if index_fut.empty:
                    st.warning("No NIFTY, BANKNIFTY or FINNIFTY FUTIDX rows were found. Confirm this is the F&O UDiFF bhavcopy.")
                    st.caption("Raw headers detected: " + ", ".join(map(str, raw_index.columns)))
                else:
                    st.success(f"Loaded {len(index_fut):,} index-futures contract-days from {source_name}.")
                    available_symbols = [x for x in ["NIFTY","BANKNIFTY","FINNIFTY"] if x in index_fut["Symbol"].unique()]
                    selected_symbols = st.multiselect("Index contracts", available_symbols, default=available_symbols, key="index_fut_symbols")
                    view = index_fut[index_fut["Symbol"].isin(selected_symbols)].copy()
                    if view.empty:
                        st.info("Select at least one index to inspect.")
                    else:
                        latest_date = view["Date"].max()
                        latest = view[view["Date"] == latest_date].copy()
                        latest_expiries = latest.sort_values("Expiry")
                        front = view[view["Expiry"] >= view["Date"]].sort_values(["Symbol","Date","Expiry"])
                        front = front.drop_duplicates(["Symbol","Date"], keep="first")
                        latest_front = front[front["Date"] == front["Date"].max()]
                        latest_total_oi = latest["OpenInterest"].sum(min_count=1) if "OpenInterest" in latest else np.nan
                        latest_total_vol = latest["Volume"].sum(min_count=1) if "Volume" in latest else np.nan
                        latest_oi_change = latest["ChangeInOI"].sum(min_count=1) if "ChangeInOI" in latest else np.nan
                        metric_row([
                            ("LATEST TRADE DATE", latest_date.strftime("%d %b %Y"), f"{len(latest):,} contracts"),
                            ("FRONT-MONTH CLOSE", f"{latest_front['Close'].mean():,.2f}" if not latest_front.empty else "—", "mean across selected indices"),
                            ("TOTAL OPEN INTEREST", f"{latest_total_oi:,.0f}" if pd.notna(latest_total_oi) else "—", "contracts, latest date"),
                            ("TOTAL CONTRACT VOLUME", f"{latest_total_vol:,.0f}" if pd.notna(latest_total_vol) else "—", f"OI change {latest_oi_change:,.0f}" if pd.notna(latest_oi_change) else "OI change unavailable")
                        ])
                        left, right = st.columns(2)
                        with left:
                            fig = px.line(front, x="Date", y="Close", color="Symbol", title="Front-month index futures · close")
                            st.plotly_chart(polish(fig, 350), use_container_width=True)
                        with right:
                            if "OpenInterest" in view.columns:
                                oi_daily = view.groupby(["Date","Symbol"], as_index=False)["OpenInterest"].sum(min_count=1)
                                fig = px.line(oi_daily, x="Date", y="OpenInterest", color="Symbol",
                                              title="Aggregate open interest · all uploaded expiries")
                                st.plotly_chart(polish(fig, 350), use_container_width=True)
                        left, right = st.columns(2)
                        with left:
                            if "Volume" in view.columns:
                                volume_daily = view.groupby(["Date","Symbol"], as_index=False)["Volume"].sum(min_count=1)
                                fig = px.bar(volume_daily, x="Date", y="Volume", color="Symbol",
                                             title="Daily traded contracts", barmode="group")
                                st.plotly_chart(polish(fig, 320), use_container_width=True)
                        with right:
                            if "ChangeInOI" in view.columns:
                                change_daily = view.groupby(["Date","Symbol"], as_index=False)["ChangeInOI"].sum(min_count=1)
                                fig = px.bar(change_daily, x="Date", y="ChangeInOI", color="Symbol",
                                             title="Daily change in open interest", barmode="group")
                                st.plotly_chart(polish(fig, 320), use_container_width=True)
                        st.markdown("#### Expiry-wise contract snapshot")
                        display_cols = [c for c in ["Date","Symbol","Expiry","DaysToExpiry","Open","High","Low","Close",
                            "SettlePrice","UnderlyingValue","Basis","BasisPct","Volume","Turnover","OpenInterest",
                            "ChangeInOI","DailyReturnPct"] if c in view.columns]
                        st.dataframe(latest_expiries[display_cols].sort_values(["Symbol","Expiry"]).style.format({
                            "Open":"{:,.2f}","High":"{:,.2f}","Low":"{:,.2f}","Close":"{:,.2f}",
                            "SettlePrice":"{:,.2f}","UnderlyingValue":"{:,.2f}","Basis":"{:,.2f}",
                            "BasisPct":"{:.2f}%","Volume":"{:,.0f}","Turnover":"{:,.2f}",
                            "OpenInterest":"{:,.0f}","ChangeInOI":"{:,.0f}","DailyReturnPct":"{:.2f}%"
                        }, na_rep="—"), use_container_width=True, height=360)
                        if "Basis" in view.columns:
                            basis_data = view.dropna(subset=["Basis"])
                            if not basis_data.empty:
                                fig = px.line(basis_data, x="Date", y="Basis", color="Symbol", line_dash="Expiry",
                                              title="Futures basis · settlement minus underlying")
                                st.plotly_chart(polish(fig, 300), use_container_width=True)
                        st.download_button("Download normalized index futures CSV",
                            view.to_csv(index=False, float_format="%.2f").encode("utf-8"),
                            file_name="nse_index_futures_normalized.csv", mime="text/csv",
                            key="download_normalized_index_futures")
                        st.caption("Front-month is the nearest listed expiry on or after each trade date. Open interest and volume are contract counts as supplied by the bhavcopy. Basis is calculated only when settlement price and underlying value exist. The front-month series is not back-adjusted; expiry rolls can create gaps. These are end-of-day records, not intraday/tick data.")
            except Exception as exc:
                st.error(f"Could not parse NSE index futures bhavcopy: {exc}")
                st.caption("Upload the F&O UDiFF Common Bhavcopy Final ZIP or extracted CSV. The template download shows normalized column names accepted by the dashboard.")

    with tab_import:
        st.markdown("#### Import NSE options data")
        st.write("Upload an NSE options CSV downloaded from an exchange or licensed vendor. For index futures, use the dedicated NSE index futures · daily tab.")
        opt_file=st.file_uploader("NSE options CSV",type=["csv"],key="nse_opt_upload")
        if opt_file is not None:
            try:
                opt=pd.read_csv(opt_file)
                st.write("Options columns detected:",", ".join(opt.columns))
                rename={}
                aliases={"strike":["STRIKE_PR","strike","Strike Price"],"option_type":["OPTION_TYP","option_type","Instrument Type"],
                         "open_interest":["OPEN_INT","open_interest","OI"],"volume":["CONTRACTS","volume","VOLUME"],
                         "expiry":["EXPIRY_DT","expiry","Expiry Date"],"close":["CLOSE","close","Settle Price"]}
                for target,choices in aliases.items():
                    source=next((c for c in choices if c in opt.columns),None)
                    if source: rename[source]=target
                opt=opt.rename(columns=rename)
                if {"strike","option_type","open_interest"}.issubset(opt.columns):
                    opt["strike"]=pd.to_numeric(opt["strike"],errors="coerce")
                    opt["open_interest"]=pd.to_numeric(opt["open_interest"],errors="coerce").fillna(0)
                    opt["option_type"]=opt["option_type"].astype(str).str.upper()
                    opt=opt.dropna(subset=["strike"])
                    side=opt[opt.option_type.isin(["CE","PE","CALL","PUT"])]
                    side["Side"]=side["option_type"].replace({"CE":"CALL","PE":"PUT"})
                    oi=side.groupby(["strike","Side"],as_index=False)["open_interest"].sum()
                    fig=px.bar(oi,x="strike",y="open_interest",color="Side",barmode="group",
                               title="Uploaded NSE option open interest by strike")
                    st.plotly_chart(polish(fig,360),use_container_width=True)
                    calls=side.loc[side.Side=="CALL","open_interest"].sum()
                    puts=side.loc[side.Side=="PUT","open_interest"].sum()
                    metric_row([("CALL OI",f"{calls:,.0f}","uploaded file"),
                                ("PUT OI",f"{puts:,.0f}","uploaded file"),
                                ("PUT / CALL OI",f"{puts/calls:.2f}" if calls else "—","descriptive")])
                    st.dataframe(side.head(150),use_container_width=True)
                    st.download_button("Download cleaned options CSV",side.to_csv(index=False).encode("utf-8"),
                                       "cleaned_nse_options.csv","text/csv")
                else:
                    st.warning("Options file needs strike, option type (CE/PE or CALL/PUT), and open interest columns.")
            except Exception as exc:
                st.error(f"Could not parse options CSV: {exc}")
        st.caption("The dedicated index-futures importer handles UDiFF F&O bhavcopy ZIP/CSV and legacy futures headers. This tab remains for options files.")



# Exchange adapters intentionally use subscriber-provided endpoints/credentials.
# Do not scrape exchange websites or embed credentials in source control.
def configured_secret(name, default=""):
    try:
        return str(st.secrets.get(name, os.getenv(name, default)))
    except Exception:
        return os.getenv(name, default)

def fetch_configured_feed(provider, timeout=12):
    """Fetch CSV/JSON from a licensed vendor or exchange endpoint configured by the operator."""
    base = f"{provider.upper()}_FEED_URL"
    url = configured_secret(base).strip()
    token = configured_secret(f"{provider.upper()}_API_TOKEN").strip()
    if not url:
        return None, {"status":"Not configured","detail":f"Set {base} and, if required, {provider.upper()}_API_TOKEN in Streamlit secrets."}
    headers = {"Accept":"application/json, text/csv"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type","").lower()
        if "json" in content_type or response.text.lstrip().startswith(("{","[")):
            payload = response.json()
            if isinstance(payload, dict):
                payload = payload.get("data", payload.get("results", payload.get("records", payload)))
            frame = pd.DataFrame(payload if isinstance(payload,list) else [payload])
        else:
            from io import StringIO
            frame = pd.read_csv(StringIO(response.text))
        if frame.empty:
            return frame, {"status":"Connected · empty response","detail":f"HTTP {response.status_code}; endpoint returned no rows."}
        return frame, {"status":"Connected","detail":f"HTTP {response.status_code} · {len(frame):,} rows · {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC"}
    except Exception as exc:
        return None, {"status":"Error","detail":str(exc)[:240]}

def pipeline_monitor_dashboard():
    st.markdown('<div class="section-kicker">06 / data engineering & feed observability</div>', unsafe_allow_html=True)
    st.subheader("Exchange data pipeline control room")
    st.caption("Independent NSE, BSE and Yahoo Finance connectors · explicit source labels · freshness checks · no silent substitution.")
    st.info("NSE/BSE feeds require a permitted API or licensed vendor connection. Add your endpoint and token in Streamlit Cloud → App settings → Secrets. This app does not scrape exchange webpages or bypass access controls.")
    providers=["NSE","BSE","YAHOO"]
    statuses={}
    outputs={}
    cols=st.columns(3)
    for col, provider in zip(cols,providers):
        with col:
            st.markdown(f"**{provider} PIPELINE**")
            if provider=="YAHOO":
                st.caption("yfinance historical / periodic snapshot")
                if st.button("Test Yahoo connection",key="test_yahoo_pipeline"):
                    try:
                        test=yf.download("RELIANCE.NS",period="5d",interval="1d",progress=False,threads=False)
                        if not test.empty:
                            statuses[provider]={"status":"Connected","detail":f"{len(test)} daily bars · latest {test.index[-1]}"}
                        else:
                            statuses[provider]={"status":"No data","detail":"Yahoo returned an empty response."}
                    except Exception as exc:
                        statuses[provider]={"status":"Error","detail":str(exc)[:200]}
            else:
                st.caption("Subscriber / licensed-vendor REST endpoint")
                st.code(f"{provider}_FEED_URL\n{provider}_API_TOKEN",language="text")
                if st.button(f"Test {provider} feed",key=f"test_{provider.lower()}_pipeline"):
                    frame, status=fetch_configured_feed(provider)
                    statuses[provider]=status
                    outputs[provider]=frame
    # Store button results in session so each independent test is visible across reruns.
    for provider in providers:
        if provider in statuses:
            st.session_state[f"pipeline_status_{provider}"]=statuses[provider]
            if provider in outputs and outputs[provider] is not None:
                st.session_state[f"pipeline_frame_{provider}"]=outputs[provider]
    st.markdown("#### Connection status")
    status_cols=st.columns(3)
    for col, provider in zip(status_cols,providers):
        status=st.session_state.get(f"pipeline_status_{provider}")
        if provider=="YAHOO" and status is None:
            status={"status":"Available · test on demand","detail":"Yahoo connector uses yfinance; availability and delays depend on provider."}
        if status is None:
            status={"status":"Not configured","detail":"Configure the endpoint and token, then test the feed."}
        with col:
            st.metric(provider, status["status"])
            st.caption(status["detail"])
    st.markdown("#### Inspect connected exchange data")
    for provider in ["NSE","BSE"]:
        frame=st.session_state.get(f"pipeline_frame_{provider}")
        if frame is not None and not frame.empty:
            with st.expander(f"{provider} · latest returned records",expanded=True):
                st.dataframe(frame.head(100),use_container_width=True)
                st.download_button(f"Download {provider} feed snapshot",frame.to_csv(index=False).encode("utf-8"),
                                   file_name=f"{provider.lower()}_feed_snapshot.csv",mime="text/csv",key=f"download_{provider}_snapshot")
    st.markdown("#### Yahoo Finance reference pipeline")
    symbol=st.selectbox("Yahoo symbol",["RELIANCE.NS","^NSEI","^NSEBANK","TCS.NS","INFY.NS","BZ=F","GC=F"])
    interval=st.selectbox("Sampling interval",["1m","5m","15m","1h","1d"],index=3)
    period=st.selectbox("Lookback",["1d","5d","1mo","3mo","1y"],index=2)
    if st.button("Fetch Yahoo reference series",type="primary"):
        try:
            hist=yf.download(symbol,period=period,interval=interval,progress=False,threads=False)
            if isinstance(hist.columns,pd.MultiIndex):
                hist.columns=hist.columns.get_level_values(0)
            if hist.empty:
                st.warning("Yahoo returned no observations for this symbol / interval.")
            else:
                close=hist["Close"]
                if isinstance(close,pd.DataFrame): close=close.iloc[:,0]
                st.metric("Latest Yahoo close",f"{float(close.dropna().iloc[-1]):,.3f}",
                          f"{len(close.dropna())} observations")
                fig=go.Figure(go.Scatter(x=close.index,y=close,name=symbol,line=dict(color=CYAN,width=1.8)))
                fig.update_layout(title=f"{symbol} · Yahoo Finance reference data")
                st.plotly_chart(polish(fig,350),use_container_width=True)
                st.dataframe(hist.tail(30),use_container_width=True)
                st.download_button("Download Yahoo series CSV",hist.to_csv().encode("utf-8"),
                                   file_name=f"yahoo_{symbol.replace('^','')}_{interval}.csv",mime="text/csv")
        except Exception as exc:
            st.error(f"Yahoo request failed: {exc}")
    st.caption("Operational note: Streamlit Cloud runs only while the app is active and is not a durable scheduler. For continuous ingestion, run a separate worker on an always-on host, persist licensed data to a database, and have Streamlit read that store. Do not treat browser refresh as a guaranteed market feed.")

st.markdown("""
<div class="hero">
  <div class="eyebrow">DEV DUTTA · QUANTITATIVE RESEARCH LAB</div>
  <h1>INDIA QUANT DESK</h1>
  <p>Systematic strategies · execution research · NSE market structure · Reliance market linkage</p>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("## INDIA QUANT DESK")
st.sidebar.caption("Research terminal · educational build")
page = st.sidebar.radio("Workspace", ["Trading & HFT", "India Markets · INR", "US Markets · USD", "India Equities · INR", "US Equities · USD", "India Portfolio & Risk · INR", "US Portfolio & Risk · USD", "India Multi-Asset · INR", "US Multi-Asset · USD", "Futures & Options", "Data Pipelines", "Stochastic Calculus & Astro Lab"])
st.sidebar.markdown("---")
st.sidebar.caption("DATA INTEGRITY")
st.sidebar.caption("Synthetic strategy sample · Yahoo Finance market proxy · no live execution")
if page == "Trading & HFT":
    pairs_dashboard()
elif page == "India Markets · INR":
    market_dashboard()
elif page == "US Markets · USD":
    us_market_dashboard()
elif page == "India Equities · INR":
    equity_markets_dashboard("INR")
elif page == "US Equities · USD":
    equity_markets_dashboard("USD")
elif page == "India Portfolio & Risk · INR":
    risk_dashboard("INR")
elif page == "US Portfolio & Risk · USD":
    risk_dashboard("USD")
elif page == "India Multi-Asset · INR":
    data_explorer_dashboard("INR")
elif page == "US Multi-Asset · USD":
    data_explorer_dashboard("USD")
elif page == "Futures & Options":
    fo_dashboard()
elif page == "Stochastic Calculus & Astro Lab":
    stochastic_astro_dashboard()
else:
    pipeline_monitor_dashboard()
st.markdown("---")
st.markdown('<div class="small-note">RESEARCH ONLY · Not investment advice · Not a live trading system · Validate with licensed exchange data before drawing market conclusions.</div>', unsafe_allow_html=True)
