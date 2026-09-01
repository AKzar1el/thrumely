from __future__ import annotations

from dataclasses import dataclass

NORMALIZED_ASPECT_RATIOS = frozenset({"1:1", "3:2", "2:3", "16:9", "9:16"})
NORMALIZED_QUALITY_TIERS = frozenset({"draft", "standard", "high"})
_REQUIRED_OPERATIONS = frozenset({"generate", "edit_previous"})


@dataclass(frozen=True)
class ProviderCapability:
    backend_id: str
    provider: str
    model: str
    operations: frozenset[str]
    aspect_ratios: frozenset[str]
    quality_tiers: frozenset[str]
    pinned_snapshot: bool
    notes: str


def candidate_capabilities() -> tuple[ProviderCapability, ...]:
    return (
        ProviderCapability(
            backend_id="openai:gpt-image-2",
            provider="openai",
            model="gpt-image-2-2026-04-21",
            operations=_REQUIRED_OPERATIONS,
            aspect_ratios=NORMALIZED_ASPECT_RATIOS,
            quality_tiers=NORMALIZED_QUALITY_TIERS,
            pinned_snapshot=True,
            notes="Dated OpenAI image-model snapshot; live calibration remains pending.",
        ),
        ProviderCapability(
            backend_id="google:gemini-3.1-flash-image",
            provider="google",
            model="gemini-3.1-flash-image",
            operations=_REQUIRED_OPERATIONS,
            aspect_ratios=NORMALIZED_ASPECT_RATIOS,
            quality_tiers=NORMALIZED_QUALITY_TIERS,
            pinned_snapshot=False,
            notes="Stable Google model alias; exact serving version must be recorded at run time.",
        ),
        ProviderCapability(
            backend_id="bfl:flux-2-pro",
            provider="bfl",
            model="flux-2-pro",
            operations=_REQUIRED_OPERATIONS,
            aspect_ratios=NORMALIZED_ASPECT_RATIOS,
            quality_tiers=NORMALIZED_QUALITY_TIERS,
            pinned_snapshot=True,
            notes="BFL documents /flux-2-pro as the fixed FLUX.2 Pro snapshot.",
        ),
    )


def validate_candidate_matrix(
    capabilities: tuple[ProviderCapability, ...] | None = None,
) -> tuple[str, ...]:
    items = candidate_capabilities() if capabilities is None else capabilities
    blockers: list[str] = []
    if len(items) != 3:
        blockers.append(f"candidate matrix must contain exactly 3 image backends; found {len(items)}")

    backend_ids = [item.backend_id for item in items]
    if len(set(backend_ids)) != len(backend_ids):
        blockers.append("candidate backend IDs must be unique")

    for item in items:
        missing_ops = _REQUIRED_OPERATIONS - item.operations
        if missing_ops:
            blockers.append(f"{item.backend_id} is missing operations: {', '.join(sorted(missing_ops))}")
        missing_ratios = NORMALIZED_ASPECT_RATIOS - item.aspect_ratios
        if missing_ratios:
            blockers.append(f"{item.backend_id} is missing aspect ratios: {', '.join(sorted(missing_ratios))}")
        missing_tiers = NORMALIZED_QUALITY_TIERS - item.quality_tiers
        if missing_tiers:
            blockers.append(f"{item.backend_id} is missing quality tiers: {', '.join(sorted(missing_tiers))}")

    return tuple(blockers)
