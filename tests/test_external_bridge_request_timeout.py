"""External bridge must not leave storage HTTP operations without a deadline."""
from io import BytesIO
from math import inf, nan
from unittest.mock import patch

import pytest

from backend.app.storage.external_bridge import ExternalBridgeStorageService
from backend.app.storage.types import ExternalBridgeStorageConfig, StorageOperationError


@pytest.mark.parametrize("seconds", [0, -1, inf, -inf, nan, True, None])
def test_bridge_rejects_unbounded_or_invalid_timeout(seconds):
    with pytest.raises(StorageOperationError, match="finite and positive"):
        ExternalBridgeStorageService(
            ExternalBridgeStorageConfig(
                base_url="https://storage.invalid",
                request_timeout_seconds=seconds,
            )
        )


@pytest.mark.parametrize("seconds", [30.0, 2.5])
def test_bridge_http_request_uses_bounded_timeout(seconds):
    storage = ExternalBridgeStorageService(
        ExternalBridgeStorageConfig(
            base_url="https://storage.invalid",
            request_timeout_seconds=seconds,
        )
    )
    with patch(
        "backend.app.storage.external_bridge.urllib_request.urlopen",
        return_value=BytesIO(b"%PDF-1.7\\n%%EOF\\n"),
    ) as opener:
        with storage.read_stream("2026/decision.pdf") as response:
            assert response.read(5) == b"%PDF-"
        assert opener.call_count == 1
        assert opener.call_args.kwargs == {"timeout": seconds}


def test_bridge_socket_timeout_fails_closed_without_retry():
    storage = ExternalBridgeStorageService(
        ExternalBridgeStorageConfig(base_url="https://storage.invalid")
    )
    with patch(
        "backend.app.storage.external_bridge.urllib_request.urlopen",
        side_effect=TimeoutError("socket timed out"),
    ) as opener:
        with pytest.raises(StorageOperationError, match="timed out"):
            with storage.read_stream("2026/decision.pdf") as response:
                response.read()
        assert opener.call_count == 1
