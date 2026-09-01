from __future__ import annotations

from thrumely.interfaces import (
    ControllerExecutionError,
    ControllerProtocolError,
    ProviderExecutionError,
)
from thrumely.bfl_provider import BFLProviderExecutionError
from thrumely.google_provider import GoogleProviderExecutionError
from thrumely.openai_provider import ProviderExecutionError as OpenAIProviderExecutionError
from thrumely.openai_controller import (
    ControllerExecutionError as OpenAIControllerExecutionError,
    ControllerProtocolError as OpenAIControllerProtocolError,
)


def test_provider_errors_share_one_calibration_boundary() -> None:
    assert OpenAIProviderExecutionError is ProviderExecutionError
    assert issubclass(BFLProviderExecutionError, ProviderExecutionError)
    assert issubclass(GoogleProviderExecutionError, ProviderExecutionError)


def test_controller_errors_share_one_calibration_boundary() -> None:
    assert OpenAIControllerExecutionError is ControllerExecutionError
    assert OpenAIControllerProtocolError is ControllerProtocolError
