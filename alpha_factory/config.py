import os
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = BASE_DIR / "examples"
OUTPUTS_DIR = BASE_DIR / "outputs"
SAMPLE_DATA_PATH = EXAMPLES_DIR / "sample_data.csv"
RAW_DATA_DIR = BASE_DIR / os.getenv("RAW_DATA_DIR", "data/raw_stock_data")
ASTOCK_LIST_CSV = os.getenv("ASTOCK_LIST_CSV", "/Users/liuxin/Project/AstockSelector/data/Astock_list.csv")

DEFAULT_FACTOR_WINDOW = 20
DEFAULT_NUM_SYMBOLS = 50
DEFAULT_NUM_DAYS = 200
RANDOM_SEED = 42
ALLOWED_WINDOWS = [5, 10, 20, 40, 60]
DEFAULT_REQUEST = "生成一组动量、反转、波动率基础因子"
BACKTEST_TOP_K_LIST = [50, 100, 200]
ROUND_TRIP_COST = 0.0025
TRADING_DAYS_PER_YEAR = 252
STOCK_MATCH_MIN_OBS = int(os.getenv("STOCK_MATCH_MIN_OBS", "30"))
STOCK_MATCH_TOP_N = int(os.getenv("STOCK_MATCH_TOP_N", "0"))

DATA_MODE = os.getenv("DATA_MODE", "demo").strip().lower()
START_DATE = os.getenv("START_DATE", "20240101")
END_DATE = os.getenv("END_DATE", date.today().strftime("%Y%m%d"))
ADJUST = os.getenv("ADJUST", "qfq")
REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.2"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
MIN_AMOUNT_THRESHOLD = float(os.getenv("MIN_AMOUNT_THRESHOLD", "0"))
USE_A_SHARE_FILTERS = os.getenv("USE_A_SHARE_FILTERS", "1").strip().lower() in {"1", "true", "yes", "on"}
AKSHARE_SYMBOL_LIMIT = int(os.getenv("AKSHARE_SYMBOL_LIMIT", "0"))
AKSHARE_WORKERS = int(os.getenv("AKSHARE_WORKERS", "1"))
AKSHARE_FORCE_DOWNLOAD = os.getenv("AKSHARE_FORCE_DOWNLOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
AKSHARE_SYMBOLS = os.getenv("AKSHARE_SYMBOLS", "").strip()
