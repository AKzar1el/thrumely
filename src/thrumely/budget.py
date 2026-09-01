from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreditProjection:
    responses: int
    credits_per_response: int
    required_credits: int
    available_credits: int | None
    remaining_credits: int | None
    remaining_fraction: float | None
    min_reserve_fraction: float
    reserve_passed: bool | None


def _nonnegative_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def project_annotation_credits(
    responses: int,
    credits_per_response: int,
    *,
    available_credits: int | None = None,
    min_reserve_fraction: float = 0.20,
) -> CreditProjection:
    _nonnegative_int("responses", responses)
    _nonnegative_int("credits_per_response", credits_per_response)
    if available_credits is not None:
        _nonnegative_int("available_credits", available_credits)
    if (
        not isinstance(min_reserve_fraction, (int, float))
        or isinstance(min_reserve_fraction, bool)
        or not 0 <= float(min_reserve_fraction) < 1
    ):
        raise ValueError("min_reserve_fraction must be in [0, 1)")

    reserve = float(min_reserve_fraction)
    required = responses * credits_per_response
    if available_credits is None:
        return CreditProjection(
            responses=responses,
            credits_per_response=credits_per_response,
            required_credits=required,
            available_credits=None,
            remaining_credits=None,
            remaining_fraction=None,
            min_reserve_fraction=reserve,
            reserve_passed=None,
        )

    remaining = available_credits - required
    if available_credits > 0:
        remaining_fraction = remaining / available_credits
    else:
        remaining_fraction = 1.0 if required == 0 else 0.0
    reserve_passed = remaining >= 0 and remaining_fraction + 1e-12 >= reserve
    return CreditProjection(
        responses=responses,
        credits_per_response=credits_per_response,
        required_credits=required,
        available_credits=available_credits,
        remaining_credits=remaining,
        remaining_fraction=remaining_fraction,
        min_reserve_fraction=reserve,
        reserve_passed=reserve_passed,
    )
