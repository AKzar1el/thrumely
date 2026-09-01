import pytest

from thrumely.budget import project_annotation_credits


def test_credit_projection_known_balance_and_boundary():
    projection = project_annotation_credits(
        400,
        2,
        available_credits=1000,
        min_reserve_fraction=0.2,
    )
    assert projection.required_credits == 800
    assert projection.remaining_credits == 200
    assert projection.reserve_passed is True

    failure = project_annotation_credits(
        401,
        2,
        available_credits=1000,
        min_reserve_fraction=0.2,
    )
    assert failure.reserve_passed is False


def test_credit_projection_unknown_balance():
    projection = project_annotation_credits(100, 5)
    assert projection.required_credits == 500
    assert projection.remaining_credits is None
    assert projection.reserve_passed is None
    with pytest.raises(ValueError):
        project_annotation_credits(True, 5)


def test_zero_balance_projection_never_emits_nonfinite_fraction():
    projection = project_annotation_credits(1, 5, available_credits=0)
    assert projection.remaining_credits == -5
    assert projection.remaining_fraction == 0.0
    assert projection.reserve_passed is False
