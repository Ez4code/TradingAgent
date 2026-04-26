# Alpha Factory MVP

Phase 1 implements a minimal factor research loop using synthetic demo data.

Run demo mode from the project root:

```bash
python main.py
```

The command will generate `alpha_factory/examples/sample_data.csv` when missing, compute three fixed-template factors, evaluate cross-sectional RankIC, and write reports to `alpha_factory/outputs/`.

Phase 2 adds natural-language factor planning:

```bash
python main.py --request "我想测试短期放量后的反转因子"
python main.py --request "测试价量背离因子"
```

If `DEEPSEEK_API_KEY` is available, the planner asks DeepSeek for strict JSON. If the key is missing or the API is unavailable, it falls back to local rule parsing. LLM output is never executed as code; only registered templates and legal windows are run.

Phase 3 adds a minimal long-only TopK backtest for each generated factor. The backtest uses the same strict timeline as the evaluator:

- factor and signal are formed with data available at T close
- simulated execution is at T+1 open
- one-period return is `open_{T+2} / open_{T+1} - 1`

Outputs include `alpha_factory/outputs/equity_curve.csv` and `alpha_factory/outputs/backtest_report.json`. Real A-share limit-up/down and suspension filters are intentionally not implemented in demo mode; future real-data phases should add those filters only when reliable fields are available.

Phase 4 adds AKShare cache mode while keeping demo mode as the default.

Install AKShare when using real A-share data:

```bash
pip install akshare
```

Run AKShare mode:

```bash
DATA_MODE=akshare START_DATE=20240101 END_DATE=20241231 python main.py
```

Optional environment variables:

```bash
ADJUST=qfq
REQUEST_SLEEP_SECONDS=0.2
MAX_RETRIES=3
MIN_AMOUNT_THRESHOLD=0
USE_A_SHARE_FILTERS=1
AKSHARE_SYMBOL_LIMIT=100
```

AKShare data is cached under `alpha_factory/data/raw_stock_data/{symbol}.csv`. Failed downloads are recorded in `alpha_factory/outputs/failed_symbols.csv`; failures for individual symbols do not stop the full run.

A-share constraints in this phase:

- Exact from cached OHLCV: missing price, missing amount, zero volume, low amount threshold.
- Implemented from available metadata when present: ST filtering via `is_st` or stock name text.
- Approximate: listed less than 120 days uses first cached trading date.
- Approximate in backtest: limit-up, limit-down, and one-price-board tradability use OHLC heuristics because exact limit-price fields are not cached yet.
- Not claimed as complete: real exchange-specific limit prices, special treatment boards, and all corporate-action edge cases.

Warnings and constraint notes are written to `alpha_factory/outputs/final_summary.md`.
