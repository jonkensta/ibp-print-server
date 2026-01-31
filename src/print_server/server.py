import http.server
import json
import logging
import threading
from queue import Queue
from typing import Any
from urllib.parse import parse_qs

# Import Printer for type hinting
from .printer import Printer

logger = logging.getLogger(__name__)

REQUIRED_KEYS = {
    "package_id",
    "inmate_id",
    "inmate_name",
    "inmate_jurisdiction",
    "unit_name",
    "unit_shipping_method",
}
MAX_FIELD_LENGTH = 10000
MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB


class PayloadTooLargeError(Exception):
    """Raised when the payload exceeds the maximum allowed size."""
    pass


class LabelServer:
    def __init__(self, address: tuple[str, int], printer: Printer) -> None:
        self._address = address
        self._printer = printer
        self._queue: Queue[dict[str, Any]] = Queue()
        self._httpd = http.server.HTTPServer(address, self._create_handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever)
        self._thread.daemon = True

    def _create_handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        queue = self._queue
        printer = self._printer

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(200, "ok")
                self._send_cors_headers()
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def _get_post_data(self) -> str:
                try:
                    content_length = int(self.headers["Content-Length"])
                except (ValueError, KeyError) as e:
                    logger.error(f"Invalid Content-Length: {e}")
                    raise ValueError("Invalid Content-Length header") from e

                if content_length > MAX_PAYLOAD_SIZE:
                    raise PayloadTooLargeError(
                        f"Payload too large: {content_length} bytes"
                    )

                return self.rfile.read(content_length).decode("utf-8")

            def _send_cors_headers(self) -> None:
                origin = self.headers.get("Origin")
                allowed_origins = {
                    "http://ibp-server.local",
                    "https://ibp-server.local",
                }
                if origin in allowed_origins:
                    self.send_header("Access-Control-Allow-Origin", origin)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()

                    # Get printer status using shared printer instance
                    try:
                        printers = printer.get_available_printers()
                        status = {
                            "status": "ok",
                            "service": "print-server",
                            "printers": {
                                "count": len(printers),
                                "names": printers,
                            },
                        }
                    except Exception as e:
                        logger.error(f"Health check failed to get printers: {e}")
                        status = {
                            "status": "degraded",
                            "service": "print-server",
                            "error": str(e),
                        }

                    self.wfile.write(json.dumps(status).encode("utf-8"))
                else:
                    self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    try:
                        body = self._get_post_data()
                    except PayloadTooLargeError as e:
                        self.send_error(413, str(e))
                        return
                    except ValueError as e:
                        self.send_error(400, str(e))
                        return

                    query = parse_qs(body, keep_blank_values=True)

                    if "data" not in query:
                        logger.warning("POST request missing 'data' field")
                        self.send_error(400, "Missing 'data' field")
                        return

                    try:
                        data = json.loads(query["data"][0])
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        self.send_error(400, "Invalid JSON")
                        return

                    if not isinstance(data, dict):
                        self.send_error(400, "Payload must be a JSON object")
                        return

                    missing_keys = REQUIRED_KEYS - data.keys()
                    if missing_keys:
                        missing_list = ", ".join(sorted(missing_keys))
                        msg = f"Missing required keys: {missing_list}"
                        logger.warning(msg)
                        self.send_error(400, msg)
                        return

                    for key in REQUIRED_KEYS:
                        val = data[key]
                        if not isinstance(val, str):
                            self.send_error(400, f"Field '{key}' must be a string")
                            return
                        if len(val) > MAX_FIELD_LENGTH:
                            self.send_error(400, f"Field '{key}' is too long")
                            return

                    logger.info("Received print job via POST")
                    queue.put(data)

                    self.send_response(200)
                    self.send_header("Content-type", "text/xml")
                    self._send_cors_headers()
                    self.end_headers()
                except Exception:
                    logger.exception("Unexpected error in do_POST")
                    self.send_error(500)

        return Handler

    def start(self) -> None:
        logger.info(f"Starting server on {self._address}")
        self._thread.start()

    def get_job(self) -> dict[str, Any]:
        return self._queue.get()

    def shutdown(self) -> None:
        logger.info("Shutting down server...")
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()
