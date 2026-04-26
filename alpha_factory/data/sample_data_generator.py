from pathlib import Path

import numpy as np
import pandas as pd

from alpha_factory.config import RANDOM_SEED


def generate_sample_data(
    output_path: Path,
    num_symbols: int = 50,
    num_days: int = 200,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=num_days)
    symbols = [f"STK{i:04d}" for i in range(1, num_symbols + 1)]

    rows = []
    market_shocks = rng.normal(loc=0.0002, scale=0.008, size=num_days)

    for symbol in symbols:
        start_price = rng.uniform(8.0, 80.0)
        drift = rng.normal(loc=0.0002, scale=0.0005)
        symbol_beta = rng.uniform(0.7, 1.3)
        idiosyncratic = rng.normal(loc=drift, scale=0.018, size=num_days)
        log_returns = symbol_beta * market_shocks + idiosyncratic
        close = start_price * np.exp(np.cumsum(log_returns))

        overnight = rng.normal(loc=0.0, scale=0.006, size=num_days)
        open_price = close / np.exp(log_returns) * np.exp(overnight)
        spread = rng.uniform(0.002, 0.025, size=num_days)
        high = np.maximum(open_price, close) * (1.0 + spread)
        low = np.minimum(open_price, close) * (1.0 - spread)

        base_volume = rng.uniform(500_000, 5_000_000)
        volume_noise = rng.lognormal(mean=0.0, sigma=0.35, size=num_days)
        volume_trend = np.exp(np.cumsum(rng.normal(0.0, 0.015, size=num_days)))
        volume = np.maximum(base_volume * volume_noise * volume_trend, 1_000).astype(int)
        amount = volume * close

        for i, date in enumerate(dates):
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "open": round(float(open_price[i]), 4),
                    "high": round(float(high[i]), 4),
                    "low": round(float(low[i]), 4),
                    "close": round(float(close[i]), 4),
                    "volume": int(volume[i]),
                    "amount": round(float(amount[i]), 2),
                }
            )

    data = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output_path, index=False)
    return data
