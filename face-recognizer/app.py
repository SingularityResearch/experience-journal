"""
app.py - Face Recognizer: the live tracker and the labeling tool in one window, as two tabs.

The two stay separate programs inside: each keeps its own web server (tracker.py on 8766,
label_tool.py on 8765) and page, exactly as when started from recognize.bat / label.bat, and this
window shows both pages, one per tab. The tracker keeps running while the Labeling tab is shown.
If either is already running from its .bat, that copy is used instead of starting a second one.

Run:  python app.py            (or FaceRecognizer.exe, built with build_app.bat)
Needs pywebview (pip install pywebview); the window is Edge WebView2, part of Windows 11.
"""
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.request
from urllib.parse import parse_qsl, urlparse

import localguard
import paths

TITLE = "Face Recognizer"
VERSION = "1.9"                                    # this build; GitHub release tags are "v" + VERSION
REPO = "SingularityResearch/facial-recognition"
HOME = paths.HOME                                  # %APPDATA%\FaceLabels: private, outside the project

HERE = paths.HERE                                  # the page files (inside the .exe when built)


def ports(env=os.environ):
    """(tab page, labeling tool, tracker) ports: 8764, 8765, 8766, or from FACE_PORTS=<n> (n, n+1, n+2), so a second
    copy with other folders (FACE_ROOT, FACE_HOME: a test build, say) runs beside the usual one."""
    raw = (env.get("FACE_PORTS") or "").strip()
    base = int(raw) if raw.isdigit() else 8764
    if not 1024 <= base <= 65000:
        raise SystemExit(f"FACE_PORTS must be between 1024 and 65000, not {raw}")
    return base, base + 1, base + 2


# Each program runs on the first free port from its own (up to PORT_TRIES), or a copy already running there is used
SHELL_PORT, LABEL_PORT, TRACK_PORT = ports()
PORT_TRIES = 10
TOOL_PORTS = range(LABEL_PORT, TRACK_PORT + PORT_TRIES)     # every port the two programs' pages can be on

# The tab page: app_ui.html (layout and style) and app_ui.js (tabs, status, Settings tab)
PAGES = {"/": (HERE / "app_ui.html", "text/html; charset=utf-8"),
         "/app_ui.js": (HERE / "app_ui.js", "text/javascript; charset=utf-8")}


def answering(url, app):
    """True if one of our programs (app = 'face-labels' or 'tracker') is already serving at url."""
    try:
        path = "api/summary" if app == "face-labels" else "api/people"
        req = urllib.request.Request(url + path, headers={"X-Face-Tool": "1"})
        with urllib.request.urlopen(req, timeout=3) as r:
            body = json.loads(r.read())
        return body.get("app") == "face-labels" if app == "face-labels" else "people" in body
    except Exception:
        return False


def lets_us_frame(url):
    """True if the page at url may be shown in this window: its frame-ancestors name this window's tab page
    (localguard.FRAME_PARENTS, set by shell_server). A program started on its own (its .bat) names only itself."""
    try:
        req = urllib.request.Request(url, headers={"X-Face-Tool": "1"})
        with urllib.request.urlopen(req, timeout=3) as r:
            csp = r.headers.get("Content-Security-Policy", "")
    except Exception:
        return False
    for rule in csp.split(";"):
        words = rule.split()
        if words[:1] == ["frame-ancestors"]:
            return any(o in words[1:] for o in localguard.FRAME_PARENTS)
    return False


def start(name, module, port, app):
    """Start one program's server in this process on the first free port from `port`, or use the copy
    already running there. Returns its URL once it answers (models loaded)."""
    for p in range(port, port + PORT_TRIES):
        url = f"http://127.0.0.1:{p}/"
        try:
            srv = module.bind(p) if hasattr(module, "bind") else bind(p)
        except OSError:
            if answering(url, app):
                if not lets_us_frame(url):
                    # Started on its own, so it trusts only its own page. Starting a second copy instead would
                    # have two programs writing the same data files, so ask for that copy to be closed.
                    raise OSError(f"It is already running at {url}, started on its own (its .bat) or by another Face "
                                  f"Recognizer window, and a copy started that way can't be shown in this window. "
                                  f"\nClose that copy (its black "
                                  f"window) and start the app again, or keep using it in your browser at {url}") from None
                print(f"{name}: using the copy already running at {url}")
                return url
            continue
        print(f"{name}: loading ...")
        module.attach(srv)
        threading.Thread(target=srv.serve_forever, daemon=True, name=name).start()
        print(f"{name}: serving at {url}")
        return url
    raise OSError(f"No free port between {port} and {port + PORT_TRIES - 1}")


