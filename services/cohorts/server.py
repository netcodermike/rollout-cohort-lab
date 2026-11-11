import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from domain import operation
from errors import Rejected


def upstream(payload):
    request = Request(os.environ["UPSTREAM_URL"], json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=2.5) as response:
            return json.load(response)
    except HTTPError as error:
        with error:
            if error.code in (400, 409, 422):
                raise Rejected(error.code, json.load(error)["error"]) from error
        raise Rejected(502, "Dependency failed") from error
    except (URLError, TimeoutError) as error:
        raise Rejected(502, "Dependency unavailable") from error


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        data = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "up"})
        else:
            self.reply(404, {"error": "Unknown route"})

    def do_POST(self):
        if self.path != os.environ["OPERATION_PATH"]:
            self.reply(404, {"error": "Unknown route"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                self.reply(413 if length > 65536 else 400, {"error": "Invalid body length"})
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            self.reply(200, operation(payload, upstream))
        except Rejected as error:
            self.reply(error.status, {"error": str(error)})
        except (KeyError, TypeError, ValueError) as error:
            self.reply(400, {"error": f"Invalid input: {error}"})
        except Exception:
            self.log_error("Unexpected service error")
            self.reply(500, {"error": "Service failed"})


if __name__ == "__main__":
    ThreadingHTTPServer((os.getenv("HOST", "127.0.0.1"), int(os.environ["PORT"])),
                        Handler).serve_forever()
