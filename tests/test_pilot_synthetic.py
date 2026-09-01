from thrumely.pilot_synthetic import run_synthetic_pilot


def test_synthetic_pilot_is_explicit_and_zero_cost():
    result = run_synthetic_pilot()
    assert result["mode"] == "SYNTHETIC_PILOT_ONLY"
    assert result["network_calls"] == 0
    assert result["credits_spent"] == 0
    assert result["rating_summary"]
    assert result["pairwise_summary"]
    assert result["bootstrap"]["tasks"] >= 2
    assert result["power"]["tasks"] >= 2
    assert result["budget"]["required_credits"] > 0
