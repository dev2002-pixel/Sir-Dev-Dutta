"""SVG visualizations for Treasury Working Capital Analytics."""

from __future__ import annotations

from pathlib import Path
from html import escape
import pandas as pd

BLUE, GREEN, RED, GRID, AMBER = "#1f4e79", "#2a9d8f", "#c0392b", "#d9e2ea", "#e67e22"


def _points(values: list[float], x0: float, y0: float, width: float, height: float) -> str:
    low, high = min(values), max(values)
    span = high - low or 1
    return " ".join(f"{x0 + i * width / max(len(values) - 1, 1):.1f},{y0 + height - (value - low) / span * height:.1f}"
                    for i, value in enumerate(values))


def _write(path: Path, body: str, width: int = 1000, height: int = 520) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">' 
                    '<style>text{font-family:Arial,sans-serif;fill:#243746}.title{font-size:24px;font-weight:bold}.label{font-size:13px}.small{font-size:11px}</style>'
                    + body + "</svg>\n")
    return path


def _axes(labels: list[str], x0: int, y0: int, width: int, height: int) -> str:
    grid = "".join(f'<line x1="{x0}" y1="{y0 + i * height / 4:.1f}" x2="{x0 + width}" y2="{y0 + i * height / 4:.1f}" stroke="{GRID}"/>' for i in range(5))
    xlabels = "".join(f'<text class="small" x="{x0 + i * width / max(len(labels)-1,1):.1f}" y="425" text-anchor="middle">{escape(label)}</text>' for i, label in enumerate(labels))
    return grid + xlabels


def create_working_capital_chart(metrics: pd.DataFrame, output_path: Path) -> Path:
    """Create a trend chart for CCC and net working capital."""
    ccc = metrics["cash_conversion_cycle"].tolist()
    nwc = (metrics["net_working_capital"] / 1_000_000).tolist()
    labels = pd.to_datetime(metrics["month"]).dt.strftime("%b %Y").tolist()
    x0, y0, width, height = 95, 95, 760, 300
    body = (f'<text class="title" x="50" y="45">Working Capital Efficiency</text>{_axes(labels,x0,y0,width,height)}'
            f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+height}" stroke="#607080"/>'
            f'<line x1="{x0}" y1="{y0+height}" x2="{x0+width}" y2="{y0+height}" stroke="#607080"/>'
            f'<polyline points="{_points(ccc,x0,y0,width,height)}" fill="none" stroke="{BLUE}" stroke-width="4"/>'
            f'<polyline points="{_points(nwc,x0,y0,width,height)}" fill="none" stroke="{GREEN}" stroke-width="4"/>'
            f'<text class="label" x="95" y="470">● CCC: {ccc[-1]:.2f} days</text>'
            f'<text class="label" x="440" y="470">■ NWC: ${nwc[-1]:.2f}m</text>')
    return _write(output_path, body)


def create_efficiency_metrics_chart(metrics: pd.DataFrame, output_path: Path) -> Path:
    """Create DSO, DIO and DPO monthly trend chart."""
    labels = pd.to_datetime(metrics["month"]).dt.strftime("%b %Y").tolist()
    x0, y0, width, height = 80, 90, 820, 300
    series = [("dso", "DSO", BLUE), ("dio", "DIO", GREEN), ("dpo", "DPO", AMBER)]
    lines = "".join(f'<polyline points="{_points(metrics[key].tolist(),x0,y0,width,height)}" fill="none" stroke="{color}" stroke-width="4"/>' for key, _, color in series)
    legend = "".join(f'<text class="label" x="{80+i*250}" y="470">● {name}: {metrics[key].iloc[-1]:.1f} days</text>' for i,(key,name,_) in enumerate(series))
    body = f'<text class="title" x="50" y="45">DSO, DIO and DPO Trend</text>{_axes(labels,x0,y0,width,height)}{lines}{legend}'
    return _write(output_path, body)


def create_balance_sheet_chart(metrics: pd.DataFrame, output_path: Path) -> Path:
    """Create AR, inventory and AP balance trends in USD millions."""
    labels = pd.to_datetime(metrics["month"]).dt.strftime("%b %Y").tolist()
    x0, y0, width, height = 80, 90, 820, 300
    series = [("accounts_receivable", "Accounts receivable", BLUE), ("inventory", "Inventory", GREEN), ("accounts_payable", "Accounts payable", RED)]
    lines = "".join(f'<polyline points="{_points((metrics[key]/1_000_000).tolist(),x0,y0,width,height)}" fill="none" stroke="{color}" stroke-width="4"/>' for key,_,color in series)
    legend = "".join(f'<text class="label" x="{80+i*290}" y="470">● {name}: ${metrics[key].iloc[-1]/1_000_000:.1f}m</text>' for i,(key,name,_) in enumerate(series))
    body = f'<text class="title" x="50" y="45">Working Capital Balance Sheet Drivers</text>{_axes(labels,x0,y0,width,height)}{lines}{legend}'
    return _write(output_path, body)


