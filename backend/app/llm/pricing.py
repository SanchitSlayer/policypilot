"""Cost estimation from the editable pricing table (config/pricing.yaml)."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.config import get_settings


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


@dataclass(frozen=True)
class CostEstimate:
    usd: float
    known: bool  # False when the model is not in the pricing table


class PricingTable:
    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices
        # Longest names first, so "gpt-4o-mini" wins over "gpt-4o" for prefix matches.
        self._by_length = sorted(prices, key=len, reverse=True)

    @classmethod
    def from_yaml(cls, path: Path) -> "PricingTable":
        data = yaml.safe_load(path.read_text()) or {}
        prices = {
            str(name): ModelPrice(float(entry["input"]), float(entry.get("output", 0.0)))
            for name, entry in (data.get("models") or {}).items()
        }
        return cls(prices)

    def price_for(self, model: str) -> ModelPrice | None:
        if model in self._prices:
            return self._prices[model]
        # Versioned names ("models/gemini-2.5-flash", "gpt-5.4-mini-2026-03-17")
        normalized = model.removeprefix("models/")
        for name in self._by_length:
            if normalized == name or normalized.startswith(f"{name}-"):
                return self._prices[name]
        return None

    def estimate(self, model: str, input_tokens: int, output_tokens: int) -> CostEstimate:
        price = self.price_for(model)
        if price is None:
            return CostEstimate(usd=0.0, known=False)
        usd = (
            input_tokens * price.input_per_million + output_tokens * price.output_per_million
        ) / 1_000_000
        return CostEstimate(usd=round(usd, 8), known=True)


@lru_cache
def get_pricing() -> PricingTable:
    return PricingTable.from_yaml(Path(get_settings().pricing_file))
