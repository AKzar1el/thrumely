from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from thrumely.cloudflare_provider import CloudflareImageProvider, CloudflareProviderExecutionError
from thrumely.schema import MediaOperation, NormalizedMediaRequest, ToolEnvironment


class FailingTransport:
    def __init__(self, error: HTTPError) -> None:
        self.error = error

    def post_multipart(self, url, headers, fields, files):
        raise self.error


def request() -> NormalizedMediaRequest:
    environment = ToolEnvironment(
        "cloudflare-fixed",
        "fixed",
        ("cloudflare:flux-2-klein-4b",),
    )
    return NormalizedMediaRequest(
        backend="cloudflare:flux-2-klein-4b",
        prompt="Create a harmless calibration image",
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=None,
        environment=environment,
    )


def http_error(*, status: int, body: object, retry_after: str | None = None) -> HTTPError:
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    encoded = json.dumps(body).encode("utf-8")
    return HTTPError(
        "https://api.cloudflare.com/client/v4/accounts/secret/ai/run/model",
        status,
        "provider message must not be persisted",
        headers,
        io.BytesIO(encoded),
    )


def test_http_error_reports_only_status_numeric_cloudflare_code_and_retry_after() -> None:
    error = http_error(
        status=429,
        retry_after="12",
        body={
            "success": False,
            "errors": [
                {
                    "code": 3040,
                    "message": "No more data centers; secret prompt text must not leak",
                }
            ],
        },
    )
    provider = CloudflareImageProvider(
        account_id="account-secret",
        api_token="token-secret",
        transport=FailingTransport(error),
    )

    with pytest.raises(CloudflareProviderExecutionError) as caught:
        provider.execute(request())

    message = str(caught.value)
    assert message == "Cloudflare image request failed (HTTP 429, code 3040, retry-after 12s)"
    assert "No more data centers" not in message
    assert "secret prompt" not in message
    assert "account-secret" not in message
    assert "token-secret" not in message


def test_http_error_with_unparseable_body_reports_status_only_without_body_echo() -> None:
    error = HTTPError(
        "https://api.cloudflare.com/client/v4/accounts/secret/ai/run/model",
        500,
        "provider detail must not leak",
        {},
        io.BytesIO(b"arbitrary upstream body that must not leak"),
    )
    provider = CloudflareImageProvider(
        account_id="account-secret",
        api_token="token-secret",
        transport=FailingTransport(error),
    )

    with pytest.raises(CloudflareProviderExecutionError) as caught:
        provider.execute(request())

    message = str(caught.value)
    assert message == "Cloudflare image request failed (HTTP 500)"
    assert "arbitrary upstream body" not in message
    assert "provider detail" not in message
