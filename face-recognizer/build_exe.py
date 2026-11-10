"""
build_exe.py - builds FaceRecognizer.exe (app.py: the tracker and the labeling tool in one window) with PyInstaller.
The one place the build is described: build_app.bat runs it on this computer, and CI runs it on GitHub's Windows
machines (.github/workflows/checks.yml), so both make the same .exe.

    python build_exe.py            -> build\\dist\\FaceRecognizer.exe, copied beside this file
    python build_exe.py --no-copy  -> build\\dist\\FaceRecognizer.exe only (CI)

The .exe carries the code and the pages only; it uses the models\\ and data\\ folders beside it (or FACE_ROOT).
Needs requirements-build.txt installed.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Every page file the three servers send: packed into the .exe (a test checks each page's scripts are listed here)
PAGES = ["tracker_ui.html", "label_ui.html", "app_ui.html", "tracker_ui.js", "label_ui.js", "app_ui.js",
         "expression.js", "signals.js", "settings_bridge.js"]
EXCLUDE = ["torch", "torchvision", "torchaudio", "torchgen", "tensorflow", "pandas", "IPython"]


def command():
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", "FaceRecognizer", "--workpath", "build", "--distpath", str(Path("build") / "dist"),
           "--specpath", "build"]
    for f in PAGES:
        cmd += ["--add-data", f"{HERE / f}{sep}."]
    cmd += ["--collect-all", "mediapipe", "--collect-all", "onnxruntime", "--collect-submodules", "webview",
            "--hidden-import", "sklearn.cluster"]
    for m in EXCLUDE:
        cmd += ["--exclude-module", m]
    return cmd + ["app.py"]


def main():
    ap = argparse.ArgumentParser(description="Build FaceRecognizer.exe")
    ap.add_argument("--no-copy", action="store_true", help="leave it in build\\dist (don't copy it beside this file)")
    args = ap.parse_args()
    missing = [f for f in PAGES if not (HERE / f).exists()]
    if missing:
        sys.exit(f"Missing page files: {', '.join(missing)}")
    subprocess.run(command(), cwd=HERE, check=True)
    exe = HERE / "build" / "dist" / ("FaceRecognizer.exe" if sys.platform == "win32" else "FaceRecognizer")
    if not exe.exists():
        sys.exit(f"PyInstaller finished but {exe} isn't there")
    if not args.no_copy:
        shutil.copy2(exe, HERE / exe.name)
    print(f"Built {exe}{'' if args.no_copy else ' (and copied beside build_exe.py)'}")


if __name__ == "__main__":
    main()
