import json

import pytest

from thrumely.datapoint_client import DatapointClient


class FakeTransport:
    def __init__(self, response):
        self.calls = []
        self.response = response

    def __call__(self, method, url, headers, body, content_type):
        self.calls.append((method, url, headers, body, content_type))
        return 200, json.dumps(self.response).encode("utf-8")


def test_preview_uses_client_transport_and_stable_user_agent():
    transport = FakeTransport({"data": {"tasks": [{"task_id": "preview-1"}]}})
    result = DatapointClient("dp_live_secret", transport=transport).get_preview("job_1")
    method, url, headers, body, content_type = transport.calls[0]
    assert method == "GET"
    assert url.endswith("/jobs/job_1/preview")
    assert headers["User-Agent"].startswith("Thrumely/")
    assert "urllib" not in headers["User-Agent"].lower()
    assert body is None
    assert content_type is None
    assert result["data"]["tasks"][0]["task_id"] == "preview-1"


def test_preview_rejects_unsafe_job_id_before_transport():
    transport = FakeTransport({"data": {"tasks": []}})
    client = DatapointClient("dp_live_secret", transport=transport)
    with pytest.raises(ValueError, match="job_id"):
        client.get_preview("../job")
    assert transport.calls == []
