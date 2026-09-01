from thrumely.datapoint_sandbox import run_offline_sandbox


def test_offline_sandbox_round_trips_pairwise_and_rating():
    result = run_offline_sandbox()
    assert result["mode"] == "OFFLINE_FAKE_SANDBOX"
    assert result["network_calls"] == 0
    assert result["jobs_created"] == 2
    assert result["pairwise"]["serving_environment"] == "sandbox"
    assert result["pairwise"]["normalized_results"][0]["votes_a"] == 4
    assert result["rating"]["normalized_results"][0]["mean"] == 4.0
    assert result["rating"]["public_responses"][0]["response"] == "4"
