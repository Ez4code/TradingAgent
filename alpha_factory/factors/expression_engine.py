import ast
from typing import Any

import numpy as np
import pandas as pd

from alpha_factory.factors.operators import kdj_j_by_symbol


ALLOWED_COLUMNS = {"open", "high", "low", "close", "volume", "amount", "returns"}
ALLOWED_FUNCTIONS = {
    "abs",
    "correlation",
    "delay",
    "delta",
    "kdj_j",
    "log",
    "max",
    "mean",
    "min",
    "rank",
    "std",
    "zscore",
}


class ExpressionValidationError(ValueError):
    pass


def validate_expression(expression: str) -> None:
    _parse_expression(expression)


def compute_expression_factor(
    data: pd.DataFrame,
    expression: str,
    output_col: str = "factor",
) -> pd.DataFrame:
    tree = _parse_expression(expression)
    result = data.copy()
    result[output_col] = _evaluate_node(tree.body, result)
    return result


def _parse_expression(expression: str) -> ast.Expression:
    if not expression or len(expression) > 500:
        raise ExpressionValidationError("expression_empty_or_too_long")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionValidationError(f"syntax_error: {exc}") from exc

    _validate_node(tree.body)
    return tree


def _validate_node(node: ast.AST) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ExpressionValidationError("only_numeric_constants_are_allowed")
        return

    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_COLUMNS:
            raise ExpressionValidationError(f"unknown_name: {node.id}")
        return

    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            raise ExpressionValidationError("unsupported_unary_operator")
        _validate_node(node.operand)
        return

    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            raise ExpressionValidationError("unsupported_binary_operator")
        _validate_node(node.left)
        _validate_node(node.right)
        return

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExpressionValidationError("only_plain_function_calls_are_allowed")
        if node.func.id not in ALLOWED_FUNCTIONS:
            raise ExpressionValidationError(f"unknown_function: {node.func.id}")
        if node.keywords:
            raise ExpressionValidationError("keyword_arguments_are_not_allowed")
        for arg in node.args:
            _validate_node(arg)
        return

    raise ExpressionValidationError(f"unsupported_syntax: {type(node).__name__}")


def _evaluate_node(node: ast.AST, data: pd.DataFrame) -> Any:
    if isinstance(node, ast.Constant):
        return float(node.value)

    if isinstance(node, ast.Name):
        return pd.to_numeric(data[node.id], errors="coerce")

    if isinstance(node, ast.UnaryOp):
        value = _evaluate_node(node.operand, data)
        return value if isinstance(node.op, ast.UAdd) else -value

    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left, data)
        right = _evaluate_node(node.right, data)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return _safe_divide(left, right)

    if isinstance(node, ast.Call):
        return _evaluate_call(node, data)

    raise ExpressionValidationError(f"unsupported_syntax: {type(node).__name__}")


def _evaluate_call(node: ast.Call, data: pd.DataFrame) -> Any:
    name = node.func.id

    if name == "kdj_j":
        if len(node.args) == 1:
            return kdj_j_by_symbol(data, _int_arg(_evaluate_node(node.args[0], data)))
        if len(node.args) == 4:
            return kdj_j_by_symbol(data, _int_arg(_evaluate_node(node.args[3], data)))
        raise ExpressionValidationError("kdj_j_requires_1_or_4_arguments")

    args = [_evaluate_node(arg, data) for arg in node.args]

    if name in {"delay", "delta", "mean", "std", "max", "min"}:
        if len(args) != 2:
            raise ExpressionValidationError(f"{name}_requires_2_arguments")
        series = _as_series(args[0], data)
        window = _int_arg(args[1])
        if name == "delay":
            return series.groupby(data["symbol"], sort=False).shift(window)
        if name == "delta":
            return series - series.groupby(data["symbol"], sort=False).shift(window)
        return _rolling_by_symbol(series, data, window, name)

    if name == "correlation":
        if len(args) != 3:
            raise ExpressionValidationError("correlation_requires_3_arguments")
        return _rolling_corr_by_symbol(
            _as_series(args[0], data),
            _as_series(args[1], data),
            data,
            _int_arg(args[2]),
        )

    if name == "rank":
        if len(args) != 1:
            raise ExpressionValidationError("rank_requires_1_argument")
        return _as_series(args[0], data).groupby(data["date"], sort=False).rank(pct=True)

    if name == "zscore":
        if len(args) != 1:
            raise ExpressionValidationError("zscore_requires_1_argument")
        series = _as_series(args[0], data)
        mean = series.groupby(data["date"], sort=False).transform("mean")
        std = series.groupby(data["date"], sort=False).transform("std")
        return (series - mean) / std.where(std != 0.0)

    if name == "abs":
        if len(args) != 1:
            raise ExpressionValidationError("abs_requires_1_argument")
        return _as_series(args[0], data).abs()

    if name == "log":
        if len(args) != 1:
            raise ExpressionValidationError("log_requires_1_argument")
        series = _as_series(args[0], data)
        return np.log(series.where(series > 0.0))

    raise ExpressionValidationError(f"unknown_function: {name}")


def _rolling_by_symbol(series: pd.Series, data: pd.DataFrame, window: int, method: str) -> pd.Series:
    def _apply(values: pd.Series) -> pd.Series:
        rolling = values.rolling(window=window, min_periods=window)
        if method == "mean":
            return rolling.mean()
        if method == "std":
            return rolling.std()
        if method == "max":
            return rolling.max()
        if method == "min":
            return rolling.min()
        raise ExpressionValidationError(f"unsupported_rolling_method: {method}")

    return series.groupby(data["symbol"], sort=False).transform(_apply)


def _rolling_corr_by_symbol(
    left: pd.Series,
    right: pd.Series,
    data: pd.DataFrame,
    window: int,
) -> pd.Series:
    frame = pd.DataFrame(
        {
            "symbol": data["symbol"].to_numpy(),
            "left": left.to_numpy(),
            "right": right.to_numpy(),
        },
        index=data.index,
    )

    def _corr(group: pd.DataFrame) -> pd.Series:
        return group["left"].rolling(window=window, min_periods=window).corr(group["right"])

    return frame.groupby("symbol", sort=False, group_keys=False).apply(_corr).reindex(data.index)


def _safe_divide(left: Any, right: Any) -> Any:
    if isinstance(right, pd.Series):
        return left / right.where(right != 0.0)
    if right == 0.0:
        return np.nan
    return left / right


def _as_series(value: Any, data: pd.DataFrame) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series(float(value), index=data.index)


def _int_arg(value: Any) -> int:
    if isinstance(value, pd.Series):
        raise ExpressionValidationError("window_must_be_a_number")
    integer = int(value)
    if integer <= 0 or integer > 252:
        raise ExpressionValidationError("window_out_of_range")
    return integer
