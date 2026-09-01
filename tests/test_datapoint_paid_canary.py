import json

import pytest

from thrumely.datapoint_client import DatapointClient, DatapointClientError


class FakeTransport:
    def __init__(self, responses):
        self.calls = []
        self.responses = list(responses)

    def __call__(self, method, url, headers, body, content_type):
        self.calls.append((method, url, headers, body, content_type))
        status, payload = self.responses.pop(0)
        return status, json.dumps(payload).encode("utf-8")


def _payload():
    return {
        "name": "thrumely-canary-1",
        "instruction": "Which result better follows the request?",
        "task_type": "comparison",
        "max_responses_per_datapoint": 1,
        "serving_environment": "prod",
        "datapoints": [
            {
                "media": {
                    "candidates": [
                        {"url": "dp://abc/a.svg", "type": "image"},
                        {"url": "dp://def/b.svg", "type": "image"},
                    ]
                }
            }
        ],
    }


def test_paid_canary_accepts_only_one_prod_comparison_response():
    transport = FakeTransport(
        [
            (
                200,
                {
                    "job_id": "job_canary",
                    "estimated_cost_credits": 5,
                    "credits_per_response": 5,
                },
            )
        ]
    )
    client = DatapointClient("dp_live_secret", transport=transport)
    result = client.create_production_canary_job(_payload(), max_estimated_credits=25)
    assert result["job_id"] == "job_canary"
    assert len(transport.calls) == 1

    for mutate in (
        lambda p: p.update(serving_environment="sandbox"),
        lambda p: p.update(max_responses_per_datapoint=2),
        lambda p: p.update(datapoints=p["datapoints"] * 2),
        lambda p: p.update(task_type="rating"),
        lambda p: p.update(annotator_filter={"country": ["US"]}),
        lambda p: p.update(dimensions={"faithfulness": "Rate faithfulness"}),
        lambda p: p.update(steps=[{"task_type": "comparison", "instruction": "Pick one"}]),
    ):
        bad = _payload()
        mutate(bad)
        with pytest.raises(ValueError, match="canary"):
            client.create_production_canary_job(bad, max_estimated_credits=25)
    assert len(transport.calls) == 1


def test_paid_canary_auto_cancels_if_server_price_exceeds_cap():
    transport = FakeTransport(
        [
            (
                200,
                {
                    "job_id": "job_expensive",
                    "estimated_cost_credits": 30,
                    "credits_per_response": 30,
                },
            ),
            (
                200,
                {
                    "job_id": "job_expensive",
                    "status": "cancelled",
                    "cost_credits": 0,
                    "released_credits": 30,
                },
            ),
        ]
    )
    client = DatapointClient("dp_live_secret", transport=transport)
    with pytest.raises(DatapointClientError, match="exceeded"):
        client.create_production_canary_job(_payload(), max_estimated_credits=25)
    assert transport.calls[1][0] == "POST"
    assert transport.calls[1][1].endswith("/jobs/job_expensive/cancel")


def test_paid_canary_rejects_price_shape_mismatch_and_cancels():
    transport = FakeTransport(
        [
            (
                200,
                {
                    "job_id": "job_badprice",
                    "estimated_cost_credits": 10,
                    "credits_per_response": 5,
                },
            ),
            (
                200,
                {
                    "job_id": "job_badprice",
                    "status": "cancelled",
                    "cost_credits": 0,
                    "released_credits": 10,
                },
            ),
        ]
    )
    client = DatapointClient("dp_live_secret", transport=transport)
    with pytest.raises(DatapointClientError, match="pricing"):
        client.create_production_canary_job(_payload(), max_estimated_credits=25)
    assert transport.calls[1][1].endswith("/jobs/job_badprice/cancel")


def test_cancel_and_complete_validate_job_ids():
    transport = FakeTransport(
        [
            (200, {"job_id": "job_1", "status": "cancelled"}),
            (200, {"job_id": "job_2", "status": "completed"}),
        ]
    )
    client = DatapointClient("dp_live_secret", transport=transport)
    assert client.cancel_job("job_1")["status"] == "cancelled"
    assert client.complete_job("job_2")["status"] == "completed"
    for bad in ("../job", "job/1", "job?x=1"):
        with pytest.raises(ValueError, match="job_id"):
            client.cancel_job(bad)
        with pytest.raises(ValueError, match="job_id"):
            client.complete_job(bad)
    assert len(transport.calls) == 2
