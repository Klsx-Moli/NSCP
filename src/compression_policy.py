from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionPolicy:
    level: str
    trigger_ratio: float
    keep_recent_turns: int
    max_summary_tokens: int
    offload_max_inline_tokens: int
    offload_enabled: bool

    def triggers_at(self, num_ctx):
        if num_ctx <= 0:
            raise ValueError("num_ctx debe ser un entero positivo")
        return int(num_ctx * self.trigger_ratio)


POLICIES = {
    "safe": CompressionPolicy("safe", 0.70, 8, 600, 600, True),
    "balanced": CompressionPolicy("balanced", 0.80, 5, 400, 400, True),
    "aggressive": CompressionPolicy("aggressive", 0.88, 3, 250, 250, True),
}
DEFAULT_LEVEL = "safe"


def get_policy(level=None):
    key = (level or DEFAULT_LEVEL).lower()
    if key not in POLICIES:
        raise ValueError(f"Nivel desconocido: {level!r}. Validos: {sorted(POLICIES)}")
    return POLICIES[key]


def needs_compaction(total_tokens, num_ctx, level=None):
    return total_tokens >= get_policy(level).triggers_at(num_ctx)
