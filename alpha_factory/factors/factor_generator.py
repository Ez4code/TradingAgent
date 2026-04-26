import hashlib
import json
from typing import Any

import pandas as pd

from alpha_factory.config import OUTPUTS_DIR
from alpha_factory.factors.factor_request import NaturalLanguageFactorRequest
from alpha_factory.factors.llm_planner import plan_from_request
from alpha_factory.factors.template_library import get_template_library


REJECTED_COLUMNS = ["template_name", "window", "expression", "reason"]


def generate_factor_plan(request_text: str) -> dict[str, Any]:
    request = NaturalLanguageFactorRequest(raw_text=request_text)
    plan = plan_from_request(request)
    templates = get_template_library()
    generated = []
    rejected = []
    seen_hashes: set[str] = set()

    for index, item in enumerate(plan.get("generated_expressions", []), start=1):
        expression = item["expression"]
        expression_hash = _expression_hash("generated_expression", expression, 0)
        if expression_hash in seen_hashes:
            rejected.append(
                {
                    "template_name": item.get("factor_name", f"llm_generated_{index}"),
                    "window": None,
                    "expression": expression,
                    "reason": "duplicate_expression_hash",
                }
            )
            continue
        seen_hashes.add(expression_hash)
        factor_name = item.get("factor_name") or f"llm_generated_{index}"
        generated.append(
            {
                "factor_type": "generated_expression",
                "factor_name": factor_name,
                "template_name": "generated_expression",
                "window": None,
                "expression": expression,
                "expression_hash": expression_hash,
                "reason": item.get("reason", ""),
                "category": item.get("category", "llm_generated"),
            }
        )

    for item in plan["selected_templates"]:
        template_name = item["template_name"]
        template = templates.get(template_name)
        if template is None:
            rejected.append(
                {
                    "template_name": template_name,
                    "window": None,
                    "expression": "",
                    "reason": "unknown_template",
                }
            )
            continue

        for window in item["windows"]:
            expression = template.expression.replace("N", str(window))
            expression_hash = _expression_hash(template_name, expression, window)
            if expression_hash in seen_hashes:
                rejected.append(
                    {
                        "template_name": template_name,
                        "window": window,
                        "expression": expression,
                        "reason": "duplicate_expression_hash",
                    }
                )
                continue
            seen_hashes.add(expression_hash)
            generated.append(
                {
                    "factor_type": "template",
                    "factor_name": f"{template_name}_{window}",
                    "template_name": template_name,
                    "window": window,
                    "expression": expression,
                    "expression_hash": expression_hash,
                    "reason": item.get("reason", ""),
                    "category": template.category,
                }
            )

    new_template_proposals = []
    if plan.get("need_new_template") and plan.get("new_template"):
        proposal = dict(plan["new_template"])
        proposal["acceptance"] = _new_template_acceptance_stub(proposal)
        new_template_proposals.append(proposal)
        rejected.append(
            {
                "template_name": proposal["template_name"],
                "window": ",".join(str(window) for window in proposal["allowed_windows"]),
                "expression": proposal["expression"],
                "reason": "new_template_requires_acceptance_and_manual_review",
            }
        )

    output = {
        "request": request_text,
        "planner": plan,
        "generated_factors": generated,
        "new_template_proposals": new_template_proposals,
        "rejected_factors": rejected,
    }
    write_factor_generation_outputs(output)
    return output


def write_factor_generation_outputs(output: dict[str, Any]) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    factor_plan = {
        "request": output["request"],
        "planner": output["planner"],
        "generated_factor_count": len(output["generated_factors"]),
        "generated_expression_count": sum(
            1 for item in output["generated_factors"] if item.get("factor_type") == "generated_expression"
        ),
        "rejected_factor_count": len(output["rejected_factors"]),
        "new_template_proposal_count": len(output["new_template_proposals"]),
    }
    _write_json(OUTPUTS_DIR / "factor_plan.json", factor_plan)
    _write_json(OUTPUTS_DIR / "generated_factors.json", output["generated_factors"])
    _write_json(OUTPUTS_DIR / "new_template_proposals.json", output["new_template_proposals"])

    rejected_df = pd.DataFrame(output["rejected_factors"], columns=REJECTED_COLUMNS)
    rejected_df.to_csv(OUTPUTS_DIR / "rejected_factors.csv", index=False)


def _write_json(path: object, data: object) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _expression_hash(template_name: str, expression: str, window: int) -> str:
    raw = f"{template_name}|{window}|{expression}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _new_template_acceptance_stub(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted": False,
        "checks": {
            "executable": "pending",
            "no_future_function": True,
            "correlation_with_existing_below_0_85": "pending",
            "financial_meaning_clear": bool(proposal.get("reason")),
            "rank_ic_not_all_nan": "pending",
            "manual_interpretability_review": "required",
        },
        "reason": "Phase 2 records proposals only; new templates are not added to the formal library automatically.",
    }
