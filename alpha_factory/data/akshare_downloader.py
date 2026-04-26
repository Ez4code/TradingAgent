import argparse
import concurrent.futures
import logging
import multiprocessing
import time
from pathlib import Path
from typing import Any

import pandas as pd

from alpha_factory.config import ASTOCK_LIST_CSV, OUTPUTS_DIR


LOGGER = logging.getLogger(__name__)

HIST_FIELD_MAP = {
    "日期": "date",
    "date": "date",
    "开盘": "open",
    "open": "open",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "收盘": "close",
    "close": "close",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "amount",
    "amount": "amount",
}


def ensure_akshare_cache(
    raw_data_dir: Path,
    start_date: str,
    end_date: str,
    adjust: str,
    request_sleep_seconds: float,
    max_retries: int,
    symbol_limit: int = 0,
    workers: int = 1,
    force_download: bool = False,
    symbols_text: str = "",
) -> list[dict[str, str]]:
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    failures: list[dict[str, str]] = []

    if symbols_text:
        stock_list = _stock_list_from_symbols(symbols_text)
    else:
        try:
            stock_list = get_stock_list()
        except Exception as exc:  # noqa: BLE001 - downloader must not crash the research run.
            failures.append({"symbol": "STOCK_LIST", "name": "", "error": str(exc)})
            write_failed_symbols(failures)
            LOGGER.warning("Unable to fetch AKShare stock list: %s", exc)
            return failures

    if symbol_limit > 0:
        stock_list = stock_list.head(symbol_limit)

    failures = download_astock_raw_data(
        stock_list=stock_list,
        output_dir=raw_data_dir,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
        delay_seconds=request_sleep_seconds,
        max_retries=max_retries,
        workers=workers,
        force_download=force_download,
    )

    write_failed_symbols(failures)
    return failures


