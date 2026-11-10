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
from urllib.parse import urlparse

import localguard
import paths

TITLE = "Face Recognizer"
VERSION = "1.7"                                    # this build; GitHub release tags are "v" + VERSION
REPO = "SingularityResearch/facial-recognition"
HOME = paths.HOME                                  # %APPDATA%\FaceLabels: private, outside the project

HERE = paths.HERE                                  # the page files (inside the .exe when built)
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


def start(name, module, port, app):
    """Start one program's server in this process on the first free port from `port`, or use the copy
    already running there. Returns its URL once it answers (models loaded)."""
    for p in range(port, port + 10):
        url = f"http://127.0.0.1:{p}/"
        try:
            srv = module.bind(p) if hasattr(module, "bind") else bind(p)
        except OSError:
            if answering(url, app):
                print(f"{name}: using the copy already running at {url}")
                return url
            continue
        print(f"{name}: loading ...")
        module.attach(srv)
        threading.Thread(target=srv.serve_forever, daemon=True, name=name).start()
        print(f"{name}: serving at {url}")
        return url
    raise OSError(f"No free port between {port} and {port + 9}")


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


def shell_server():
    """The tab page itself, on 127.0.0.1 (an http://127.0.0.1 page counts as secure, which the camera
    needs; so must the page around the tracker's frame). The same request checks as the two programs
    (localguard): the right Host; and for anything that does something (contacts GitHub, opens a
    browser or a folder) the X-Face-Tool header, which only this page sends."""
    acts = ("/update", "/open-release", "/open")

    class Handler(localguard.Handler):
        frame_ancestors = "'none'"                       # the window's own page: never inside another page

        def _get(self):
            path = self.path.split("?", 1)[0]
            if self.refused(write=path in acts):
                return
            if path in PAGES:
                file, ctype = PAGES[path]
                return self.send(file.read_text("utf-8").replace("{{VERSION}}", VERSION).encode(), ctype)
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

    try:
        srv = bind(8764)                            # fixed, so the page's remembered tab survives restarts
    except OSError:
        srv = bind(0)                               # taken (a second copy?): any free port
    srv.RequestHandlerClass = Handler
    port = srv.server_address[1]
    localguard.FRAME_PARENTS.update({f"http://127.0.0.1:{port}", f"http://localhost:{port}"})   # may frame the programs
    threading.Thread(target=srv.serve_forever, daemon=True, name="shell").start()
    return f"http://127.0.0.1:{srv.server_address[1]}/"


def allow_camera(window):
    """Let this window's own local pages use the camera and microphone without asking each time
    (WebView2 asks by default). Pages from anywhere else still get WebView2's prompt."""
    if getattr(window, "_camera_ok", False):
        return
    window._camera_ok = True
    try:
        from System import Action
        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind as Kind, CoreWebView2PermissionState as State

        def on_request(_, e):
            if urlparse(e.Uri).hostname == "127.0.0.1" and e.PermissionKind in (Kind.Camera, Kind.Microphone):
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
        jobs = [("track", "Face tracker", tracker, 8766, "tracker"),
                ("label", "Face Labels", label_tool, 8765, "face-labels")]
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
    run_programs()
    window = webview.create_window(TITLE, shell_server(), width=1440, height=920, min_size=(900, 600),
                                   background_color="#0d1512")
    window.events.loaded += lambda: allow_camera(window)
    # private_mode=False keeps each page's remembered options and per-person baselines between runs
    webview.start(private_mode=False, storage_path=str(HOME / "webview"))
    os._exit(0)                                     # window closed: stop both servers and background readers


if __name__ == "__main__":
    main()
