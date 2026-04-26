import logging

import pandas as pd

from alpha_factory.config import DATA_MODE, MIN_AMOUNT_THRESHOLD, OUTPUTS_DIR, USE_A_SHARE_FILTERS


LOGGER = logging.getLogger(__name__)


class UniverseFilter:
    """Universe construction for demo and cached A-share data."""

    def __init__(
        self,
        data_mode: str = DATA_MODE,
        use_a_share_filters: bool = USE_A_SHARE_FILTERS,
        min_amount_threshold: float = MIN_AMOUNT_THRESHOLD,
    ) -> None:
        self.data_mode = data_mode
        self.use_a_share_filters = use_a_share_filters
        self.min_amount_threshold = min_amount_threshold
        self.warnings: list[str] = []

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.empty:
            self._write_universe_monthly(pd.DataFrame())
            return data.copy()

        if self.data_mode != "akshare" or not self.use_a_share_filters:
            result = data.copy()
            self._write_demo_universe(result)
            return result

        result = data.copy()
        result["month"] = result["date"].dt.to_period("M").astype(str)
        result = self._apply_tradability_filter(result)
        result = self._apply_st_filter(result)
        result = self._apply_listing_age_filter(result)
        result, monthly_universe = self._apply_monthly_amount_filters(result)
        self._write_universe_monthly(monthly_universe)
        return result.drop(columns=["month"], errors="ignore").reset_index(drop=True)

    def get_warnings(self) -> list[str]:
        return list(self.warnings)

    def _apply_tradability_filter(self, data: pd.DataFrame) -> pd.DataFrame:
        before = len(data)
        mask = (
            data[["open", "high", "low", "close", "amount"]].notna().all(axis=1)
            & (data["amount"] > 0)
            & (data["volume"].fillna(0) > 0)
        )
        dropped = before - int(mask.sum())
        if dropped:
            self._warn(f"Suspension/non-tradable filter dropped {dropped} rows with missing prices or non-positive volume/amount.")
        return data.loc[mask].copy()

    def _apply_st_filter(self, data: pd.DataFrame) -> pd.DataFrame:
        if "is_st" in data.columns:
            mask = ~data["is_st"].fillna(False).astype(bool)
            dropped = len(data) - int(mask.sum())
            if dropped:
                self._warn(f"ST filter dropped {dropped} rows using cached is_st flag.")
            return data.loc[mask].copy()

        if "name" in data.columns:
            mask = ~data["name"].astype(str).str.upper().str.contains("ST", na=False)
            dropped = len(data) - int(mask.sum())
            if dropped:
                self._warn(f"ST filter dropped {dropped} rows using stock name text.")
            return data.loc[mask].copy()

        self._warn("ST filter unavailable: cached data has neither is_st nor name column; filter was skipped.")
        return data

    def _apply_listing_age_filter(self, data: pd.DataFrame, min_days: int = 120) -> pd.DataFrame:
        if data.empty:
            return data

        first_dates = data.groupby("symbol")["date"].transform("min")
        listed_days = (data["date"] - first_dates).dt.days
        mask = listed_days >= min_days
        dropped = len(data) - int(mask.sum())
        if dropped:
            self._warn(
                "Listing-age filter used first cached trading date as an approximation and "
                f"dropped {dropped} rows younger than {min_days} days."
            )
        else:
            self._warn("Listing-age filter used first cached trading date as an approximation; no rows were dropped.")
        return data.loc[mask].copy()

    def _apply_monthly_amount_filters(self, data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        if data.empty:
            return data, pd.DataFrame()

        monthly = (
            data.groupby(["month", "symbol"], as_index=False)
            .agg(avg_amount=("amount", "mean"), trading_days=("date", "nunique"))
            .sort_values(["month", "symbol"])
        )
        monthly["amount_quantile_20"] = monthly.groupby("month")["avg_amount"].transform(lambda values: values.quantile(0.2))
        monthly["passes_bottom_20_filter"] = monthly["avg_amount"] > monthly["amount_quantile_20"]
        monthly["passes_amount_threshold"] = monthly["avg_amount"] >= self.min_amount_threshold
        monthly["included"] = monthly["passes_bottom_20_filter"] & monthly["passes_amount_threshold"]

        dropped = int((~monthly["included"]).sum())
        if dropped:
            self._warn(
                f"Monthly amount filters excluded {dropped} symbol-month entries "
                f"(bottom 20% and min amount {self.min_amount_threshold})."
            )

        included = monthly.loc[monthly["included"], ["month", "symbol"]]
        filtered = data.merge(included, on=["month", "symbol"], how="inner")
        if filtered.empty:
            self._warn("Universe filters removed all rows; downstream reports will be empty.")
        return filtered, monthly

    def _write_demo_universe(self, data: pd.DataFrame) -> None:
        monthly = (
            data.assign(month=data["date"].dt.to_period("M").astype(str))
            .groupby(["month", "symbol"], as_index=False)
            .agg(avg_amount=("amount", "mean"), trading_days=("date", "nunique"))
        )
        monthly["included"] = True
        self._write_universe_monthly(monthly)

    def _write_universe_monthly(self, monthly: pd.DataFrame) -> None:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        monthly.to_csv(OUTPUTS_DIR / "universe_monthly.csv", index=False)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        LOGGER.warning(message)
