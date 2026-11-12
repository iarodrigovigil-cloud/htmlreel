"""Turning an HTML page into a silent MP4, one frame at a time.

The page is asked for its state at an exact millisecond -- page.html?t=4200 --
and screenshotted. One browser launch per frame.

WHY ONE LAUNCH PER FRAME, which looks wasteful and is the whole point: a page
that is a pure function of t gives the same pixels for the same t no matter
when or where it is rendered. There is no animation clock to drift, no
scheduler to fall behind, and no state carried from the previous frame. That
also makes the captures independent, so they can run in parallel in any order,
and a crashed run can be resumed: a frame already on disk is never recaptured.

The cost is real -- a 30-second reel at 15 fps is 450 browser launches, which
takes minutes, not seconds. In exchange the output is reproducible, which
matters far more when a frame has to be fixed three weeks later.
"""

import concurrent.futures
import os

from . import tools

FLAGS = [
    "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
    "--disable-extensions", "--disable-background-networking",
    "--no-first-run", "--disable-sync", "--mute-audio",
    "--disable-dev-shm-usage",
]


def page_url(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")


def _capture(job):
    index, url, destination, flags, binary = job
    if os.path.exists(destination) and os.path.getsize(destination) > 0:
        return index, True

    # Two tries with a longer deadline on the second. A launch that hangs is
    # far more common than one that fails outright, and retrying it usually
    # works; retrying forever does not.
    for deadline in (30, 60):
        try:
            result = tools.run(
                [binary, *flags, "--screenshot=" + destination, url],
                timeout=deadline)
        except Exception:
            continue
        if result.returncode == 0 and os.path.exists(destination):
            return index, True
    return index, False


def frames(reel, report=print):
    """Capture every frame that is not already on disk.

    Returns the list of frame numbers that could not be captured.
    """
    if not os.path.exists(reel.page):
        raise FileNotFoundError(reel.page)

    binary = tools.chrome()
    os.makedirs(reel.frames_dir, exist_ok=True)
    flags = FLAGS + [
        "--window-size=%d,%d" % (reel.width, reel.height),
        "--force-device-scale-factor=1",
    ]
    base = page_url(reel.page)
    step = reel.duration * 1000.0 / reel.frame_count

    jobs = []
    for index in range(reel.frame_count):
        millisecond = round(index * step)
        jobs.append((
            index,
            "%s?t=%d" % (base, millisecond),
            os.path.join(reel.frames_dir, "f_%05d.png" % index),
            flags,
            binary,
        ))

    report("%s: %d frames at %g fps (%d browsers at a time)"
           % (reel.name, reel.frame_count, reel.fps, reel.parallelism))

    failed, done = [], 0
    with concurrent.futures.ThreadPoolExecutor(reel.parallelism) as pool:
        for index, ok in pool.map(_capture, jobs):
            done += 1
            if not ok:
                failed.append(index)
            if done % 90 == 0 or done == reel.frame_count:
                report("  %d/%d" % (done, reel.frame_count))
    return sorted(failed)


def assemble(reel, report=print):
    """Stitch the captured frames into a silent MP4."""
    destination = reel.output("-silent")
    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    result = tools.run([
        tools.ffmpeg(), "-y",
        "-framerate", str(reel.fps),
        "-i", os.path.join(reel.frames_dir, "f_%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(reel.crf),
        "-movflags", "+faststart", destination,
    ])
    if not os.path.exists(destination):
        raise RuntimeError("ffmpeg could not assemble the frames:\n%s"
                           % result.stderr[-1500:])
    report("  %s  (%.1f MB)" % (os.path.basename(destination),
                                os.path.getsize(destination) / 1048576))
    return destination


def to_vertical(reel, source, report=print):
    """Letterbox the wide cut onto a vertical canvas.

    The picture is scaled, never cropped: cropping a 16:9 frame to 9:16 throws
    away two thirds of the width, which is where the text usually is. The bars
    take the background colour from the config so they read as part of the
    design rather than as a mistake.
    """
    if not reel.vertical:
        return None
    spec = reel.vertical
    destination = reel.output("-silent-vertical")
    result = tools.run([
        tools.ffmpeg(), "-y", "-i", source,
        "-vf", "scale=%d:-2,pad=%d:%d:0:(oh-ih)/2:color=%s"
               % (spec["width"], spec["width"], spec["height"],
                  spec["background"]),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(spec["crf"]),
        "-movflags", "+faststart", destination,
    ])
    if not os.path.exists(destination):
        raise RuntimeError("ffmpeg could not build the vertical cut:\n%s"
                           % result.stderr[-1000:])
    report("  %s  (%.1f MB)" % (os.path.basename(destination),
                                os.path.getsize(destination) / 1048576))
    return destination
