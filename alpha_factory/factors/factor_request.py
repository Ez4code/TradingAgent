from dataclasses import dataclass, field


@dataclass(frozen=True)
class NaturalLanguageFactorRequest:
    raw_text: str
    target_style: str = "general"
    preferred_horizon: str = "medium"
    factor_intent: str = "basic_factor_research"
    constraints: dict[str, object] = field(default_factory=dict)
