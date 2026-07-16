"""Shared test fixtures and environment mocks."""

import sys
import types
from unittest.mock import MagicMock

# Mock curl_cffi for environments where it cannot be installed (e.g., Android/Termux).
# The real HTTP request is patched per test as needed.
if "curl_cffi" not in sys.modules:
    curl_cffi = types.ModuleType("curl_cffi")
    requests = types.ModuleType("curl_cffi.requests")
    response_mock = MagicMock()
    response_mock.status_code = 200
    response_mock.text = ""
    response_mock.content = b""
    response_mock.headers = {}

    def fake_get(url, **kwargs):
        return response_mock

    requests.get = fake_get
    curl_cffi.requests = requests
    sys.modules["curl_cffi"] = curl_cffi
    sys.modules["curl_cffi.requests"] = requests
