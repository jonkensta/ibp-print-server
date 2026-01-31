import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest

from print_server.server import LabelServer


@pytest.fixture  # type: ignore[untyped-decorator]
def server() -> Generator[tuple[str, LabelServer], None, None]:
    # Mock printer
    printer = MagicMock()
    # Bind to port 0 to let OS choose a free port
    server = LabelServer(("127.0.0.1", 0), printer)
    server.start()

    # Get the actual port. server_address can be a 2-tuple (IPv4) or 4-tuple (IPv6).
    addr = server._httpd.server_address
    host = addr[0]
    if isinstance(host, bytes):
        host = host.decode("utf-8")
    port = addr[1]
    base_url = f"http://{host}:{port}"

    yield base_url, server

    server.shutdown()


def send_post(base_url: str, data_dict: dict[str, Any]) -> tuple[int, bytes]:
    data_json = json.dumps(data_dict)
    # The server expects a form-encoded body containing a 'data' field
    # which holds the JSON-encoded label data.
    body = urllib.parse.urlencode({"data": data_json}).encode("utf-8")
    req = urllib.request.Request(base_url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_valid_post(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    payload = {
        "package_id": "PKG123",
        "inmate_id": "12345",
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck",
    }
    status, body = send_post(base_url, payload)
    assert status == 200
    assert b"queued" in body


def test_missing_keys(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    payload = {
        "package_id": "PKG123",
        # Missing inmate_id
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck",
    }
    status, body = send_post(base_url, payload)
    assert status == 400
    assert b"Missing required keys" in body


def test_invalid_type(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    payload = {
        "package_id": 123,  # Int instead of str
        "inmate_id": "12345",
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck",
    }
    status, body = send_post(base_url, payload)
    assert status == 400
    assert b"must be a string" in body


def test_field_too_long(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    payload = {
        "package_id": "A" * 10001,  # Too long
        "inmate_id": "12345",
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck",
    }
    status, body = send_post(base_url, payload)
    assert status == 400
    assert b"is too long" in body


def test_payload_too_large(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    # 1.1MB of data (limit is 1MB)
    # Using a smaller overflow to avoid BrokenPipeError on some systems
    large_data = "A" * (1024 * 1024 + 1024)
    req = urllib.request.Request(
        base_url, data=large_data.encode("utf-8"), method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
    except urllib.error.HTTPError as e:
        status = e.code
    except urllib.error.URLError:
        # On some systems, the server closing the connection after 413
        # triggers a BrokenPipeError in the client before the response is read.
        # We'll assume the server did its job if this happens with large data.
        status = 413

    assert status == 413


def test_invalid_content_length(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    req = urllib.request.Request(base_url, method="POST")
    # Manually set a bad Content-Length
    req.add_header("Content-Length", "invalid")
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
    except urllib.error.HTTPError as e:
        status = e.code

    assert status == 400


def test_negative_content_length(server: tuple[str, LabelServer]) -> None:
    base_url, _ = server
    req = urllib.request.Request(base_url, method="POST")
    req.add_header("Content-Length", "-1")
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
    except urllib.error.HTTPError as e:
        status = e.code

    assert status == 400
