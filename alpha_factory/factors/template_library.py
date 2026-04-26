from dataclasses import dataclass


@dataclass(frozen=True)
class FactorTemplate:
    name: str
    expression: str
    allowed_windows: list[int]
    category: str


def get_template_library() -> dict[str, FactorTemplate]:
    templates = [
        FactorTemplate("momentum", "close / delay(close, N) - 1", [5, 10, 20, 40, 60], "price"),
        FactorTemplate("reversal", "-1 * (close / delay(close, N) - 1)", [5, 10, 20, 40, 60], "price"),
        FactorTemplate("volatility", "std(returns, N)", [5, 10, 20, 40, 60], "risk"),
        FactorTemplate("inverse_volatility", "-1 * std(returns, N)", [5, 10, 20, 40, 60], "risk"),
        FactorTemplate("price_volume_corr", "correlation(close, volume, N)", [5, 10, 20, 40, 60], "volume_price"),
        FactorTemplate(
            "amount_momentum",
            "mean(amount, N) / delay(mean(amount, N), N) - 1",
            [5, 10, 20, 40, 60],
            "liquidity",
        ),
        FactorTemplate("liquidity", "mean(amount, N)", [5, 10, 20, 40, 60], "liquidity"),
        FactorTemplate("breakout", "close / max(close, N) - 1", [5, 10, 20, 40, 60], "price"),
        FactorTemplate("distance_to_ma", "close / mean(close, N) - 1", [5, 10, 20, 40, 60], "price"),
        FactorTemplate("turnover_proxy", "volume / mean(volume, N)", [5, 10, 20, 40, 60], "volume"),
        FactorTemplate(
            "kdj_j_oversold",
            "-1 * kdj_j(close, high, low, N)",
            [5, 10, 20],
            "technical_reversal",
        ),
        FactorTemplate(
            "kdj_j_rebound",
            "(20 - kdj_j(close, high, low, N)) / 100 + delta(kdj_j(close, high, low, N), 1) / 100",
            [5, 10, 20],
            "technical_reversal",
        ),
    ]
    return {template.name: template for template in templates}


def get_default_templates() -> list[FactorTemplate]:
    return [
        get_template_library()["momentum"],
        get_template_library()["reversal"],
        get_template_library()["volatility"],
    ]
