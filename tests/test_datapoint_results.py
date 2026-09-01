import pytest

from thrumely.datapoint_results import normalize_comparison_results, normalize_public_responses, normalize_rating_results


def test_normalize_comparison_results_maps_media_order_and_ignores_extras():
    payload = {"job_id": "job_cmp", "task_type": "comparison", "results": [{"datapoint_index": 0, "votes": {"A": 4, "B": 1}, "total_responses": 5, "consensus": "A", "confidence": 0.8, "agreement_rate": 0.8, "media": [{"media_id": "m_a", "role": "candidates", "url": "/signed/a"}, {"media_id": "m_b", "role": "candidates", "url": "/signed/b"}], "future_field": {"x": 1}}]}
    rows = normalize_comparison_results(payload)
    assert rows == ({"job_id": "job_cmp", "datapoint_index": 0, "votes_a": 4, "votes_b": 1, "consensus": "A", "total_responses": 5, "confidence": 0.8, "agreement_rate": 0.8, "media_id_a": "m_a", "media_id_b": "m_b"},)


def test_normalize_rating_results_keeps_distribution_and_weighted_fields():
    payload = {"job_id": "job_rate", "task_type": "rating", "results": [{"datapoint_index": 2, "mean": 4.0, "median": 4, "distribution": {"3": 1, "4": 3, "5": 1}, "total_responses": 5, "weighted_mean": 4.1, "weighted_distribution": {"3": 0.7, "4": 3.2, "5": 1.1}}]}
    row = normalize_rating_results(payload)[0]
    assert row["job_id"] == "job_rate" and row["datapoint_index"] == 2
    assert row["distribution"] == {"3": 1, "4": 3, "5": 1}
    assert row["weighted_mean"] == 4.1


def test_public_response_normalization_drops_granular_location():
    payload = {"job_id": "job_cmp", "task_type": "comparison", "responses": [{"datapoint_index": 0, "response": "A", "response_label": "A", "response_time_ms": 4832, "annotator_id": "anon_8f2cd1a3e9", "annotator_country": "US", "annotator_country_name": "United States", "annotator_region": "CA", "annotator_city": "San Francisco", "timestamp": "2026-04-21 12:37:18.452731+00:00"}]}
    row = normalize_public_responses(payload)[0]
    assert row["annotator_id"] == "anon_8f2cd1a3e9"
    assert row["annotator_country"] == "US"
    assert "annotator_city" not in row and "annotator_region" not in row and "annotator_country_name" not in row


def test_result_normalizer_rejects_task_type_mismatch():
    with pytest.raises(ValueError, match="task_type"):
        normalize_comparison_results({"job_id": "x", "task_type": "rating", "results": []})
