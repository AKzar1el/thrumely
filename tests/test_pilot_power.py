import pytest

from thrumely.pilot_power import estimate_task_difference_sd, simulate_power_from_task_sd


def test_estimate_task_difference_sd():
    estimate = estimate_task_difference_sd((0.0, 0.2, 0.4))
    assert estimate.tasks == 3
    assert estimate.mean_difference == pytest.approx(0.2)
    assert estimate.sample_sd == pytest.approx(0.2)
    with pytest.raises(ValueError):
        estimate_task_difference_sd((0.1,))


def test_power_from_task_sd_is_deterministic():
    first = simulate_power_from_task_sd(
        (-0.2, 0.1, 0.3, 0.5),
        target_tasks=50,
        effect=0.2,
        simulations=500,
        alpha=0.05,
        seed=3,
    )
    second = simulate_power_from_task_sd(
        (-0.2, 0.1, 0.3, 0.5),
        target_tasks=50,
        effect=0.2,
        simulations=500,
        alpha=0.05,
        seed=3,
    )
    assert first == second
    assert 0 <= first.estimated_power <= 1


def test_task_difference_estimate_rejects_boolean_and_nonnumeric_values():
    with pytest.raises((TypeError, ValueError), match="numeric"):
        estimate_task_difference_sd((True, 0.2))
    with pytest.raises((TypeError, ValueError), match="numeric"):
        estimate_task_difference_sd(("oops", 0.2))


def test_power_wrapper_rejects_boolean_configuration_values():
    differences = (-0.2, 0.1, 0.3, 0.5)
    with pytest.raises(ValueError, match="effect"):
        simulate_power_from_task_sd(
            differences,
            target_tasks=50,
            effect=True,
            simulations=100,
            seed=3,
        )
    with pytest.raises(ValueError, match="simulations"):
        simulate_power_from_task_sd(
            differences,
            target_tasks=50,
            effect=0.2,
            simulations=True,
            seed=3,
        )
    with pytest.raises(ValueError, match="seed"):
        simulate_power_from_task_sd(
            differences,
            target_tasks=50,
            effect=0.2,
            simulations=100,
            seed=True,
        )
