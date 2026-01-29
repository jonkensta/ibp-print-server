import json
import logging
import threading
import http.server
from queue import Queue
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

class LabelServer(object):

    def __init__(self, address):
        self._address = address
        self._queue = Queue()
        self._httpd = http.server.HTTPServer(address, self._create_handler())
        self._thread = threading.Thread(target=self._httpd.serve_forever)
        self._thread.daemon = True # Daemon thread exits when main thread exits

    def _create_handler(self):
        queue = self._queue
        # We need to access the queue inside the handler, but Handler is instantiated per request.
        # So we create a closure or subclass with reference.
        
        class Handler(http.server.BaseHTTPRequestHandler):

            def do_OPTIONS(self):
                self.send_response(200, 'ok')
                self.send_header('Access-Control-Allow-Origin', 'http://ibp-server.local')
                # Also allow https variant if needed, but Access-Control-Allow-Origin only takes one URI or *.
                # If we need multiple, we check Origin header and echo it if matches.
                # For now, plan said "http://ibp-server.local (and https://)".
                # Let's implement dynamic check.
                
                origin = self.headers.get('Origin')
                allowed_origins = {'http://ibp-server.local', 'https://ibp-server.local'}
                if origin in allowed_origins:
                     self.send_header('Access-Control-Allow-Origin', origin)
                
                self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()

            def _get_post_data(self):
                try:
                    content_length = int(self.headers['Content-Length'])
                    return self.rfile.read(content_length).decode('utf-8')
                except (ValueError, KeyError) as e:
                    logger.error(f"Error reading POST data: {e}")
                    raise

            def do_GET(self):
                if self.path == '/health':
                     self.send_response(200)
                     self.send_header('Content-type', 'application/json')
                     # CORS for GET too
                     origin = self.headers.get('Origin')
                     allowed_origins = {'http://ibp-server.local', 'https://ibp-server.local'}
                     if origin in allowed_origins:
                        self.send_header('Access-Control-Allow-Origin', origin)
                     self.end_headers()
                     
                     # Simple health status
                     status = {"status": "ok", "service": "print-server"}
                     self.wfile.write(json.dumps(status).encode('utf-8'))
                else:
                    self.send_error(404)

            def do_POST(self):
                try:
                    body = self._get_post_data()
                    # The original code expected data in a form field 'data'
                    # "query = parse_qs(self._get_post_data(), keep_blank_values=1)"
                    # "data = json.loads(query['data'][0])"
                    
                    query = parse_qs(body, keep_blank_values=1)
                    if 'data' not in query:
                         logger.warning("POST request missing 'data' field")
                         self.send_error(400, "Missing 'data' field")
                         return

                    try:
                        data = json.loads(query['data'][0])
                        logger.info("Received print job via POST")
                        queue.put(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        self.send_error(400, "Invalid JSON")
                        return

                    self.send_response(200)
                    self.send_header("Content-type", "text/xml")
                    
                    origin = self.headers.get('Origin')
                    allowed_origins = {'http://ibp-server.local', 'https://ibp-server.local'}
                    if origin in allowed_origins:
                        self.send_header('Access-Control-Allow-Origin', origin)
                        
                    self.end_headers()
                except Exception as e:
                    logger.exception("Unexpected error in do_POST")
                    self.send_error(500)

        return Handler

    def start(self):
        logger.info(f"Starting server on {self._address}")
        self._thread.start()

    def get_job(self):
        # Blocking get
        return self._queue.get()

    def shutdown(self):
        logger.info("Shutting down server...")
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join()
