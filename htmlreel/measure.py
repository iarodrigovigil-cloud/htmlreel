"""Finding where each spoken block starts and ends.

MEASURE THE VOICE BEFORE YOU FIX THE SHOT CUTS. The temptation is to design
the shots first and record to fit them. It does not work: two takes of the
same script by the same voice can differ by more than 20% in length, so cuts
chosen before the recording exists are guesses, and a guess that is wrong by
half a second means re-rendering every frame.

The method: a recording is a run of blocks separated by the pauses the reader
takes at the blank lines of the script. silencedetect finds every quiet
stretch; some of them are those boundaries and the rest are commas and full
stops inside a block, which are the rhythm of the delivery and must survive.

WHAT THIS MODULE WILL NOT DO IS GUESS WHICH IS WHICH. Sorting the gaps by
length and cutting at the longest ones is the obvious approach and it is
unsound, because the two populations overlap. A real recording measured while
writing this: the longest pause in the whole take, 0.70 s, was a full stop in
the middle of a block, while one of the four real boundaries was 0.41 s. No
threshold separates those. A reader slows down at the end of a dense sentence
and hurries over a boundary they do not feel.

So: this module reports the gaps and their lengths. You decide which are
boundaries, using the thing that actually knows -- the script, and a transcript
with word timestamps when a shot has to reveal something on a given phrase.
The number of blocks is not a mystery; it is the number of blank-line-separated
paragraphs you handed the reader.
"""

import re

from . import tools

LINE = re.compile(r"silence_(start|end):\s*(-?[\d.]+)")


def silences(path, threshold_db=-35.0, minimum=0.25):
    """Every stretch quieter than the threshold, as (start, end) seconds."""
    result = tools.run([
        tools.ffmpeg(), "-hide_banner", "-i", path,
        "-af", "silencedetect=noise=%gdB:d=%g" % (threshold_db, minimum),
        "-f", "null", "-",
    ])
    # NOTE: never add "-v error" to that command. It suppresses the filter's
    # own output along with the banner, and silencedetect then succeeds while
    # printing nothing at all.
    found, start = [], None
    for kind, value in LINE.findall(result.stderr):
        if kind == "start":
            start = float(value)
        elif start is not None:
            found.append((start, float(value)))
            start = None
    if start is not None:
        found.append((start, tools.duration(path)))
    return found


def speech_end(path, threshold_db=-35.0):
    """Where the last sound dies away.

    Measured on the reversed audio: a trailing silence that runs to the end of
    the file is not reliably reported in the forward pass.
    """
    total = tools.duration(path)
    result = tools.run([
        tools.ffmpeg(), "-hide_banner", "-i", path,
        "-af", "areverse,silencedetect=noise=%gdB:d=0.04" % threshold_db,
        "-f", "null", "-",
    ])
    for kind, value in LINE.findall(result.stderr):
        if kind == "start":
            return round(total - float(value), 3)
    return round(total, 3)


def gaps(path, threshold_db=-35.0, minimum=0.25):
    """Every candidate boundary in the recording.

    Returns (gaps, speech_end), where each gap is a dict with the moment
    speech stops, the moment it resumes, and how long the silence lasts.
    Leading and trailing silence are not gaps: they are the edges.
    """
    end = speech_end(path, threshold_db)
    found = []
    for start, stop in silences(path, threshold_db, minimum):
        if stop >= end or start <= 0.0:
            continue
        found.append({
            "after": round(start, 3),
            "before": round(stop, 3),
            "length": round(stop - start, 3),
        })
    return found, end


def split(found, end, boundaries):
    """Cut the recording into blocks at the chosen gaps.

    `boundaries` holds the gaps, out of `found`, that separate blocks.
    """
    chosen = sorted(boundaries, key=lambda g: g["after"])
    blocks, cursor = [], 0.0
    for gap in chosen:
        blocks.append((cursor, gap["after"]))
        cursor = gap["before"]
    blocks.append((cursor, end))

    inside = []
    for start, stop in blocks:
        inside.append([g for g in found
                       if start < g["after"] and g["before"] < stop])
    return blocks, inside


def longest(found, count):
    """The `count` longest gaps -- a starting suggestion, never an answer."""
    return sorted(sorted(found, key=lambda g: -g["length"])[:count],
                  key=lambda g: g["after"])
