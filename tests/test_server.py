import json
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import MagicMock

import pytest

from print_server.server import LabelServer


@pytest.fixture
def server():
    # Mock printer
    printer = MagicMock()
    # Bind to port 0 to let OS choose a free port
    server = LabelServer(("127.0.0.1", 0), printer)
    server.start()

    # Get the actual port
    host, port = server._httpd.server_address
    base_url = f"http://{host}:{port}"

    yield base_url, server

    server.shutdown()


def send_post(base_url, data_dict):
    data_json = json.dumps(data_dict)
    # The server expects 'data' in the query string of the body
    # (x-www-form-urlencoded style somewhat)
    # wait, looking at code: query = parse_qs(body) ...
    # data = json.loads(query["data"][0])
    # So the body should be `data=<json_string>`

    body = urllib.parse.urlencode({"data": data_json}).encode("utf-8")
    req = urllib.request.Request(base_url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_valid_post(server):
    base_url, _ = server
    payload = {
        "package_id": "PKG123",
        "inmate_id": "12345",
        "inmate_name": "John Doe",
        "inmate_jurisdiction": "County",
        "unit_name": "Block A",
        "unit_shipping_method": "Truck",
    }
    status, _ = send_post(base_url, payload)
    assert status == 200


def test_missing_keys(server):
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


def test_invalid_type(server):
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


def test_field_too_long(server):
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


def test_payload_too_large(server):
    base_url, _ = server
    # 2MB of data
    large_data = "A" * (2 * 1024 * 1024)
    # Just construct a raw body that is too large
    req = urllib.request.Request(
        base_url, data=large_data.encode("utf-8"), method="POST"
    )
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
    except urllib.error.HTTPError as e:
        status = e.code

    assert status == 413


def test_invalid_content_length(server):
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


def test_negative_content_length(server):
    base_url, _ = server

    req = urllib.request.Request(base_url, method="POST")

    req.add_header("Content-Length", "-1")

    try:
        with urllib.request.urlopen(req) as response:
            status = response.status

    except urllib.error.HTTPError as e:
        status = e.code

    assert status == 400