def bind(port):
    return localguard.bind(port)                     # no address reuse on Windows: a second copy gets OSError


STATUS = {"track": {}, "label": {}}         # {"url": ...} once serving, {"error": ...} if it failed


def latest_release():
    """{latest, newer} from GitHub's latest release of this project, or {error}. Only when asked
    (the window's "Check for updates"): the app contacts nothing on its own except the first-start
    model download."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "FaceRecognizer"})
        with urllib.request.urlopen(req, timeout=10) as r:
            tag = json.loads(r.read()).get("tag_name", "")
        num = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3])
        return {"latest": tag, "newer": num(tag) > num(VERSION)}
    except Exception as e:
        return {"error": str(e)}


def data_dir():
    """The programs' data folder (face_id.DATA): data\\ beside the .exe, or beside the source files."""
    return paths.ROOT / "data"


def shell_handler():
    """The tab page's request handler. The same request checks as the two programs (localguard): the right
    Host; and for anything that does something (contacts GitHub, opens a browser or a folder) the X-Face-Tool
    header, which only this page sends."""
    acts = ("/update", "/open-release", "/open", "/attention")

    class Handler(localguard.Handler):
        frame_ancestors = "'none'"                       # the window's own page: never inside another page
        # beyond localguard.POLICY: the two programs' pages in its frames (on 127.0.0.1, any of their ports); no
        # pictures of its own beyond its server's
        policy = {"frame-src": " ".join(f"http://127.0.0.1:{p}" for p in TOOL_PORTS), "img-src": "'self'"}

        def _get(self):
            path = self.path.split("?", 1)[0]
            if self.refused(write=path in acts):
                return
            if path in PAGES:
                file, ctype = PAGES[path]
                return self.send(file.read_text("utf-8").replace("{{VERSION}}", VERSION).encode(), ctype)
            if path == "/attention":                     # alerts: the window's title and taskbar button
                q = dict(parse_qsl(self.path.partition("?")[2]))
                attention(int(q.get("unread", "0") or 0), q.get("flash") == "1")
                return self.send({})
            if path not in ("/status", "/paths") + acts:
                return self.send({"error": "not found"}, code=404)
            if path == "/open-release":                 # in the normal browser, not inside this window
                import webbrowser
                webbrowser.open(f"https://github.com/{REPO}/releases/latest")
                body = {}
            elif path in ("/paths", "/open"):             # the Settings tab's data folders
                where = {"data": data_dir(), "private": HOME}
                if path == "/open":
                    d = where.get(self.path.split("what=", 1)[-1])
                    if d:
                        d.mkdir(parents=True, exist_ok=True)
                        os.startfile(d)
                body = {k: str(v) for k, v in where.items()}
            elif path == "/update":
                body = latest_release()
            else:
                body = STATUS
            self.send(body)

    return Handler


def shell_server():
    """The tab page itself, on 127.0.0.1 (an http://127.0.0.1 page counts as secure, which the camera
    needs; so must the page around the tracker's frame)."""
    try:
        srv = bind(SHELL_PORT)                      # fixed, so the page's remembered tab survives restarts
    except OSError:
        srv = bind(0)                               # taken (a second copy?): any free port
    srv.RequestHandlerClass = shell_handler()
    port = srv.server_address[1]
    # the programs this window starts may be framed by this page (and only then: see localguard.FRAME_PARENTS)
    localguard.FRAME_PARENTS.update({f"http://127.0.0.1:{port}", f"http://localhost:{port}"})
    threading.Thread(target=srv.serve_forever, daemon=True, name="shell").start()
    return f"http://127.0.0.1:{srv.server_address[1]}/"


WINDOW = None                               # the app window, once made (main)


