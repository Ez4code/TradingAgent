import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any

from alpha_factory.config import ALLOWED_WINDOWS
from alpha_factory.factors.factor_request import NaturalLanguageFactorRequest
from alpha_factory.factors.template_library import get_template_library


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_REASONING_EFFORT = "high"


def plan_from_request(request: NaturalLanguageFactorRequest) -> dict[str, Any]:
    api_key, key_source = _get_deepseek_api_key()
    if not api_key:
        return _rule_based_plan(request.raw_text, "missing_api_key")

    try:
        raw_plan = _call_deepseek(request.raw_text, api_key)
        return _sanitize_plan(
            raw_plan,
            fallback_reason=f"llm_plan_sanitized; api_key_source={key_source}",
        )
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return _rule_based_plan(request.raw_text, f"llm_failed: {exc}")


def _get_deepseek_api_key() -> tuple[str | None, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        return api_key, "environment"

    try:
        completed = subprocess.run(
            [
                "zsh",
                "-lc",
                'source ~/.zshrc >/dev/null 2>&1; printf "%s" "$DEEPSEEK_API_KEY"',
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None, "missing"

    api_key = completed.stdout.strip()
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key
        return api_key, "zshrc"

    return None, "missing"


def _call_deepseek(raw_text: str, api_key: str) -> dict[str, Any]:
    template_names = list(get_template_library().keys())
    prompt = {
        "role": "user",
        "content": (
            "你是 A 股因子研究规划器。只能输出 JSON，不要输出 Markdown。\n"
            f"合法模板: {template_names}\n"
            f"合法窗口: {ALLOWED_WINDOWS}\n"
            "优先组合已有模板。只有现有模板组合无法表达时，才提议新模板。\n"
            "禁止输出 Python 代码。输出格式必须为：\n"
            "{"
            '"intent": "...", '
            '"selected_templates": [{"template_name": "...", "windows": [5], "reason": "..."}], '
            '"need_new_template": false, '
            '"new_template": null'
            "}\n"
            f"用户需求: {raw_text}"
        ),
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "reasoning_effort": DEEPSEEK_REASONING_EFFORT,
        "thinking": {"type": "enabled"},
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON only. Do not include explanations outside JSON.",
            },
            prompt,
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        body = json.loads(response.read().decode("utf-8"))

    content = body["choices"][0]["message"]["content"]
    return json.loads(_extract_json_object(content))


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("LLM response did not contain a JSON object")
    return match.group(0)


def _sanitize_plan(plan: dict[str, Any], fallback_reason: str) -> dict[str, Any]:
    templates = get_template_library()
    selected = []
    rejected = []

    for item in plan.get("selected_templates", []):
        name = item.get("template_name")
        if name not in templates:
            rejected.append({"template_name": name, "reason": "unknown_template"})
            continue

        legal_windows = [
            int(window)
            for window in item.get("windows", [])
            if isinstance(window, int) and window in templates[name].allowed_windows
        ]
        if not legal_windows:
            rejected.append({"template_name": name, "reason": "no_legal_window"})
            continue

        selected.append(
            {
                "template_name": name,
                "windows": sorted(set(legal_windows)),
                "reason": str(item.get("reason", fallback_reason)),
            }
        )

    if not selected:
        selected = _default_selected_templates()

    new_template = plan.get("new_template") if plan.get("need_new_template") else None
    sanitized_new_template = _sanitize_new_template(new_template) if new_template else None

    return {
        "intent": str(plan.get("intent", "general_factor_research")),
        "selected_templates": selected,
        "need_new_template": bool(sanitized_new_template),
        "new_template": sanitized_new_template,
        "planner_mode": "llm",
        "llm_model": DEEPSEEK_MODEL,
        "reasoning_effort": DEEPSEEK_REASONING_EFFORT,
        "planner_notes": fallback_reason,
        "rejected_plan_items": rejected,
    }


def _rule_based_plan(raw_text: str, reason: str) -> dict[str, Any]:
    text = raw_text.lower()
    selected: list[dict[str, Any]]
    intent = "basic_factor_research"
    new_template = None

    if any(token in text for token in ["放量", "volume spike", "turnover"]) and any(
        token in text for token in ["反转", "reversal"]
    ):
        intent = "volume_price_reversal"
        selected = [
            {"template_name": "reversal", "windows": [5, 10], "reason": "用户想测试短期反转"},
            {"template_name": "turnover_proxy", "windows": [5, 10], "reason": "用于刻画放量"},
        ]
    elif any(token in text for token in ["低波动", "low volatility", "低波"]) and any(
        token in text for token in ["流动性", "liquidity"]
    ):
        intent = "low_volatility_high_liquidity"
        selected = [
            {"template_name": "inverse_volatility", "windows": [10, 20], "reason": "刻画低波动偏好"},
            {"template_name": "liquidity", "windows": [10, 20], "reason": "刻画高流动性"},
        ]
    elif any(token in text for token in ["价量背离", "背离", "divergence"]):
        intent = "volume_price_divergence"
        selected = [
            {"template_name": "price_volume_corr", "windows": [10, 20], "reason": "刻画价量相关关系"},
            {"template_name": "turnover_proxy", "windows": [10, 20], "reason": "辅助观察成交量变化"},
            {"template_name": "distance_to_ma", "windows": [10, 20], "reason": "辅助观察价格偏离"},
        ]
        new_template = _volume_price_divergence_template()
    elif any(token in text for token in ["动量", "momentum"]):
        intent = "momentum_research"
        selected = [
            {"template_name": "momentum", "windows": [20], "reason": "用户提到动量"},
            {"template_name": "reversal", "windows": [20], "reason": "与动量方向对照"},
            {"template_name": "volatility", "windows": [20], "reason": "基础风险刻画"},
        ]
    else:
        selected = _default_selected_templates()

    return {
        "intent": intent,
        "selected_templates": selected,
        "need_new_template": new_template is not None,
        "new_template": new_template,
        "planner_mode": "rule_based",
        "llm_model": None,
        "reasoning_effort": None,
        "planner_notes": reason,
        "rejected_plan_items": [],
    }


def _default_selected_templates() -> list[dict[str, Any]]:
    return [
        {"template_name": "momentum", "windows": [20], "reason": "基础动量因子"},
        {"template_name": "reversal", "windows": [20], "reason": "基础反转因子"},
        {"template_name": "volatility", "windows": [20], "reason": "基础波动率因子"},
    ]


def _volume_price_divergence_template() -> dict[str, Any]:
    return {
        "template_name": "volume_price_divergence",
        "expression": "rank(delta(volume, N)) - rank(delta(close, N))",
        "allowed_windows": [5, 10, 20],
        "category": "volume_price",
        "reason": "刻画量价背离，无法由当前单一模板直接表达",
        "novelty_check": {
            "not_equivalent_to_existing": True,
            "not_simple_sign_flip": True,
            "not_only_parameter_change": True,
        },
    }


def _sanitize_new_template(template: dict[str, Any] | None) -> dict[str, Any] | None:
    if not template:
        return None

    required = ["template_name", "expression", "allowed_windows", "category", "reason", "novelty_check"]
    if any(key not in template for key in required):
        return None

    allowed_windows = [
        int(window)
        for window in template["allowed_windows"]
        if isinstance(window, int) and window in ALLOWED_WINDOWS
    ]
    if not allowed_windows:
        return None

    expression = str(template["expression"])
    allowed_tokens = {
        "rank",
        "delta",
        "mean",
        "std",
        "correlation",
        "delay",
        "max",
        "close",
        "volume",
        "amount",
        "returns",
        "N",
    }
    tokens = set(re.findall(r"[A-Za-z_]+", expression))
    if not tokens.issubset(allowed_tokens):
        return None

    novelty_check = template.get("novelty_check", {})
    if not all(
        bool(novelty_check.get(key))
        for key in ["not_equivalent_to_existing", "not_simple_sign_flip", "not_only_parameter_change"]
    ):
        return None

    return {
        "template_name": str(template["template_name"]),
        "expression": expression,
        "allowed_windows": sorted(set(allowed_windows)),
        "category": str(template["category"]),
        "reason": str(template["reason"]),
        "novelty_check": novelty_check,
    }
