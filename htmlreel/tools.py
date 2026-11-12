"""Locating Chrome, ffmpeg and ffprobe, and running them."""

import os
import shutil
import subprocess
import sys

CHROME_NAMES = [
    "chrome", "google-chrome", "google-chrome-stable", "chromium",
    "chromium-browser", "msedge",
]

CHROME_PLACES = {
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ],
}


class MissingTool(Exception):
    pass


def _find(env_var, names, places):
    override = os.environ.get(env_var)
    if override:
        if not os.path.exists(override) and not shutil.which(override):
            raise MissingTool("%s points at %s, which does not exist."
                              % (env_var, override))
        return override
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for path in places.get(sys.platform, []):
        if os.path.exists(path):
            return path
    raise MissingTool(
        "Could not find %s. Install it, put it on PATH, or set %s to its path."
        % (names[0], env_var))


def chrome():
    """Chrome, Chromium or Edge: any of them renders a page to PNG."""
    return _find("HTMLREEL_CHROME", CHROME_NAMES, CHROME_PLACES)


def ffmpeg():
    return _find("HTMLREEL_FFMPEG", ["ffmpeg"], {})


def ffprobe():
    return _find("HTMLREEL_FFPROBE", ["ffprobe"], {})


def run(command, timeout=None):
    """Run a command and hand back the completed process.

    stderr is captured but never discarded: ffmpeg writes everything there,
    including the output of filters such as silencedetect.
    """
    return subprocess.run(command, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def duration(path):
    """Length of a media file in seconds."""
    result = run([ffprobe(), "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=nw=1:nk=1", path])
    text = result.stdout.strip()
    if not text:
        raise MissingTool("ffprobe could not read %s:\n%s"
                          % (path, result.stderr.strip()[-600:]))
    return float(text)
