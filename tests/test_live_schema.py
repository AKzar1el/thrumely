from __future__ import annotations

import pytest

from thrumely.interfaces import ControllerDecision, ProviderMediaResult
from thrumely.schema import ControllerConfig, NormalizedMediaRequest, MediaOperation, ToolCallRecord, ToolEnvironment


def test_controller_config_accepts_frozen_live_provenance() -> None:
    config = ControllerConfig(
        controller_id="openai-sol-calibration",
        provider="openai",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        max_output_tokens=1024,
        system_prompt_sha256="a" * 64,
        sdk_version="3.6.0",
    )
    assert config.model == "gpt-5.6-sol"
    assert config.reasoning_effort == "medium"


def test_controller_config_rejects_bad_system_prompt_hash() -> None:
    with pytest.raises(ValueError, match="system_prompt_sha256"):
        ControllerConfig(
            controller_id="openai-sol-calibration",
            provider="openai",
            model="gpt-5.6-sol",
            system_prompt_sha256="not-a-hash",
        )


def test_controller_decision_finish_has_no_media_request() -> None:
    decision = ControllerDecision(
        action="finish",
        request=None,
        response_id="resp_test",
        actual_model="gpt-5.6-sol",
        usage={"input_tokens": 10, "output_tokens": 2},
        observable_output=(),
    )
    assert decision.request is None


def test_controller_decision_media_requires_request() -> None:
    with pytest.raises(ValueError, match="media action"):
        ControllerDecision(
            action="media",
            request=None,
            response_id="resp_test",
            actual_model="gpt-5.6-sol",
            usage={},
            observable_output=(),
        )


def test_provider_result_rejects_negative_retry_count() -> None:
    with pytest.raises(ValueError, match="retry_count"):
        ProviderMediaResult(
            media_bytes=b"png",
            mime_type="image/png",
            width=1024,
            height=1024,
            provider="openai",
            model="gpt-image-2-2026-04-21",
            raw_request={},
            raw_response={},
            request_id="img_test",
            latency_seconds=0.1,
            cost_usd=None,
            moderation_status=None,
            retry_count=-1,
            usage={},
        )


def test_tool_call_record_accepts_live_provider_metadata() -> None:
    environment = ToolEnvironment("fixed-openai", "fixed", ("openai:gpt-image-2",))
    request = NormalizedMediaRequest(
        backend="openai:gpt-image-2",
        prompt="blue square",
        operation=MediaOperation.GENERATE,
        aspect_ratio="1:1",
        quality_tier="standard",
        previous_artifact_id=None,
        environment=environment,
    )
    record = ToolCallRecord(
        call_index=1,
        request=request,
        raw_request={},
        raw_response={},
        request_id="img_test",
        artifact_id="artifact_test",
        latency_seconds=0.1,
        cost_usd=None,
        error=None,
        moderation_status=None,
        provider="openai",
        model="gpt-image-2-2026-04-21",
        retry_count=0,
        usage={"output_tokens": 196},
    )
    assert record.provider == "openai"
    assert record.retry_count == 0