def create_cash_flow_chart(forecast: pd.DataFrame, output_path: Path) -> Path:
    """Create monthly cash inflow, outflow and net cash-flow trends."""
    labels = pd.to_datetime(forecast["date"]).dt.strftime("%b %d").tolist()
    inflow = (forecast["inflows"]/1_000_000).tolist()
    outflow = (forecast["outflows"]/1_000_000).tolist()
    net = (forecast["net_cash_flow"]/1_000_000).tolist()
    x0,y0,width,height=80,90,820,300
    lines = (f'<polyline points="{_points(inflow,x0,y0,width,height)}" fill="none" stroke="{GREEN}" stroke-width="4"/>'
             f'<polyline points="{_points(outflow,x0,y0,width,height)}" fill="none" stroke="{RED}" stroke-width="4"/>'
             f'<polyline points="{_points(net,x0,y0,width,height)}" fill="none" stroke="{BLUE}" stroke-width="4"/>')
    body = f'<text class="title" x="50" y="45">Cash Flow Dynamics</text>{_axes(labels,x0,y0,width,height)}{lines}'
    body += f'<text class="label" x="80" y="470">● Inflows ${inflow[-1]:.2f}m</text><text class="label" x="340" y="470">● Outflows ${outflow[-1]:.2f}m</text><text class="label" x="610" y="470">● Net ${net[-1]:.2f}m</text>'
    return _write(output_path, body)


def create_liquidity_chart(forecast: pd.DataFrame, scenarios: pd.DataFrame, threshold: float, output_path: Path) -> Path:
    """Create forecast and stress-case charts with a liquidity threshold."""
    cash = (forecast["closing_cash"] / 1_000_000).tolist()
    minimums = (scenarios["minimum_cash"] / 1_000_000).tolist()
    threshold_m = threshold / 1_000_000
    x0, y0, width, height = 75, 105, 410, 250
    minv, maxv = min(cash + [threshold_m]) - .1, max(cash) + .1
    threshold_y = y0 + height - (threshold_m - minv) / (maxv - minv) * height
    labels = pd.to_datetime(forecast["date"]).dt.strftime("%b %d").tolist()
    forecast_labels = "".join(f'<text class="small" x="{x0+i*width/max(len(cash)-1,1):.1f}" y="380" text-anchor="middle">{escape(label)}</text>' for i,label in enumerate(labels))
    bars = ""
    for i,(minimum,breached) in enumerate(zip(minimums,scenarios["threshold_breached"])):
        bar_height=max(0,minimum-.85)/.35*height
        color=RED if breached else GREEN
        bars += f'<rect x="{555+i*43}" y="{y0+height-bar_height:.1f}" width="29" height="{bar_height:.1f}" fill="{color}"/><text class="small" x="{569+i*43}" y="385" text-anchor="middle">{i+1}</text>'
    body=(f'<text class="title" x="50" y="45">Liquidity Forecast and Stress Test</text>'
          f'<text class="label" x="75" y="78">Closing cash ($m)</text><line x1="{x0}" y1="{y0+height}" x2="{x0+width}" y2="{y0+height}" stroke="#607080"/>'
          f'<polyline points="{_points(cash,x0,y0,width,height)}" fill="none" stroke="{BLUE}" stroke-width="4"/>'
          f'<line x1="{x0}" y1="{threshold_y:.1f}" x2="{x0+width}" y2="{threshold_y:.1f}" stroke="{RED}" stroke-width="3" stroke-dasharray="8 6"/>'
          f'<text class="small" x="{x0+8}" y="{threshold_y-7:.1f}">Threshold ${threshold_m:.1f}m</text>{forecast_labels}'
          f'<text class="label" x="555" y="78">Minimum cash by stress case ($m)</text><line x1="540" y1="{y0+height}" x2="955" y2="{y0+height}" stroke="#607080"/>'
          f'{bars}<text class="small" x="555" y="430">Green: threshold maintained</text><text class="small" x="755" y="430">Red: threshold breached</text>')
    return _write(output_path, body)
