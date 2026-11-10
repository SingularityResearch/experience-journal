"""
localguard.py - keep other websites out of the local tools' web servers.

label_tool.py and tracker.py serve pages on 127.0.0.1. Without a check, any website open
in your browser could send them requests (for example, a hidden form that overwrites your
labels), or use "DNS rebinding" to read their answers. Every request must therefore:

  * name this computer in its Host header (127.0.0.1 or localhost, with the right port), which
    defeats DNS rebinding, and
  * for anything that changes or computes something (POST): carry the custom header
    X-Face-Tool: 1 and, if the browser sends an Origin, come from this tool's own page.
    Browsers won't let another website add a custom header without the server's permission
    (a CORS preflight these servers never grant), so only the tool's own pages can do it.
"""

import http.server
import sys
import traceback

HEADER = "X-Face-Tool"

# Pages may be shown in a frame only by themselves and by the app window's tab page (app.py), normally on
# 127.0.0.1:8764; app.py adds its real address when that port was taken. Any other site, or another local
# program, framing a page could trick clicks on it, or pose as the Settings tab (settings_bridge.js).
FRAME_PARENTS = {"http://127.0.0.1:8764", "http://localhost:8764"}


def page_headers(handler):
    """Headers every answer gets: who may frame it, and no content sniffing."""
    handler.send_header("Content-Security-Policy", "frame-ancestors 'self' " + " ".join(sorted(FRAME_PARENTS)))
    handler.send_header("X-Content-Type-Options", "nosniff")


class _Server(http.server.ThreadingHTTPServer):
    # Windows lets a second program bind a port that's already in use when SO_REUSEADDR is set (Python's HTTP
    # server sets it), and the old program keeps getting the connections. Without it the bind fails as it
    # should, and the caller's "already running" branch is taken.
    allow_reuse_address = sys.platform != "win32"


def bind(port):
    """A web server socket on 127.0.0.1:port, not serving yet. OSError when the port is taken."""
    return _Server(("127.0.0.1", port), http.server.BaseHTTPRequestHandler)


def answer_errors(handler, run, send_error):
    """Run one request; a mistake no route caught still gets an answer (500 with the error), not a dropped
    connection, and is written to the log."""
    try:
        run()
    except (BrokenPipeError, ConnectionResetError):
        pass
    except Exception as e:
        traceback.print_exc()
        try:
            send_error({"error": f"{type(e).__name__}: {e}"}, 500)
        except OSError:
            pass


def refuse_reason(headers, port, write):
    """Return why a request must be refused, or None if it may proceed."""
    local = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if headers.get("Host", "") not in local:
        return "This tool only answers requests addressed to 127.0.0.1."
    if write:
        if headers.get(HEADER) != "1":
            return f"Missing the {HEADER} header; requests must come from the tool's own page."
        origin = headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in local}:
            return "Requests from other websites are not allowed."
    return None