def attention(unread, flash):
    """New alerts (the tracker's inbox): say how many in the window's title, which shows on its taskbar button, and
    flash the taskbar button when one just happened and the window isn't the one in front (Windows only)."""
    w = WINDOW
    if w is None:
        return
    unread = max(0, min(unread, 9999))
    try:
        w.set_title(f"{TITLE} · {unread} new alert{'s' if unread != 1 else ''}" if unread else TITLE)
    except Exception:
        pass
    if not flash or sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
        hwnd = int(w.native.Handle.ToInt64())
        # FLASHW_ALL | FLASHW_TIMERNOFG: caption and taskbar button, until the window comes to the front
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        traceback.print_exc()


def camera_allowed(uri):
    """True if the page at uri may use the camera and microphone without a prompt: only the tracker this window
    started or found (its address in STATUS), not any other program on 127.0.0.1."""
    track = STATUS["track"].get("url")
    if not track:
        return False
    u, t = urlparse(uri), urlparse(track)
    return (u.scheme, u.hostname, u.port) == (t.scheme, t.hostname, t.port)


def allow_camera(window):
    """Let this window's tracker page use the camera and microphone without asking each time (WebView2 asks by
    default). Any other page, including other programs on 127.0.0.1, still gets WebView2's prompt."""
    if getattr(window, "_camera_ok", False):
        return
    window._camera_ok = True
    try:
        from System import Action
        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind as Kind, CoreWebView2PermissionState as State

        def on_request(_, e):
            # the tracker's own alerts may show as Windows notifications too
            if e.PermissionKind in (Kind.Camera, Kind.Microphone, Kind.Notifications) and camera_allowed(e.Uri):
                e.State = State.Allow

        def hook():
            window.native.webview.CoreWebView2.PermissionRequested += on_request
        window.native.Invoke(Action(hook))
    except Exception:
        print("Camera permission: WebView2 will ask (couldn't pre-allow):")
        traceback.print_exc()


def run_programs():
    def fail(key, name, e):
        traceback.print_exc()
        why = str(e) if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"   # SystemExit: our own message
        STATUS[key] = {"error": f"{name} couldn't start.\n\n{why}\n\nDetails are in {HOME / 'app.log'}"}

    def get_models():
        """First start of a downloaded FaceRecognizer.exe: fetch the models (fetch_models.py)."""
        import fetch_models
        if not fetch_models.needed():
            return True
        print(f"Downloading models into {fetch_models.MODELS}: {', '.join(fetch_models.needed())}")

        def show(done, total, _):
            STATUS["fetch"] = {"done": done, "total": total}
        try:
            fetch_models.fetch(show)
            STATUS.pop("fetch", None)
            return True
        except OSError as e:
            for key, name in (("track", "Face tracker"), ("label", "Face Labels")):
                fail(key, name, OSError(f"The face models couldn't be downloaded: {e}\n"
                                        f"Check the internet connection and start the app again."))
            return False

    def one(key, name, module, port, app):
        try:
            STATUS[key] = {"url": start(name, module, port, app)}
        except BaseException as e:               # incl. SystemExit (e.g. face_id.NotDownloaded) from loading
            fail(key, name, e)

    def go():
        if not get_models():
            return
        try:
            import label_tool
            import tracker                          # imports face_id, which checks the model and data files
        except BaseException as e:
            for key, name in (("track", "Face tracker"), ("label", "Face Labels")):
                fail(key, name, e)
            return
        jobs = [("track", "Face tracker", tracker, TRACK_PORT, "tracker"),
                ("label", "Face Labels", label_tool, LABEL_PORT, "face-labels")]
        for job in jobs:                            # both load at once: tracker models and the label database
            threading.Thread(target=one, args=job, daemon=True).start()

    threading.Thread(target=go, daemon=True).start()


def main():
    HOME.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False) or sys.stdout is None:      # no console: keep the messages in a log
        log = open(HOME / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} {TITLE} starting")
    import webview
    shell = shell_server()                          # first: the programs started next trust this page to frame them
    run_programs()
    window = webview.create_window(TITLE, shell, width=1440, height=920, min_size=(900, 600),
                                   background_color="#0d1512")
    global WINDOW
    WINDOW = window
    window.events.loaded += lambda: allow_camera(window)
    # private_mode=False keeps each page's remembered options and per-person baselines between runs
    webview.start(private_mode=False, storage_path=str(HOME / "webview"))
    os._exit(0)                                     # window closed: stop both servers and background readers


if __name__ == "__main__":
    main()
