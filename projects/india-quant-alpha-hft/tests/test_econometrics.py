import numpy as np
import pandas as pd
from india_quant.econometrics import estimate_hedge_ratio, generate_positions

def test_hedge_ratio_recovers_relationship():
    rng = np.random.default_rng(3)
    x = np.linspace(4, 5, 300)
    y = 0.4 + 1.25 * x + rng.normal(0, 0.001, len(x))
    df = pd.DataFrame({"asset_a": np.exp(y), "asset_b": np.exp(x)})
    alpha, beta = estimate_hedge_ratio(df)
    assert abs(alpha - 0.4) < 0.01
    assert abs(beta - 1.25) < 0.01

def test_position_state_machine():
    z = pd.Series([0.0, -2.2, -1.0, -0.2, 2.3, 0.1])
    assert generate_positions(z, 2.0, 0.5).tolist() == [0.0, 1.0, 1.0, 0.0, -1.0, 0.0]
