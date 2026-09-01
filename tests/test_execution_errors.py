from __future__ import annotations

from thrumely.interfaces import (
    ControllerExecutionError,
    ControllerProtocolError,
    ProviderExecutionError,
)


def test_generic_execution_errors_are_typed_runtime_boundaries() -> None:
    assert issubclass(ProviderExecutionError, RuntimeError)
    assert issubclass(ControllerExecutionError, RuntimeError)
    assert issubclass(ControllerProtocolError, RuntimeError)
