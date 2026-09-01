import pytest

from thrumely.datapoint_protocol import build_pairwise_sandbox_job, build_rating_sandbox_job


def test_pairwise_sandbox_payload_is_forced_choice_and_sandbox_only():
    payload = build_pairwise_sandbox_job(
        "pairwise-smoke",
        "Create a red mug on a white table.",
        [{"candidate_a": "dp://a/red.png", "candidate_b": "dp://b/blue.png"}],
    )
    assert payload["task_type"] == "comparison"
    assert payload["serving_environment"] == "sandbox"
    assert payload["max_responses_per_datapoint"] == 5
    candidates = payload["datapoints"][0]["media"]["candidates"]
    assert [item["url"] for item in candidates] == ["dp://a/red.png", "dp://b/blue.png"]
    assert all(item["type"] == "image" for item in candidates)
    assert "Tie" not in payload["instruction"]
    assert "Create a red mug on a white table." in payload["instruction"]
    assert "context" not in payload["datapoints"][0]


def test_rating_sandbox_payload_uses_five_point_scale_and_context():
    payload = build_rating_sandbox_job("rating-smoke", [{"context": "Create a red mug on a white table.", "subject": "dp://a/red.png"}])
    assert payload["task_type"] == "rating"
    assert payload["serving_environment"] == "sandbox"
    assert payload["response_options"]["scale"] == [1, 2, 3, 4, 5]
    assert "{context}" in payload["instruction"]
    assert payload["datapoints"][0]["media"]["subject"][0]["url"] == "dp://a/red.png"


def test_protocol_validates_media_and_response_count():
    with pytest.raises(ValueError, match="media reference"):
        build_rating_sandbox_job("bad", [{"context": "x", "subject": "./local.png"}])
    with pytest.raises(ValueError, match="max_responses"):
        build_pairwise_sandbox_job(
            "bad",
            "x",
            [{"candidate_a": "dp://a/a.png", "candidate_b": "dp://b/b.png"}],
            max_responses_per_datapoint=0,
        )
