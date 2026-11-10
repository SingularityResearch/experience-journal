"""
photofiles.py - photo files as the labeling engine sees them: content hashes, picture fingerprints (for
duplicates), online-only cloud files (Windows attributes; made local while read, then unpinned), camera dates,
and the photo folders that have been added (data/settings.json). Split out of labels.py; `labels` re-exports it.
"""
import hashlib
import os
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

import face_id as F


# --------------------------------------------------------------------------- photo fingerprints
def file_hash(path):
    """SHA-1 of the file's bytes: the same photo copied or renamed gets the same key."""
    h, n = hashlib.sha1(), 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    if n != os.stat(path).st_size:            # e.g. an online-only cloud file that wasn't all downloaded
        raise OSError(f"read only {n:,} of {os.stat(path).st_size:,} bytes of {Path(path).name}")
    return h.hexdigest()


CLOUD = 0x400000 | 0x1000                     # Windows file attributes: data still in the cloud (online-only)




def needs_possible(p):
    """True if photo record p hasn't been looked at for possible faces yet (videos aren't: too slow)."""
    return bool(p.get("path")) and not p.get("video") and not p.get("dup_of") and "maybe" not in p


def online_only(path):
    try:
        return bool(os.stat(path).st_file_attributes & CLOUD)
    except (OSError, AttributeError):         # AttributeError: not Windows
        return False


def make_local(path):
    """Download an online-only file (iCloud Photos, OneDrive) all the way. Read straight through, such
    a file can come back cut short (seen with iCloud: 190 KB of a 442 KB video, then end of file), so it's
    pinned ("Always keep on this device") and waited for, allowing at least 0.5 MB/s (iCloud for Windows
    managed about 1 video a minute on 2026-11-08).
    Returns True if this pinned it (unpin() it when done), False if it was already here.
    Raises OSError if it didn't arrive in time."""
    if not online_only(path):
        return False
    subprocess.run(["attrib", "+P", "-U", str(path)], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    end = time.time() + 300 + os.stat(path).st_size / 5e5
    while online_only(path):
        if time.time() > end:
            raise OSError(f"{Path(path).name} didn't finish downloading from the cloud")
        time.sleep(1)
    return True


def unpin(paths):
    """Undo make_local's pin: the files stay here, and the cloud app may free their space again later."""
    for p in paths:
        subprocess.run(["attrib", "-P", str(p)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def fingerprint(bgr):
    """256-bit picture fingerprint (difference hash). Re-saved, resized or re-compressed copies of a
    photo differ in a few bits; different photos differ in roughly half of them."""
    g = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (17, 16), interpolation=cv2.INTER_AREA)
    return np.packbits((g[:, 1:] > g[:, :-1]).ravel()).tobytes().hex()


def photo_date(path):
    """When the photo was taken (EXIF), else the file's date. '' if unreadable."""
    try:
        from PIL import Image
        if Path(path).suffix.lower() in (".heic", ".heif"):
            import pillow_heif
            pillow_heif.register_heif_opener()
        with Image.open(path) as im:
            ex = im.getexif()
            d = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        if d:
            return f"{d[:4]}-{d[5:7]}-{d[8:10]} {d[11:16]}"
    except Exception:
        pass
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(Path(path).stat().st_mtime))
    except OSError:
        return ""


def settings():
    return F.load_json("settings.json", {"folders": []})


def remember_folder(folder):
    s = settings()
    folder = str(Path(folder))
    if folder not in s["folders"]:
        s["folders"].append(folder)
        F.save_json("settings.json", s)
