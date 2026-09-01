from thrumely.redaction import redact_secrets, sanitize_public_payload, strip_private_reasoning


def test_public_payload_redacts_secret_keys_and_removes_reasoning() -> None:
    payload = {
        "authorization": "Bearer secret",
        "nested": {"api_key": "abc", "safe": "keep"},
        "reasoning": "private",
        "encrypted_content": "ciphertext",
        "blocks": [
            {"type": "reasoning", "text": "hidden"},
            {"type": "redacted_reasoning", "text": "also hidden"},
            {"type": "text", "text": "visible"},
        ],
    }
    assert sanitize_public_payload(payload) == {
        "authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "safe": "keep"},
        "blocks": [{"type": "text", "text": "visible"}],
    }


def test_redaction_is_case_insensitive_and_handles_tuples() -> None:
    payload = ({"Access_Token": "x"}, {"Password": "y"})
    assert redact_secrets(payload) == [
        {"Access_Token": "[REDACTED]"},
        {"Password": "[REDACTED]"},
    ]


def test_reasoning_strip_preserves_safe_nested_values() -> None:
    assert strip_private_reasoning({"safe": {"value": 1}}) == {"safe": {"value": 1}}
