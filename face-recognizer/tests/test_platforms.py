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
