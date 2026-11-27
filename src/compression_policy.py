"""Políticas de compresión del contexto conversacional (nivel técnico).

Niveles alineados con configs/compilation_profiles.json: safe /
balanced / aggressive. El perfil de modelo ``hermes`` de
configs/model_profiles.json declara ``compression_tolerance: low`` y
``best_level: safe``; por eso el nivel por defecto público aquí es
``safe`` y se recomienda no bajarlo para objetivos Hermes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionPolicy:
    """Umbrales de decisión para la compresión de contexto.

    trigger_ratio:              fracción de num_ctx que dispara la
                                compresión (p. ej. 0.70 -> al 70 %).
    keep_recent_turns:          turnos recientes que entran siempre
                                íntegros en la ventana reconstruida.
    max_summary_tokens:         presupuesto máximo del resumen de
                                turnos intermedios.
    offload_max_inline_tokens:  turnos no recientes por encima de este
                                tamaño se mueven a archivo local y se
                                sustituyen por un puntero (nunca si
                                contienen bloques de código).
    offload_enabled:            si el offloading está permitido.
    """

    level: str
    trigger_ratio: float
    keep_recent_turns: int
    max_summary_tokens: int
    offload_max_inline_tokens: int
    offload_enabled: bool

    def triggers_at(self, num_ctx: int) -> int:
        """Umbral en tokens a partir del cual se comprime."""
        if num_ctx <= 0:
            raise ValueError("num_ctx debe ser un entero positivo")
        return int(num_ctx * self.trigger_ratio)


POLICIES: dict[str, CompressionPolicy] = {
    "safe": CompressionPolicy(
        level="safe",
        trigger_ratio=0.70,
        keep_recent_turns=8,
        max_summary_tokens=600,
        offload_max_inline_tokens=600,
        offload_enabled=True,
    ),
    "balanced": CompressionPolicy(
        level="balanced",
        trigger_ratio=0.80,
        keep_recent_turns=5,
        max_summary_tokens=400,
        offload_max_inline_tokens=400,
        offload_enabled=True,
    ),
    "aggressive": CompressionPolicy(
        level="aggressive",
        trigger_ratio=0.88,
        keep_recent_turns=3,
        max_summary_tokens=250,
        offload_max_inline_tokens=250,
        offload_enabled=True,
    ),
}

DEFAULT_LEVEL = "safe"


def get_policy(level: str | None = None) -> CompressionPolicy:
    """Devuelve la política de un nivel; `None` usa DEFAULT_LEVEL."""
    key = (level or DEFAULT_LEVEL).lower()
    if key not in POLICIES:
        raise ValueError(
            f"Nivel de compresión desconocido: {level!r}. "
            f"Válidos: {sorted(POLICIES)}"
        )
    return POLICIES[key]


def needs_compaction(total_tokens: int, num_ctx: int,
                     level: str | None = None) -> bool:
    """True si el historial ha alcanzado el umbral de compresión."""
    return total_tokens >= get_policy(level).triggers_at(num_ctx)
