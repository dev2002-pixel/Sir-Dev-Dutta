"""Interactive stochastic-calculus and astro-market event-study workspace."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
import json
import yfinance as yf


def _polish(fig, height=360):
    fig.update_layout(template="plotly_dark", height=height,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#E7EEF8", family="Manrope, sans-serif"),
                      margin=dict(l=15, r=15, t=48, b=15),
                      legend=dict(orientation="h", y=1.12))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#263449")
    return fig


def _gbm_paths(s0, mu, sigma, years, steps, n_paths, seed):
    rng = np.random.default_rng(seed)
    dt = years / steps
    z = rng.standard_normal((steps, n_paths))
    increments = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z
    log_paths = np.vstack([np.zeros(n_paths), np.cumsum(increments, axis=0)])
    return s0 * np.exp(log_paths), np.linspace(0, years, steps + 1)


def _ito_terms(kind, s, t, power, time_rate, mu, sigma):
    if kind == "Log price: f(S,t) = log(S) + a t":
        f = np.log(s) + time_rate * t
        fs, fss, ft = 1.0 / s, -1.0 / s**2, time_rate
    elif kind == "Squared price: f(S,t) = S² exp(a t)":
        e = np.exp(time_rate * t)
        f, fs, fss, ft = s**2 * e, 2*s*e, 2*e, time_rate*s**2*e
    elif kind == "Square-root price: f(S,t) = sqrt(S) exp(a t)":
        e = np.exp(time_rate * t)
        f, fs, fss, ft = np.sqrt(s)*e, 0.5*e/np.sqrt(s), -0.25*e/s**1.5, time_rate*np.sqrt(s)*e
    else:
        e = np.exp(time_rate * t)
        f = s**power * e
        fs = power * s**(power-1) * e
        fss = power*(power-1)*s**(power-2)*e
        ft = time_rate*f
    drift = ft + mu*s*fs + 0.5*sigma**2*s**2*fss
    diffusion = sigma*s*fs
    return f, fs, fss, ft, drift, diffusion


@st.cache_data(ttl=900, show_spinner=False)
def _commodity_prices(start, end):
    raw = yf.download(["BZ=F", "GC=F"], start=start, end=end,
                      auto_adjust=True, progress=False, threads=True)
    if raw is None or raw.empty:
        return pd.DataFrame()
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame()
    if isinstance(close.columns, pd.MultiIndex):
        close.columns = close.columns.get_level_values(-1)
    close = close.rename(columns={"BZ=F": "Brent crude", "GC=F": "Gold"})
    return close.apply(pd.to_numeric, errors="coerce").dropna(how="all").sort_index()


@st.cache_data(ttl=900, show_spinner=False)
def _asset_history(ticker, start, end):
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False, threads=True)
    if raw is None or raw.empty:
        return pd.DataFrame()
    close = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw[['Close']]
    if isinstance(close, pd.Series):
        close = close.to_frame()
    if isinstance(close.columns, pd.MultiIndex):
        close.columns = close.columns.get_level_values(-1)
    if ticker in close.columns:
        close = close[[ticker]]
    close = close.apply(pd.to_numeric, errors='coerce').dropna(how='all')
    close.columns = ['Adjusted close']
    return close.sort_index()

def _tradingview_chart(symbol, interval='D', height=560):
    cfg = {'autosize':True,'symbol':symbol,'interval':interval,'timezone':'Etc/UTC','theme':'dark','style':'1','locale':'en','enable_publishing':False,'allow_symbol_change':True,'hide_side_toolbar':False,'withdateranges':True,'details':True,'studies':['STD;SMA','STD;EMA','STD;RSI'],'container_id':'tv_stochastic_chart'}
    html = '<div id="tv_stochastic_chart" style="height:' + str(height) + 'px;width:100%"></div><script src="https://s3.tradingview.com/tv.js"></script><script>new TradingView.widget(' + json.dumps(cfg) + ');</script>'
    components.html(html, height=height+20, scrolling=False)

def stochastic_astro_dashboard():
    st.markdown('<div class="section-kicker">07 / mathematical finance & alternative research</div>', unsafe_allow_html=True)
    st.title("Stochastic Calculus & Astro-Market Research")
    st.caption("GBM simulation · Itô calculus · commodity event studies · transparent assumptions")
    math_tab, astro_tab, guide_tab = st.tabs(["Market-calibrated GBM & Itô", "Crude & gold · astro event study", "Concepts & assumptions"])

    with math_tab:
        st.subheader("Market-calibrated GBM & Itô research")
        st.caption("Select a market instrument, estimate GBM parameters from adjusted historical closes, inspect diagnostics and compare the Python calibration with a TradingView chart.")
        presets = {
            "India · INR": {"Reliance":"RELIANCE.NS","NIFTY 50":"^NSEI","Bank NIFTY":"^NSEBANK","HDFC Bank":"HDFCBANK.NS","TCS":"TCS.NS","Infosys":"INFY.NS"},
            "US · USD": {"Apple":"AAPL","Microsoft":"MSFT","NVIDIA":"NVDA","S&P 500":"^GSPC","Nasdaq":"^IXIC","SPY":"SPY","Tesla":"TSLA"},
            "Commodities": {"Gold":"GC=F","Brent crude":"BZ=F","WTI crude":"CL=F","Silver":"SI=F"}
        }
        m1,m2,m3 = st.columns([1,1.3,1])
        with m1: region = st.selectbox("Asset universe", list(presets), key="stoch_region")
        with m2: asset_label = st.selectbox("Instrument", list(presets[region]), key="stoch_asset_" + region)
        with m3: interval_tv = st.selectbox("TradingView timeframe", ["5","15","60","240","D","W","M"], index=4, key="stoch_tv_interval")
        yahoo_ticker = presets[region][asset_label]
        default_tv = {"RELIANCE.NS":"NSE:RELIANCE","^NSEI":"NSE:NIFTY","^NSEBANK":"NSE:BANKNIFTY","HDFCBANK.NS":"NSE:HDFCBANK","TCS.NS":"NSE:TCS","INFY.NS":"NSE:INFY","AAPL":"NASDAQ:AAPL","MSFT":"NASDAQ:MSFT","NVDA":"NASDAQ:NVDA","^GSPC":"SP:SPX","^IXIC":"NASDAQ:IXIC","SPY":"AMEX:SPY","TSLA":"NASDAQ:TSLA","GC=F":"COMEX:GC1!","BZ=F":"NYMEX:BR1!","CL=F":"NYMEX:CL1!","SI=F":"COMEX:SI1!"}.get(yahoo_ticker, yahoo_ticker)
        with st.form("stoch_custom_symbol_form"):
            custom_tv = st.text_input("TradingView symbol override (optional)", placeholder="e.g. NASDAQ:AMD, NSE:SBIN, NYSE:IBM")
            apply_tv = st.form_submit_button("Apply chart symbol")
        if apply_tv and custom_tv.strip():
            st.session_state["stoch_tv_override"] = custom_tv.strip().upper()
        if apply_tv and not custom_tv.strip():
            st.session_state.pop("stoch_tv_override", None)
        tv_symbol = st.session_state.get("stoch_tv_override", default_tv)
        tv_tab, cal_tab = st.tabs(["TradingView live chart", "Historical calibration & GBM fit"])
        with tv_tab:
            st.markdown("**" + asset_label + " · " + tv_symbol + "**")
            _tradingview_chart(tv_symbol, interval_tv, 560)
            st.caption("TradingView is an embedded visualization. It does not expose its chart data to the Python estimator; the estimator below independently downloads adjusted historical closes from Yahoo Finance.")
        with cal_tab:
            data_ticker = st.text_input("Historical data ticker (Yahoo Finance format)", value=yahoo_ticker, help="This ticker powers the Python estimator. Examples: RELIANCE.NS, ^NSEI, AAPL, GC=F, BZ=F.", key="stoch_data_ticker_" + region).strip()
            d1,d2 = st.columns(2)
            with d1: hist_start = st.date_input("Calibration start", value=pd.Timestamp("2018-01-01").date(), key="stoch_hist_start")
            with d2: hist_end = st.date_input("Calibration end (exclusive)", value=pd.Timestamp.today().date()+pd.Timedelta(days=1), key="stoch_hist_end")
            if hist_start >= hist_end:
                st.error("Calibration start must precede end date.")
            else:
                with st.spinner("Downloading adjusted historical prices and fitting GBM parameters..."):
                    hist = _asset_history(data_ticker, str(hist_start), str(hist_end))
                if hist.empty or len(hist) < 30:
                    st.warning("Not enough historical observations were returned. Try another instrument or date range.")
                else:
                    px_series = hist["Adjusted close"].dropna()
                    logret = np.log(px_series).diff().dropna()
                    ann_factor = 252.0
                    sigma_hat = float(logret.std(ddof=0) * np.sqrt(ann_factor))
                    mu_hat = float(logret.mean() * ann_factor + 0.5 * sigma_hat**2)
                    drift_log = float(logret.mean() * ann_factor)
                    rolling_vol = logret.rolling(63).std(ddof=0) * np.sqrt(ann_factor)
                    r1,r2,r3,r4 = st.columns(4)
                    r1.metric("GBM μ estimate", f"{mu_hat:.2%}")
                    r2.metric("Annual σ estimate", f"{sigma_hat:.2%}")
                    r3.metric("Log-return drift", f"{drift_log:.2%}")
                    r4.metric("Observations", f"{len(logret):,}")
                    st.latex(r"\hat{\sigma}=\sqrt{252}\,s(r_t),\qquad \hat{\mu}=252\,\bar r+\frac{1}{2}\hat{\sigma}^{2}")
                    fit_fig = go.Figure()
                    fit_fig.add_trace(go.Scatter(x=px_series.index,y=px_series,name="Adjusted close",line=dict(color="#39D0C8",width=2)))
                    fit_fig.update_layout(title=asset_label + " · historical adjusted close",yaxis_title="Price")
                    st.plotly_chart(_polish(fit_fig,330),use_container_width=True)
                    vol_fig = go.Figure()
                    vol_fig.add_trace(go.Scatter(x=rolling_vol.index,y=rolling_vol,name="63-session annualized volatility",line=dict(color="#F4A261",width=2),fill="tozeroy"))
                    vol_fig.add_hline(y=sigma_hat,line_dash="dash",line_color="#39D0C8",annotation_text="Full-sample σ")
                    vol_fig.update_layout(title="Rolling realized volatility · regime stability",yaxis_title="Annualized volatility")
                    st.plotly_chart(_polish(vol_fig,300),use_container_width=True)
                    residual = logret - logret.mean()
                    diag1,diag2,diag3 = st.columns(3)
                    diag1.metric("Daily return skew",f"{logret.skew():.3f}")
                    diag2.metric("Daily return excess kurtosis",f"{logret.kurtosis():.3f}")
                    diag3.metric("Return autocorrelation · lag 1",f"{logret.autocorr(1):.3f}")
                    st.caption("Large skew/kurtosis, autocorrelation or unstable rolling volatility are warnings that constant-parameter GBM may be a poor fit. These are diagnostics, not a formal goodness-of-fit test.")
                    observed_log_drift = float(logret.mean() * 252)
                    theoretical_log_drift = mu_hat - 0.5 * sigma_hat**2
                    st.markdown("#### Itô log-price consistency check")
                    st.latex(r"d\\log S_t = (\\mu-\\frac{1}{2}\\sigma^2)dt+\\sigma dW_t")
                    q1,q2 = st.columns(2)
                    q1.metric("Observed annualized mean log return", f"{observed_log_drift:.2%}")
                    q2.metric("GBM / Itô implied log drift", f"{theoretical_log_drift:.2%}")
                    st.caption("Under the fitted GBM parameterization, μ − ½σ² equals the annualized sample mean log return by construction. This is a parameterization identity, not independent model validation.")
                    st.download_button("Download calibration data",hist.assign(LogReturn=logret.reindex(hist.index)).to_csv().encode("utf-8"),file_name="gbm_"+data_ticker.replace("^","").replace("=","_")+"_calibration.csv",mime="text/csv")
                    st.session_state["stoch_fit_mu"] = mu_hat
                    st.session_state["stoch_fit_sigma"] = max(sigma_hat,0.001)
                    if st.button("Use fitted μ and σ in GBM simulator",type="primary",key="apply_fitted_gbm"):
                        st.session_state["gbm_mu_input"] = mu_hat
                        st.session_state["gbm_sigma_input"] = max(sigma_hat,0.001)
                        st.success("Calibration values saved for the simulator below. Re-run the page if inputs do not refresh.")
        st.divider()
        st.subheader("GBM simulation · calibrated or user-defined parameters")
        st.latex(r"dS_t = \mu S_t\,dt + \sigma S_t\,dW_t")
        st.latex(r"dS_t = \mu S_t\,dt + \sigma S_t\,dW_t")
        st.write("The exact time-step solution is S(t+Δt) = S(t) exp[(μ − σ²/2)Δt + σ√Δt Z], where Z is standard normal.")
        a, b, c = st.columns(3)
        with a:
            s0 = st.number_input("Initial price S₀", min_value=0.01, value=100.0, step=5.0)
            mu = st.number_input("Annual drift μ", value=float(st.session_state.get("gbm_mu_input",0.08)), step=0.01, format="%.3f", key="gbm_mu_input")
        with b:
            sigma = st.number_input("Annual volatility σ", min_value=0.001, value=float(st.session_state.get("gbm_sigma_input",0.25)), step=0.01, format="%.3f", key="gbm_sigma_input")
            years = st.number_input("Horizon (years)", min_value=0.05, value=1.0, step=0.25)
        with c:
            n_paths = st.select_slider("Simulation paths", options=[250, 500, 1000, 2500, 5000], value=1000)
            steps = st.select_slider("Time steps", options=[50, 100, 252, 500, 1000], value=252)
        seed = st.number_input("Random seed (reproducibility)", min_value=0, max_value=999999, value=42)
        paths, times = _gbm_paths(s0, mu, sigma, years, steps, n_paths, int(seed))
        terminal = paths[-1]
        theoretical_mean = s0*np.exp(mu*years)
        theoretical_median = s0*np.exp((mu-0.5*sigma**2)*years)
        theoretical_std = theoretical_mean*np.sqrt(np.exp(sigma**2*years)-1)
        m = st.columns(4)
        m[0].metric("Simulated mean", f"{terminal.mean():,.2f}")
        m[1].metric("Theoretical mean", f"{theoretical_mean:,.2f}")
        m[2].metric("Theoretical median", f"{theoretical_median:,.2f}")
        m[3].metric("Theoretical terminal σ", f"{theoretical_std:,.2f}")
        fig = go.Figure()
        for i in range(min(80, n_paths)):
            fig.add_trace(go.Scatter(x=times, y=paths[:, i], mode="lines",
                                     line=dict(width=0.8), opacity=0.22, showlegend=False,
                                     hovertemplate="t=%{x:.2f}<br>S=%{y:.2f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=times, y=paths.mean(axis=1), name="Simulated mean",
                                 line=dict(color="#39D0C8", width=2.5)))
        fig.add_hline(y=theoretical_mean, line_dash="dash", line_color="#F4A261",
                      annotation_text="Theoretical E[S(T)]")
        fig.update_layout(title="GBM sample paths", xaxis_title="Time (years)", yaxis_title="Price")
        st.plotly_chart(_polish(fig, 440), use_container_width=True)
        hist = go.Figure(go.Histogram(x=terminal, nbinsx=45, name="Terminal price",
                                      marker_color="#56B4E9"))
        hist.add_vline(x=theoretical_mean, line_dash="dash", line_color="#F4A261")
        hist.update_layout(title="Terminal-price distribution", xaxis_title="S(T)", yaxis_title="Path count")
        st.plotly_chart(_polish(hist, 300), use_container_width=True)
        st.dataframe(pd.DataFrame({"Statistic":["5th percentile","Median","Mean","95th percentile"],
                                   "Simulated":[*np.quantile(terminal,[.05,.5,.5,.95])[:2],
                                                terminal.mean(),np.quantile(terminal,.95)],
                                   "Analytical":[s0*np.exp((mu-.5*sigma**2)*years+sigma*np.sqrt(years)*-1.644854), theoretical_median, theoretical_mean, s0*np.exp((mu-.5*sigma**2)*years+sigma*np.sqrt(years)*1.644854)]}),
                     hide_index=True, use_container_width=True)
        st.caption("GBM assumes constant drift and volatility, continuous paths and log-normal prices. It omits jumps, stochastic volatility, seasonality, convenience yield, storage costs and market microstructure. The displayed drift is a user assumption, not an estimated forecast.")

        st.divider()
        st.subheader("Itô's lemma · pointwise coefficient calculator")
        st.latex(r"df(t,S_t)=\left(f_t+\mu S f_S+\frac{1}{2}\sigma^2S^2f_{SS}\right)dt+\sigma S f_S\,dW_t")
        kind = st.selectbox("Function f(t,S)", [
            "Log price: f(S,t) = log(S) + a t",
            "Squared price: f(S,t) = S² exp(a t)",
            "Square-root price: f(S,t) = sqrt(S) exp(a t)",
            "Power-exponential: f(S,t) = Sᵖ exp(a t)"
        ])
        x, y, z = st.columns(3)
        with x:
            s_eval = st.number_input("Evaluation price S", min_value=0.001, value=float(s0), key="ito_s")
            t_eval = st.number_input("Evaluation time t (years)", min_value=0.0, value=0.0, key="ito_t")
        with y:
            power = st.number_input("Power p", value=2.0, step=0.25, key="ito_power")
            time_rate = st.number_input("Time coefficient a", value=0.0, step=0.05, key="ito_a")
        with z:
            ito_mu = st.number_input("GBM drift μ", value=float(mu), step=0.01, key="ito_mu")
            ito_sigma = st.number_input("GBM volatility σ", min_value=0.001, value=float(sigma), step=0.01, key="ito_sigma")
        f, fs, fss, ft, drift, diffusion = _ito_terms(kind, s_eval, t_eval, power, time_rate, ito_mu, ito_sigma)
        vals = st.columns(4)
        vals[0].metric("f(t,S)", f"{f:,.5f}")
        vals[1].metric("fₜ", f"{ft:,.5f}")
        vals[2].metric("fₛ", f"{fs:,.5f}")
        vals[3].metric("fₛₛ", f"{fss:,.5f}")
        st.success(f"At S={s_eval:.3f}, t={t_eval:.3f}:  df = ({drift:.6f}) dt + ({diffusion:.6f}) dW")
        st.code(
            f"Drift = f_t + μ S f_S + 0.5 σ² S² f_SS = {drift:.8f}\n"
            f"Diffusion = σ S f_S = {diffusion:.8f}\n"
            f"Therefore df = {drift:.8f} dt + {diffusion:.8f} dW",
            language="text")
        st.caption("The calculator applies Itô's lemma to the selected smooth function under the stated GBM. Coefficients are local values at the selected (t,S), not a full pathwise integral.")

    with astro_tab:
        st.subheader("Planetary-event dates vs Brent crude and gold")
        st.warning("Astrology is not an established financial forecasting method. This workspace is an exploratory event-study tool only; it cannot establish causation or validate astrological effects.")
        st.write("Upload a dated event calendar, then compare event-window commodity returns with non-event observations. No planetary ephemeris is generated or assumed by this app.")
        st.markdown("Required event CSV columns: date, body, event. Example: 2026-01-15, Mars, retrograde_station.")
        events_file = st.file_uploader("Upload planetary transit / event calendar CSV", type=["csv"], key="astro_events_csv")
        start_col, end_col = st.columns(2)
        with start_col:
            astro_start = st.date_input("Commodity history start", value=pd.Timestamp("2015-01-01").date(), key="astro_start")
        with end_col:
            astro_end = st.date_input("Commodity history end (exclusive)", value=pd.Timestamp.today().date()+pd.Timedelta(days=1), key="astro_end")
        if st.button("Load Brent & gold research prices", key="load_astro_prices"):
            _commodity_prices.clear()
        prices = _commodity_prices(str(astro_start), str(astro_end))
        if prices.empty:
            st.info("No commodity history returned. Refresh or adjust the dates; Yahoo Finance is a research proxy, not an exchange feed.")
        else:
            returns = prices.pct_change()
            latest = prices.ffill().iloc[-1]
            mc = st.columns(2)
            mc[0].metric("Latest Brent proxy", f"{latest.get('Brent crude', np.nan):,.2f}")
            mc[1].metric("Latest gold proxy", f"{latest.get('Gold', np.nan):,.2f}")
            price_fig = go.Figure()
            for col in prices:
                series = prices[col].dropna()
                if not series.empty:
                    price_fig.add_trace(go.Scatter(x=series.index, y=series/series.iloc[0]*100,
                                                   name=col, mode="lines"))
            price_fig.update_layout(title="Brent and gold · rebased to 100", yaxis_title="Indexed price")
            st.plotly_chart(_polish(price_fig, 330), use_container_width=True)
            if events_file is not None:
                try:
                    events = pd.read_csv(events_file)
                    required = {"date","body","event"}
                    if not required.issubset(events.columns):
                        st.error("Event CSV must contain date, body and event columns.")
                    else:
                        events["date"] = pd.to_datetime(events["date"], errors="coerce").dt.tz_localize(None)
                        events["body"] = events["body"].astype(str)
                        events["event"] = events["event"].astype(str)
                        events = events.dropna(subset=["date"]).sort_values("date")
                        events["matched_trade_date"] = events["date"].apply(
                            lambda d: prices.index[prices.index >= d][0] if (prices.index >= d).any() else pd.NaT)
                        event_returns = []
                        for _, event in events.dropna(subset=["matched_trade_date"]).iterrows():
                            idx = prices.index.get_loc(event["matched_trade_date"])
                            row = {"date":event["date"],"matched_trade_date":event["matched_trade_date"],
                                   "body":event["body"],"event":event["event"]}
                            for asset in prices.columns:
                                for horizon in [1,3,5,10]:
                                    if idx+horizon < len(prices):
                                        p0, p1 = prices[asset].iloc[idx], prices[asset].iloc[idx+horizon]
                                        row[f"{asset} +{horizon}d %"] = (p1/p0-1)*100 if pd.notna(p0) and pd.notna(p1) and p0 else np.nan
                            event_returns.append(row)
                        study = pd.DataFrame(event_returns)
                        if study.empty:
                            st.info("No event dates overlap the selected commodity history.")
                        else:
                            st.markdown("#### Event-window forward returns")
                            st.caption("Forward returns use the next available commodity trading session on or after each event date. Horizons count observed rows, not calendar days.")
                            st.dataframe(study.style.format({c:"{:.2f}%" for c in study.columns if c.endswith("%")}, na_rep="—"),
                                         use_container_width=True, height=350)
                            horizon_cols = [c for c in study if c.endswith("+5d %")]
                            if horizon_cols:
                                summary = study.groupby(["body","event"])[horizon_cols].agg(["count","mean","median"])
                                st.markdown("#### Grouped five-session event-window summary")
                                st.dataframe(summary, use_container_width=True)
                                fig = px.bar(study, x="event", y=horizon_cols[0], color="body",
                                             title=f"Five-session forward return · {horizon_cols[0].replace(' +5d %','')}",
                                             barmode="group")
                                st.plotly_chart(_polish(fig, 330), use_container_width=True)
                            st.download_button("Download event-study results", study.to_csv(index=False).encode("utf-8"),
                                               "crude_gold_astro_event_study.csv", "text/csv")
                            st.caption("Descriptive only: event clustering, overlapping windows, multiple testing, omitted macroeconomic variables and selection bias can create spurious patterns. Use out-of-sample tests and a pre-registered hypothesis before interpreting any relationship.")
                except Exception as exc:
                    st.error(f"Could not process event calendar: {exc}")
            else:
                st.info("Upload your event calendar CSV to run the event-window comparison.")
            st.download_button("Download event calendar template",
                "date,body,event\n2026-01-15,Mars,retrograde_station\n2026-03-20,Venus,ingress\n".encode("utf-8"),
                "planetary_events_template.csv","text/csv")

    with guide_tab:
        st.subheader("Concept map")
        st.markdown("""
**1 · Brownian motion**
- Independent increments, normally distributed increments and continuous paths.
- Quadratic variation: [W]_t = t.

**2 · Geometric Brownian motion**
- dS = μS dt + σS dW.
- Exact solution: S_t = S_0 exp[(μ − σ²/2)t + σW_t].
- E[S_t] = S_0 exp(μt); median = S_0 exp[(μ − σ²/2)t].

**3 · Itô's lemma**
- For f(t,S), include the second-order correction ½ f_SS (dS)².
- Since (dW)² = dt, the correction contributes ½ σ²S²f_SS dt.
- Example: d log(S) = (μ − ½σ²)dt + σdW.

**4 · Practical modelling caveats**
- GBM has constant parameters and no jumps; commodity futures also involve carry, storage, convenience yield, rolls and seasonality.
- A spot/continuous-futures proxy is not the same as a specific listed contract.
- An event study is descriptive. Statistical association is not causation, and astrological interpretation is not an evidence-based forecast.
""")
