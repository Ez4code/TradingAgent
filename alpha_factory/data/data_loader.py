from pathlib import Path

import pandas as pd

from alpha_factory.config import (
    ADJUST,
    AKSHARE_SYMBOL_LIMIT,
    AKSHARE_FORCE_DOWNLOAD,
    AKSHARE_SYMBOLS,
    AKSHARE_WORKERS,
    DATA_MODE,
    END_DATE,
    MAX_RETRIES,
    RAW_DATA_DIR,
    REQUEST_SLEEP_SECONDS,
    START_DATE,
)
from alpha_factory.data.akshare_downloader import ensure_akshare_cache


REQUIRED_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume", "amount"]


def load_data(data_mode: str = DATA_MODE) -> pd.DataFrame:
    if data_mode == "demo":
        from alpha_factory.config import SAMPLE_DATA_PATH

        return load_sample_data(SAMPLE_DATA_PATH)
    if data_mode == "akshare":
        return load_akshare_data()
    raise ValueError(f"Unsupported DATA_MODE: {data_mode}. Expected 'demo' or 'akshare'.")


def load_sample_data(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    return _prepare_market_data(data)


def load_akshare_data(
    raw_data_dir: Path = RAW_DATA_DIR,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> pd.DataFrame:
    failures = ensure_akshare_cache(
        raw_data_dir=raw_data_dir,
        start_date=start_date,
        end_date=end_date,
        adjust=ADJUST,
        request_sleep_seconds=REQUEST_SLEEP_SECONDS,
        max_retries=MAX_RETRIES,
        symbol_limit=AKSHARE_SYMBOL_LIMIT,
        workers=AKSHARE_WORKERS,
        force_download=AKSHARE_FORCE_DOWNLOAD,
        symbols_text=AKSHARE_SYMBOLS,
    )
    frames = []
    for path in sorted(raw_data_dir.glob("*.csv")):
        try:
            frames.append(pd.read_csv(path))
        except Exception:
            continue

    if not frames:
        prepared = _prepare_market_data(pd.DataFrame(columns=REQUIRED_COLUMNS))
        prepared.attrs["data_warnings"] = _failure_warnings(failures)
        return prepared

    data = pd.concat(frames, ignore_index=True)
    data["date"] = pd.to_datetime(data["date"])
    mask = (data["date"] >= pd.to_datetime(start_date)) & (data["date"] <= pd.to_datetime(end_date))
    data = data.loc[mask].copy()
    prepared = _prepare_market_data(data)
    prepared.attrs["data_warnings"] = _failure_warnings(failures)
    return prepared


def _prepare_market_data(data: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_COLUMNS if col not in data.columns]
    if missing:
        raise ValueError(f"sample data is missing required columns: {missing}")

    data["date"] = pd.to_datetime(data["date"])
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)

    by_symbol = data.groupby("symbol", sort=False)
    data["returns"] = data["close"] / by_symbol["close"].shift(1) - 1.0
    data["future_return"] = by_symbol["open"].shift(-2) / by_symbol["open"].shift(-1) - 1.0

    return data


def _failure_warnings(failures: list[dict[str, str]]) -> list[str]:
    if not failures:
        return []
    examples = "; ".join(f"{item.get('symbol', '')}: {item.get('error', '')}" for item in failures[:5])
    return [f"AKShare download/cache update had {len(failures)} failures. Examples: {examples}"]
