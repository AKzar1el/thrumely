import pytest

from thrumely.power import PowerSimulationConfig, simulate_power


def test_power_config_rejects_invalid_values():
    with pytest.raises(ValueError):
        PowerSimulationConfig(tasks=1, effect=0.2)
    with pytest.raises(ValueError):
        PowerSimulationConfig(tasks=100, effect=0.2, alpha=1.0)
    with pytest.raises(ValueError):
        PowerSimulationConfig(tasks=100, effect=0.2, simulations=0)


def test_power_simulation_is_seed_reproducible():
    config = PowerSimulationConfig(tasks=100, effect=0.2, simulations=500, seed=42)
    assert simulate_power(config) == simulate_power(config)


def test_zero_effect_false_positive_rate_is_near_alpha():
    result = simulate_power(PowerSimulationConfig(tasks=100, effect=0.0, simulations=3000, seed=7))
    assert 0.03 <= result.estimated_power <= 0.07
    assert abs(result.mean_simulated_effect) < 0.02


def test_larger_effect_and_more_tasks_raise_power():
    small = simulate_power(PowerSimulationConfig(tasks=40, effect=0.1, simulations=1500, seed=9))
    large = simulate_power(PowerSimulationConfig(tasks=120, effect=0.3, simulations=1500, seed=9))
    assert large.estimated_power > small.estimated_power
    assert large.estimated_power > 0.75