def download_astock_raw_data(
    stock_list: pd.DataFrame,
    output_dir: Path | str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
    delay_seconds: float = 1.0,
    max_retries: int = 3,
    workers: int = 1,
    force_download: bool = False,
) -> list[dict[str, str]]:
    """Download A-share daily data to one CSV per symbol.

    This intentionally mirrors the user's reference downloader: one function
    handles a single symbol, and this wrapper optionally runs many symbols in
    parallel. Each failed symbol is returned instead of raising globally.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    records = stock_list.to_dict("records")

    if workers <= 1:
        failures = []
        for row in records:
            failure = download_symbol_to_cache(
                row=row,
                output_dir=output_path,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
                delay_seconds=delay_seconds,
                max_retries=max_retries,
                force_download=force_download,
            )
            if failure:
                failures.append(failure)
        return failures

    failures = []
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
    ) as executor:
        futures = [
            executor.submit(
                download_symbol_to_cache,
                row,
                output_path,
                start_date,
                end_date,
                adjust,
                delay_seconds,
                max_retries,
                force_download,
            )
            for row in records
        ]

        for future in concurrent.futures.as_completed(futures):
            try:
                failure = future.result()
                if failure:
                    failures.append(failure)
            except Exception as exc:  # noqa: BLE001 - keep batch downloader resilient.
                failures.append({"symbol": "UNKNOWN", "name": "", "error": str(exc)})

    return failures


def download_symbol_to_cache(
    row: dict[str, Any],
    output_dir: Path | str,
    start_date: str,
    end_date: str,
    adjust: str,
    delay_seconds: float,
    max_retries: int,
    force_download: bool = False,
) -> dict[str, str] | None:
    symbol = str(row["symbol"])
    name = str(row.get("name", ""))
    output_path = Path(output_dir)
    cache_path = output_path / f"{symbol}.csv"

    if not force_download and not _cache_needs_update(cache_path, end_date):
        return None

    incremental_start = start_date if force_download else _incremental_start_date(cache_path, start_date)
    try:
        print(f"Downloading data for {symbol}... ({incremental_start} to {end_date})", flush=True)
        downloaded = download_stock_daily(
            symbol=symbol,
            start_date=incremental_start,
            end_date=end_date,
            adjust=adjust,
            max_retries=max_retries,
            request_sleep_seconds=delay_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - one failed symbol must not stop the batch.
        LOGGER.warning("AKShare download failed for %s: %s", symbol, exc)
        return {"symbol": symbol, "name": name, "error": str(exc)}

    if downloaded.empty:
        LOGGER.warning("AKShare returned empty data for %s", symbol)
        return {"symbol": symbol, "name": name, "error": "empty_data"}

    downloaded["name"] = name
    downloaded["is_st"] = bool(row.get("is_st", False))
    _merge_and_write_cache(cache_path, downloaded, replace_existing=force_download)
    print(f"Saved data for {symbol} rows={len(downloaded)}", flush=True)
    return None


def get_stock_list() -> pd.DataFrame:
    local_list = _load_local_stock_list(ASTOCK_LIST_CSV)
    if local_list is not None:
        return local_list

    ak = _import_akshare()
    try:
        sh_df = ak.stock_info_sh_name_code(symbol="主板A股")
        sz_df = ak.stock_info_sz_name_code(symbol="A股列表")
        sh_df = sh_df.rename(columns={"证券代码": "code", "证券简称": "name"})
        sz_df = sz_df.rename(columns={"A股代码": "code", "A股简称": "name"})
        sh_df["market"] = "sh"
        sz_df["market"] = "sz"
        stock_list = pd.concat([sh_df, sz_df], ignore_index=True, sort=False)
        stock_list["code"] = stock_list["code"].astype(str).str.zfill(6)
        stock_list["symbol"] = stock_list["market"] + stock_list["code"]
        stock_list = stock_list[["symbol", "code", "name", "market"]]
    except Exception:
        spot = ak.stock_zh_a_spot_em()
        if "代码" not in spot.columns:
            raise ValueError(f"stock_zh_a_spot_em missing 代码 column; got {list(spot.columns)}")

        name_col = "名称" if "名称" in spot.columns else None
        stock_list = pd.DataFrame(
            {
                "code": spot["代码"].astype(str).str.zfill(6),
                "name": spot[name_col].astype(str) if name_col else "",
            }
        )
        stock_list["market"] = stock_list["code"].map(_infer_market)
        stock_list["symbol"] = stock_list["market"] + stock_list["code"]

    stock_list["is_st"] = stock_list["name"].str.upper().str.contains("ST", na=False)
    stock_list = stock_list.drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)
    return stock_list


def download_stock_daily(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str,
    max_retries: int,
    request_sleep_seconds: float,
) -> pd.DataFrame:
    ak = _import_akshare()
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            if request_sleep_seconds > 0:
                time.sleep(request_sleep_seconds)
            daily_symbol = _to_daily_symbol(symbol)
            raw = ak.stock_zh_a_daily(
                symbol=daily_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            return normalize_akshare_daily(raw, daily_symbol)
        except Exception as daily_exc:  # noqa: BLE001 - retry external data calls.
            last_error = daily_exc
            try:
                hist_symbol = _to_plain_code(symbol)
                raw = ak.stock_zh_a_hist(
                    symbol=hist_symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                )
                return normalize_akshare_daily(raw, _to_daily_symbol(symbol))
            except Exception as hist_exc:  # noqa: BLE001 - retry external data calls.
                last_error = hist_exc
                LOGGER.warning(
                    "AKShare retry %s/%s failed for %s: daily=%s; hist=%s",
                    attempt,
                    max_retries,
                    symbol,
                    daily_exc,
                    hist_exc,
                )
                if attempt < max_retries:
                    time.sleep(max(request_sleep_seconds, 0.1) * attempt)

    raise RuntimeError(f"download failed after {max_retries} retries: {last_error}")


def download_stock_daily_hist_only(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str,
    max_retries: int,
    request_sleep_seconds: float,
) -> pd.DataFrame:
    ak = _import_akshare()
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            if request_sleep_seconds > 0:
                time.sleep(request_sleep_seconds)
            raw = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            return normalize_akshare_daily(raw, symbol)
        except Exception as exc:  # noqa: BLE001 - retry external data calls.
            last_error = exc
            LOGGER.warning("AKShare retry %s/%s failed for %s: %s", attempt, max_retries, symbol, exc)
            if attempt < max_retries:
                time.sleep(max(request_sleep_seconds, 0.1) * attempt)

    raise RuntimeError(f"download failed after {max_retries} retries: {last_error}")


def normalize_akshare_daily(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume", "amount"])

    data = raw.rename(columns={col: HIST_FIELD_MAP.get(col, col) for col in raw.columns}).copy()
    required = ["date", "open", "high", "low", "close", "volume", "amount"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"AKShare daily data missing required fields {missing}; got {list(raw.columns)}")

    data = data[required].copy()
    data["date"] = pd.to_datetime(data["date"])
    data["symbol"] = str(symbol).zfill(6)
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["date", "open", "high", "low", "close"])
    data = data.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    return data[["date", "symbol", "open", "high", "low", "close", "volume", "amount"]]


def write_failed_symbols(failures: list[dict[str, Any]]) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["symbol", "name", "error"]
    pd.DataFrame(failures, columns=columns).to_csv(OUTPUTS_DIR / "failed_symbols.csv", index=False)


def _import_akshare() -> Any:
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise RuntimeError("AKShare is not installed. Install with `pip install akshare`.") from exc
    return ak


def _load_local_stock_list(path: str) -> pd.DataFrame | None:
    if not path or not Path(path).exists():
        return None
    stock_list = pd.read_csv(path)
    if "symbol" not in stock_list.columns:
        return None

    if "code" not in stock_list.columns:
        stock_list["code"] = stock_list["symbol"].astype(str).str.extract(r"(\d{6})")[0]
    if "market" not in stock_list.columns:
        stock_list["market"] = stock_list["symbol"].astype(str).str.extract(r"^(sh|sz)")[0]
        stock_list["market"] = stock_list["market"].fillna(stock_list["code"].map(_infer_market))
    if "name" not in stock_list.columns:
        stock_list["name"] = ""

    stock_list["code"] = stock_list["code"].astype(str).str.zfill(6)
    stock_list["market"] = stock_list["market"].astype(str).str.lower()
    stock_list["symbol"] = stock_list["symbol"].astype(str)
    missing_prefix = ~stock_list["symbol"].str.match(r"^(sh|sz)\d{6}$", na=False)
    stock_list.loc[missing_prefix, "symbol"] = stock_list.loc[missing_prefix, "market"] + stock_list.loc[missing_prefix, "code"]
    stock_list["is_st"] = stock_list["name"].astype(str).str.upper().str.contains("ST", na=False)
    return stock_list[["symbol", "code", "name", "market", "is_st"]].drop_duplicates("symbol").reset_index(drop=True)


def _to_daily_symbol(symbol: str) -> str:
    value = str(symbol)
    if value.startswith(("sh", "sz")):
        return value
    code = _to_plain_code(value)
    return _infer_market(code) + code


def _to_plain_code(symbol: str) -> str:
    return str(symbol).replace("sh", "").replace("sz", "").zfill(6)


def _infer_market(code: str) -> str:
    plain = str(code).zfill(6)
    if plain.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def _cache_needs_update(cache_path: Path, end_date: str) -> bool:
    if not cache_path.exists():
        return True
    try:
        cached = pd.read_csv(cache_path, usecols=["date"])
    except Exception:
        return True
    if cached.empty:
        return True
    latest = pd.to_datetime(cached["date"], errors="coerce").max()
    requested_end = _effective_cache_end_date(end_date)
    return pd.isna(latest) or latest.normalize() < requested_end.normalize()


def _incremental_start_date(cache_path: Path, start_date: str) -> str:
    if not cache_path.exists():
        return start_date
    try:
        cached = pd.read_csv(cache_path, usecols=["date"])
    except Exception:
        return start_date
    if cached.empty:
        return start_date
    latest = pd.to_datetime(cached["date"], errors="coerce").max()
    if pd.isna(latest):
        return start_date
    return (latest + pd.Timedelta(days=1)).strftime("%Y%m%d")


def _merge_and_write_cache(cache_path: Path, downloaded: pd.DataFrame, replace_existing: bool = False) -> None:
    if cache_path.exists() and not replace_existing:
        existing = pd.read_csv(cache_path)
        combined = pd.concat([existing, downloaded], ignore_index=True)
    else:
        combined = downloaded

    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values("date").drop_duplicates("date", keep="last")
    combined.to_csv(cache_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download A-share daily K-line data with AKShare.")
    parser.add_argument("--list-csv", default=ASTOCK_LIST_CSV, help="Stock list CSV with symbol/code/name/market columns.")
    parser.add_argument("--output-list-csv", default=ASTOCK_LIST_CSV, help="Where to save generated stock list CSV.")
    parser.add_argument("--generate-list", action="store_true", help="Fetch stock list from AKShare and save it.")
    parser.add_argument("--download-dir", default=str(Path("alpha_factory/data/raw_stock_data")), help="Cache output directory.")
    parser.add_argument("--start-date", default="20240101", help="Start date, YYYYMMDD.")
    parser.add_argument("--end-date", default="20500101", help="End date, YYYYMMDD.")
    parser.add_argument("--adjust", default="qfq", help="Adjustment mode passed to AKShare, e.g. qfq or empty string.")
    parser.add_argument("--delay", default=1.0, type=float, help="Seconds to wait between requests per worker.")
    parser.add_argument("--max-retries", default=3, type=int, help="Retry count per symbol.")
    parser.add_argument("--workers", default=1, type=int, help="Number of concurrent processes.")
    parser.add_argument("--limit", default=0, type=int, help="Limit number of symbols, 0 means no limit.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols, e.g. sh600519,sz000001.")
    parser.add_argument("--force", action="store_true", help="Redownload even if cache already reaches end date.")
    args = parser.parse_args()

    if args.symbols:
        stock_list = _stock_list_from_symbols(args.symbols)
    elif args.generate_list:
        stock_list = _fetch_and_save_stock_list(args.output_list_csv)
    else:
        stock_list = _load_local_stock_list(args.list_csv)
        if stock_list is None:
            raise FileNotFoundError(
                f"Stock list CSV not found or invalid: {args.list_csv}. "
                "Run with --generate-list or pass --list-csv."
            )

    if args.limit > 0:
        stock_list = stock_list.head(args.limit)
        print(f"Limiting download to first {args.limit} stocks", flush=True)

    failures = download_astock_raw_data(
        stock_list=stock_list,
        output_dir=Path(args.download_dir),
        start_date=args.start_date,
        end_date=args.end_date,
        adjust=args.adjust,
        delay_seconds=args.delay,
        max_retries=args.max_retries,
        workers=args.workers,
        force_download=args.force,
    )
    write_failed_symbols(failures)
    print(f"Download finished. failures={len(failures)}", flush=True)


def _fetch_and_save_stock_list(output_csv: str) -> pd.DataFrame:
    local_backup = _load_local_stock_list("")
    if local_backup is not None:
        return local_backup

    previous = globals().get("ASTOCK_LIST_CSV")
    try:
        globals()["ASTOCK_LIST_CSV"] = ""
        stock_list = get_stock_list()
    finally:
        globals()["ASTOCK_LIST_CSV"] = previous

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stock_list.to_csv(output_path, index=False)
    print(f"Saved A-stock list to {output_path} rows={len(stock_list)}", flush=True)
    return stock_list


def _stock_list_from_symbols(symbols_text: str) -> pd.DataFrame:
    symbols = [item.strip() for item in symbols_text.split(",") if item.strip()]
    rows = []
    for symbol in symbols:
        daily_symbol = _to_daily_symbol(symbol)
        code = _to_plain_code(daily_symbol)
        rows.append(
            {
                "symbol": daily_symbol,
                "code": code,
                "name": "",
                "market": daily_symbol[:2],
                "is_st": False,
            }
        )
    return pd.DataFrame(rows).drop_duplicates("symbol").reset_index(drop=True)


def _effective_cache_end_date(end_date: str) -> pd.Timestamp:
    requested_end = pd.to_datetime(end_date)
    while requested_end.weekday() >= 5:
        requested_end -= pd.Timedelta(days=1)
    return requested_end


if __name__ == "__main__":
    main()
