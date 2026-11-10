"""What differs between Windows, macOS and Linux (paths.user_data, desktop.py), checked for all three on any one:
where each system keeps a user's application data, and how a folder is shown."""
from pathlib import Path

import desktop
import paths


def test_each_system_keeps_application_data_where_it_expects():
    home = Path("/home/ann")
    assert paths.user_data("FaceLabels", "win32", {"APPDATA": r"C:\Users\Ann\AppData\Roaming"}, home) == \
        Path(r"C:\Users\Ann\AppData\Roaming") / "FaceLabels"
    assert paths.user_data("FaceLabels", "darwin", {}, home) == home / "Library" / "Application Support" / "FaceLabels"
    assert paths.user_data("FaceLabels", "linux", {}, home) == home / ".local" / "share" / "FaceLabels"
    assert paths.user_data("FaceLabels", "linux", {"XDG_DATA_HOME": "/data/ann"}, home) == Path("/data/ann/FaceLabels")


def test_folders_open_in_each_systems_file_manager():
    ran = []
    desktop.open_folder("/tmp/x", "darwin", ran.append)
    desktop.open_folder("/tmp/x", "linux", ran.append)
    assert ran == [["open", "/tmp/x"], ["xdg-open", "/tmp/x"]]


def test_attention_never_raises_where_the_window_cant_do_it():
    class NoWindow:
        native = None
    for platform in ("win32", "darwin", "linux"):
        desktop.attention(NoWindow(), platform)          # prints why, doesn't raise


def test_the_window_is_tried_in_a_child_process_on_linux_only(monkeypatch):
    import subprocess
    import types

    import app
    ran = []

    def fake_run(cmd, **kw):
        ran.append(cmd)
        return types.SimpleNamespace(returncode=ran_code[0], stderr=b"Could not initialize GLX")
    monkeypatch.setattr(subprocess, "run", fake_run)
    ran_code = [3]                                   # the child aborted or never showed the page
    monkeypatch.setattr(app.sys, "platform", "linux")
    assert app.window_works() is False and ran[-1][-1] == "--probe-window"
    ran_code[0] = 0
    assert app.window_works() is True
    monkeypatch.setattr(app.sys, "platform", "darwin")
    n = len(ran)
    assert app.window_works() is True and len(ran) == n      # macOS and Windows: not tried, always their web view


def test_the_linux_build_leaves_graphics_libraries_to_the_system(tmp_path):
    import build_exe
    names = ["libgbm.so.1", "libX11.so.6", "libGLX_mesa.so.0", "libwayland-client.so.0",      # the system's own
             "libdrm-b0291a67.so.2.4.0", "libX11-xcb-b482bfde.so.1.0.0", "libQt6Core.so.6", "libglib-2.0.so.0"]
    for n in names:
        (tmp_path / n).write_bytes(b"")
    gone = build_exe.drop_system_libs(tmp_path)
    assert sorted(gone) == sorted(names[:4])
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(names[4:])   # private copies and Qt stay
