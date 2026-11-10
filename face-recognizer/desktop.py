"""
desktop.py - the few things the app asks of the operating system, on Windows, macOS and Linux: show a folder in the
file manager, and draw the user's eye to the app window when an alert comes in (its taskbar button flashes on
Windows, its Dock icon bounces on macOS, its window is marked urgent on Linux). Each does nothing, quietly, where the
system or the window toolkit can't; nothing here is needed for the app to work.
"""
import os
import subprocess
import sys
import traceback


def open_folder(path, platform=sys.platform, run=subprocess.Popen):
    """Show a folder in the system's file manager."""
    path = str(path)
    if platform == "win32":
        os.startfile(path)                                    # noqa: S606 - a folder of ours, not user input
    elif platform == "darwin":
        run(["open", path])
    else:
        run(["xdg-open", path])


def attention(window, platform=sys.platform):
    """Draw the user's eye to the app window (pywebview window): until it's brought to the front where the system
    allows it. Errors are printed, never raised."""
    try:
        if platform == "win32":
            _flash_windows(window)
        elif platform == "darwin":
            from AppKit import NSApp                          # pyobjc, which pywebview's macOS window uses
            NSApp.requestUserAttention_(0)                    # NSCriticalRequest: bounces until the app is active
        else:
            native = getattr(window, "native", None)
            if hasattr(native, "set_urgency_hint"):           # GTK window
                native.set_urgency_hint(True)
            else:                                             # Qt window
                from qtpy.QtWidgets import QApplication
                QApplication.alert(native)
    except Exception:
        traceback.print_exc()


def _flash_windows(window):
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
    hwnd = int(window.native.Handle.ToInt64())
    # FLASHW_ALL | FLASHW_TIMERNOFG: caption and taskbar button, until the window comes to the front
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
