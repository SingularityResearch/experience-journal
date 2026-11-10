r"""
paths.py - where the programs keep things, and the one way they write files.

  ROOT  the folder with models\ and data\: beside the source files, or beside FaceRecognizer.exe when built
        (the .exe carries only the code and pages and shares this folder's models and data with the .bat
        launchers). FACE_ROOT=<folder> uses another one (tests, a second copy).
  HOME  %APPDATA%\FaceLabels: what is private to this computer's user and never belongs in the project
        (Web search keys, describe settings and descriptions, webcam snapshots, presence log, the app window's
        storage, app.log). FACE_HOME=<folder> uses another one (tests).

Nothing here imports the rest of the project, so every module (and the tests) can use it.
"""
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ["FACE_ROOT"]).resolve() if os.environ.get("FACE_ROOT") else (
    Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else HERE)
HOME = Path(os.environ["FACE_HOME"]).resolve() if os.environ.get("FACE_HOME") else (
    Path(os.environ.get("APPDATA", Path.home())) / "FaceLabels")


def replace_file(tmp, dest, tries=20):
    """os.replace, retrying briefly: on Windows it fails while another program (or thread) is reading dest."""
    for k in range(tries):
        try:
            return os.replace(tmp, dest)
        except PermissionError:
            if k == tries - 1:
                raise
            time.sleep(0.05)


def atomic_write(path, data):
    """Write text or bytes to path without ever leaving a half-written file: into path.tmp, then replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if isinstance(data, str):
        tmp.write_text(data, "utf-8")
    else:
        tmp.write_bytes(data)
    replace_file(tmp, path)
