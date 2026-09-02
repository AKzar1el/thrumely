from __future__ import annotations

from typing import Any, Mapping

VERCEL_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
VERCEL_CONTROLLER_MODEL = "openai/gpt-5.6-sol"
VERCEL_IMAGE_MODEL = "openai/gpt-image-2"
VERCEL_IMAGE_RELEASE_DATE = "2026-04-21"
VERCEL_GATEWAY_TIMEOUT_SECONDS = 15.0


class GatewayRoutingError(RuntimeError):
    pass


def openai_only_extra_body() -> dict[str, Any]:
    return {"providerOptions": {"gateway": {"only": ["openai"]}}}


def _primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    if hasattr(value, "model_dump"):
        return _primitive(value.model_dump(mode="json", exclude_none=True))
    if hasattr(value, "__dict__"):
        return {
            str(key): _primitive(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def extract_provider_metadata(response: Any) -> Mapping[str, Any]:
    value = getattr(response, "provider_metadata", None)
    if value is None:
        value = getattr(response, "providerMetadata", None)
    if value is None:
        model_extra = getattr(response, "model_extra", None)
        if isinstance(model_extra, Mapping):
            value = model_extra.get("provider_metadata") or model_extra.get("providerMetadata")
    if value is None:
        primitive = _primitive(response)
        if isinstance(primitive, dict):
            value = primitive.get("provider_metadata") or primitive.get("providerMetadata")
    primitive = _primitive(value)
    return primitive if isinstance(primitive, dict) else {}


def _field(mapping: Mapping[str, Any], camel: str, snake: str) -> Any:
    if camel in mapping:
        return mapping[camel]
    return mapping.get(snake)


def validate_gateway_routing(
    provider_metadata: Mapping[str, Any],
    *,
    required_provider: str,
) -> Mapping[str, Any]:
    gateway = provider_metadata.get("gateway")
    if not isinstance(gateway, Mapping):
        raise GatewayRoutingError("gateway routing metadata is missing")
    routing = gateway.get("routing")
    if not isinstance(routing, Mapping):
        raise GatewayRoutingError("gateway routing metadata is missing")

    final_provider = _field(routing, "finalProvider", "final_provider")
    resolved_provider = _field(routing, "resolvedProvider", "resolved_provider")
    model_attempt_count = _field(routing, "modelAttemptCount", "model_attempt_count")
    provider_attempt_count = _field(
        routing,
        "totalProviderAttemptCount",
        "total_provider_attempt_count",
    )

    if final_provider != required_provider or resolved_provider != required_provider:
        raise GatewayRoutingError("gateway used an unexpected provider")
    if model_attempt_count != 1 or provider_attempt_count != 1:
        raise GatewayRoutingError("gateway used more than one model or provider attempt")

    model_attempts = _field(routing, "modelAttempts", "model_attempts")
    if not isinstance(model_attempts, list) or len(model_attempts) != 1:
        raise GatewayRoutingError("gateway model-attempt provenance is incomplete")
    model_attempt = model_attempts[0]
    if not isinstance(model_attempt, Mapping):
        raise GatewayRoutingError("gateway model-attempt provenance is invalid")

    provider_attempts = _field(model_attempt, "providerAttempts", "provider_attempts")
    if not isinstance(provider_attempts, list) or len(provider_attempts) != 1:
        raise GatewayRoutingError("gateway provider-attempt provenance is incomplete")
    provider_attempt = provider_attempts[0]
    if not isinstance(provider_attempt, Mapping):
        raise GatewayRoutingError("gateway provider-attempt provenance is invalid")
    if provider_attempt.get("provider") != required_provider or provider_attempt.get("success") is not True:
        raise GatewayRoutingError("gateway provider attempt did not satisfy the required route")

    return routing
