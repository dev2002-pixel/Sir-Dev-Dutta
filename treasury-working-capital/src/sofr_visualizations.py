"""SOFR-specific SVG charts for the Treasury Working Capital project."""

from __future__ import annotations

from html import escape
from pathlib import Path
import pandas as pd

BLUE, GREEN, RED, AMBER, GRID = "#1f4e79", "#2a9d8f", "#c0392b", "#e67e22", "#d9e2ea"


def _points(values, x0, y0, width, height):
    values = [float(v) for v in values]
    low, high = min(values), max(values)
    span = high - low or 1
    return " ".join(f"{x0+i*width/max(len(values)-1,1):.1f},{y0+height-(v-low)/span*height:.1f}" for i,v in enumerate(values))


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="520" viewBox="0 0 1000 520"><style>text{{font-family:Arial,sans-serif;fill:#243746}}.title{{font-size:24px;font-weight:bold}}.label{{font-size:13px}}.small{{font-size:11px}}</style>{body}</svg>\n')
    return path


def _axes(labels, x0=80, y0=90, width=820, height=300):
    grid = "".join(f'<line x1="{x0}" y1="{y0+i*height/4:.1f}" x2="{x0+width}" y2="{y0+i*height/4:.1f}" stroke="{GRID}"/>' for i in range(5))
    xlabels = "".join(f'<text class="small" x="{x0+i*width/max(len(labels)-1,1):.1f}" y="425" text-anchor="middle">{escape(str(label))}</text>' for i,label in enumerate(labels))
    return grid+xlabels


def create_sofr_forecast_chart(history: pd.DataFrame, prediction: pd.DataFrame, output_path: Path) -> Path:
    """Observed SOFR plus AR(1) forecast and prediction interval."""
    hist = history.copy(); pred = prediction.copy()
    labels = pd.concat([hist["month"], pred["month"]]).dt.strftime("%b %y").tolist()
    values = hist["sofr_pct"].tolist() + pred["sofr_pct"].tolist()
    x0,y0,width,height=80,90,820,300
    body=f'<text class="title" x="50" y="45">SOFR Forecast — AR(1) Model</text>{_axes(labels,x0,y0,width,height)}'
    body += f'<polyline points="{_points(values,x0,y0,width,height)}" fill="none" stroke="{BLUE}" stroke-width="4"/>'
    body += f'<polyline points="{_points(pred["sofr_pct"].tolist(),x0+width*len(hist)/max(len(values)-1,1),y0,width*(len(pred)-1)/max(len(values)-1,1),height)}" fill="none" stroke="{AMBER}" stroke-width="4" stroke-dasharray="8 6"/>'
    body += f'<text class="label" x="80" y="470">Observed: {hist["sofr_pct"].iloc[-1]:.2f}%</text><text class="label" x="330" y="470">First forecast: {pred["sofr_pct"].iloc[0]:.2f}%</text><text class="label" x="650" y="470">Forecast horizon: {len(pred)} months</text>'
    return _write(output_path,body)


def create_sofr_relationship_chart(relationships: pd.DataFrame, output_path: Path) -> Path:
    """Correlation of SOFR with DSO, DIO, DPO, CCC and NWC."""
    body='<text class="title" x="50" y="45">SOFR Relationships with Working Capital</text>'
    for i,row in relationships.iterrows():
        label=str(row["relationship"]).replace("SOFR vs ",""); val=float(row["correlation"]); y=95+i*65; bw=300*abs(val); x=500 if val>=0 else 500-bw
        body += f'<text class="label" x="70" y="{y+20}">{escape(label)}</text><rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="30" fill="{GREEN if val>=0 else RED}"/><text class="small" x="{x+bw+8 if val>=0 else x-35:.1f}" y="{y+20}">{val:.2f}</text>'
    body += '<line x1="500" y1="80" x2="500" y2="420" stroke="#607080"/><text class="small" x="70" y="450">Correlation is descriptive, not causal; all project inputs are synthetic.</text>'
    return _write(output_path,body)


def create_sofr_sensitivity_chart(sensitivity: pd.DataFrame, output_path: Path) -> Path:
    """Annual interest expense sensitivity to SOFR shocks for a $10m balance."""
    base=sensitivity[sensitivity["floating_balance"]=="$10m"].copy()
    shocks=base["sofr_shock_bps"].tolist(); interest=(base["annual_interest"]/1000).tolist(); labels=[f"{x:+.0f}" for x in shocks]
    x0,y0,width,height=90,90,800,300
    body=f'<text class="title" x="50" y="45">SOFR Sensitivity — $10m Floating Balance</text>{_axes(labels,x0,y0,width,height)}'
    body += f'<polyline points="{_points(interest,x0,y0,width,height)}" fill="none" stroke="{RED}" stroke-width="4"/>'
    body += f'<text class="label" x="90" y="470">Annual interest expense ($000s) under SOFR shocks in basis points</text>'
    return _write(output_path,body)
