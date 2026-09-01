import json
from pathlib import Path

import pytest

from thrumely.datapoint_client import DatapointClient, DatapointClientError


class FakeTransport:
    def __init__(self, responses=None, error=None):
        self.calls = []
        self.responses = list(responses or [])
        self.error = error

    def __call__(self, method, url, headers, body, content_type):
        self.calls.append((method, url, headers, body, content_type))
        if self.error:
            raise self.error
        status, payload = self.responses.pop(0)
        return status, json.dumps(payload).encode("utf-8")


def test_create_job_injects_key_but_refuses_non_sandbox_before_transport():
    transport = FakeTransport([(200, {"job_id": "job_1", "serving_environment": "sandbox"})])
    client = DatapointClient("dp_live_secret", transport=transport)
    payload = {"name": "x", "task_type": "rating", "serving_environment": "sandbox", "datapoints": [{"media": {}}]}
    result = client.create_sandbox_job(payload)
    assert result["job_id"] == "job_1"
    assert transport.calls[0][2]["X-API-Key"] == "dp_live_secret"
    for env in ("prod", "all", None):
        bad = dict(payload)
        bad["serving_environment"] = env
        with pytest.raises(ValueError, match="sandbox"):
            client.create_sandbox_job(bad)
    assert len(transport.calls) == 1


def test_client_error_never_leaks_api_key():
    transport = FakeTransport(error=RuntimeError("request failed using dp_live_secret"))
    client = DatapointClient("dp_live_secret", transport=transport)
    with pytest.raises(DatapointClientError) as exc:
        client.get_job("job_1")
    assert "dp_live_secret" not in str(exc.value)


def test_upload_media_builds_multipart_and_returns_dp_ref(tmp_path: Path):
    image = tmp_path / "sample.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    transport = FakeTransport([(200, {"media": [{"media_id": "m_1", "media_ref": "dp://a1b2c3d4e5f6/sample.png", "type": "image", "size_bytes": 15}]})])
    client = DatapointClient("dp_live_secret", transport=transport)
    result = client.upload_media(image)
    method, url, headers, body, content_type = transport.calls[0]
    assert method == "POST" and url.endswith("/media")
    assert "multipart/form-data; boundary=" in content_type
    assert b"sample.png" in body and b"fixture" in body
    assert result["media_ref"] == "dp://a1b2c3d4e5f6/sample.png"


def test_http_error_body_cannot_echo_api_key():
    transport = FakeTransport([(401, {"detail": "invalid key dp_live_secret"})])
    client = DatapointClient("dp_live_secret", transport=transport)
    with pytest.raises(DatapointClientError) as exc:
        client.get_job("job_1")
    assert "dp_live_secret" not in str(exc.value)


def test_job_id_rejects_path_metacharacters_before_transport():
    transport = FakeTransport([])
    client = DatapointClient("dp_live_secret", transport=transport)
    for job_id in ("../jobs", "job_1/results", "job?x=1", ""):
        with pytest.raises(ValueError, match="job_id"):
            client.get_job(job_id)
    assert transport.calls == []


def test_upload_rejects_header_unsafe_filename(tmp_path: Path):
    image = tmp_path / 'bad"name.png'
    image.write_bytes(b"fixture")
    client = DatapointClient("dp_live_secret", transport=FakeTransport([]))
    with pytest.raises(ValueError, match="filename"):
        client.upload_media(image)


def test_client_rejects_non_datapoint_base_url():
    with pytest.raises(ValueError, match="base_url"):
        DatapointClient("dp_live_secret", base_url="https://example.com/steal")


def test_get_all_results_follows_result_pagination():
    transport = FakeTransport([
        (200, {"job_id": "job_1", "task_type": "rating", "page": 1, "per_page": 1, "total_results": 2, "results": [{"datapoint_index": 0}]}),
        (200, {"job_id": "job_1", "task_type": "rating", "page": 2, "per_page": 1, "total_results": 2, "results": [{"datapoint_index": 1}]}),
    ])
    client = DatapointClient("dp_live_secret", transport=transport)
    merged = client.get_all_results("job_1", per_page=1)
    assert [row["datapoint_index"] for row in merged["results"]] == [0, 1]
    assert [call[1].split("?", 1)[1] for call in transport.calls] == ["page=1&per_page=1", "page=2&per_page=1"]


def test_get_all_responses_follows_total_pages():
    transport = FakeTransport([
        (200, {"job_id": "job_1", "task_type": "comparison", "page": 1, "per_page": 1, "total_pages": 2, "responses": [{"response": "A"}]}),
        (200, {"job_id": "job_1", "task_type": "comparison", "page": 2, "per_page": 1, "total_pages": 2, "responses": [{"response": "B"}]}),
    ])
    client = DatapointClient("dp_live_secret", transport=transport)
    merged = client.get_all_responses("job_1", per_page=1)
    assert [row["response"] for row in merged["responses"]] == ["A", "B"]
    assert [call[1].split("?", 1)[1] for call in transport.calls] == ["page=1&per_page=1", "page=2&per_page=1"]
