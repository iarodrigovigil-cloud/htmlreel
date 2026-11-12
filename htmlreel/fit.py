"""Placing the voice against the shots, and mixing the finished reel.

The rule the whole module exists to keep: a block of narration is spoken over
one shot and never spills into the next. The voice is not stretched, sped up
or pitched to make that true. Each block starts a fixed moment after its shot
begins -- the lead -- and the gap to the following block is generated silence.
The slack left at the end of each shot is reported, so a shot that is nearly
too short shows up as a number instead of as a crossed cut in the finished
file.

Everything is measured and checked BEFORE any audio is written. Not having the
track is a smaller problem than having a wrong one that looks finished.
"""

import os

from . import tools


class DoesNotFit(Exception):
    pass


def _pieces(block):
    """A block as alternating spoken runs and shortened pauses.

    ("speak", from, to) takes that slice of the recording.
    ("pause", seconds, None) replaces an internal pause with a shorter one.
    """
    pieces, cursor = [], block["start"]
    for start, end, new_length in block["trim"]:
        pieces.append(("speak", cursor, start))
        pieces.append(("pause", new_length, None))
        cursor = end
    pieces.append(("speak", cursor, block["end"]))
    return pieces


def _length(pieces):
    return sum(b - a if kind == "speak" else a for kind, a, b in pieces)


def plan(reel):
    """Work out where every block lands. Raises DoesNotFit if one does not."""
    voice = reel.voice
    cuts = voice["cuts"]
    rows, placed, trouble, cursor = [], [], [], 0.0

    for index, block in enumerate(voice["blocks"]):
        pieces = _pieces(block)
        length = _length(pieces)
        start = cuts[index] + block["lead"]
        end = start + length
        limit = cuts[index + 1]
        slack = limit - end

        if start < cursor - 0.001:
            trouble.append("block %d starts at %.2f, but block %d is still "
                           "going at %.2f" % (index + 1, start, index, cursor))
        if slack < -0.001:
            trouble.append("block %d runs %.2f s past the end of its shot"
                           % (index + 1, -slack))

        rows.append({
            "n": index + 1, "length": length, "shot": (cuts[index], limit),
            "voice": (start, end), "slack": slack, "note": block["note"],
        })
        placed.append((start, pieces))
        cursor = end

    if cursor > reel.duration + 0.001:
        trouble.append("the narration ends at %.2f, past the %.1f s of the reel"
                       % (cursor, reel.duration))
    if trouble:
        raise DoesNotFit("\n".join("  " + line for line in trouble))
    return rows, placed


def build_track(reel, placed, report=print):
    """Write the narration out as one track as long as the reel.

    Silence is GENERATED and concatenated rather than applied as a delay.
    `adelay` was the obvious tool and it returned the track unshifted; building
    the gaps explicitly always works. The generated silence is MONO on purpose:
    concatenating mono silence with a stereo recording makes the result about
    3 dB quieter than the other reels in a series, which is the kind of fault
    nobody notices until the whole set is published.
    """
    voice = reel.voice
    destination = reel.output("-voice", ".wav")
    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    rate = voice["sample_rate"]

    filters, labels, n, cursor = [], [], 0, 0.0
    for start, pieces in placed:
        if start - cursor > 0.001:
            filters.append("aevalsrc=0:d=%.3f:s=%d:c=mono[t%d]"
                           % (start - cursor, rate, n))
            labels.append("[t%d]" % n)
            n += 1
        for kind, a, b in pieces:
            if kind == "speak":
                filters.append("[0:a]atrim=start=%.3f:end=%.3f,"
                               "asetpts=PTS-STARTPTS[t%d]" % (a, b, n))
            else:
                filters.append("aevalsrc=0:d=%.3f:s=%d:c=mono[t%d]"
                               % (a, rate, n))
            labels.append("[t%d]" % n)
            n += 1
        cursor = start + _length(pieces)

    chain = ";".join(filters) + ";" + "".join(labels) + \
        "concat=n=%d:v=0:a=1" % len(labels)
    if voice["fade_in"] > 0:
        chain += ",afade=t=in:st=0:d=%.3f" % voice["fade_in"]
    chain += ",apad,atrim=end=%.3f[out]" % reel.duration

    result = tools.run([
        tools.ffmpeg(), "-y", "-i", voice["source"],
        "-filter_complex", chain, "-map", "[out]",
        "-c:a", "pcm_s16le", destination,
    ])
    if not os.path.exists(destination):
        raise RuntimeError("ffmpeg could not build the voice track:\n%s"
                           % result.stderr[-1500:])
    report("  voice track  %.2f s   %s"
           % (tools.duration(destination), os.path.basename(destination)))
    return destination


def mix(reel, video, track, destination, report=print):
    """Lay the voice track, and any music, over a silent cut."""
    voice = reel.voice
    command = [tools.ffmpeg(), "-y", "-i", video, "-i", track]
    if voice["music"]:
        command += ["-i", voice["music"], "-filter_complex",
                    "[2:a]volume=%s[m];[1:a][m]amix=inputs=2:duration=first:"
                    "dropout_transition=0[out]" % voice["music_volume"]]
        audio = "[out]"
    else:
        audio = "1:a"
    command += ["-map", "0:v", "-map", audio, "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", "-shortest", destination]

    result = tools.run(command)
    if not os.path.exists(destination):
        raise RuntimeError("ffmpeg could not mix %s:\n%s"
                           % (os.path.basename(destination),
                              result.stderr[-1500:]))
    report("  %-14s %.2f s   %5.0f KB   %s"
           % ("mixed", tools.duration(destination),
              os.path.getsize(destination) / 1024,
              os.path.basename(destination)))
    return destination


def speech_runs(track, threshold_db=-50.0, minimum=0.30):
    """The stretches of the finished track that carry sound."""
    from . import measure

    quiet = measure.silences(track, threshold_db, minimum)
    runs, cursor = [], 0.0
    for start, end in quiet:
        if start > cursor + 0.001:
            runs.append((cursor, start))
        cursor = end
    return runs


def verify(reel, track, report=print):
    """Read the finished track back and check nothing crossed a cut.

    This checks the file that was written, not the plan that was meant to
    produce it.

    The test is per cut, not per block, and that is deliberate. Matching runs
    of sound back to blocks is guesswork -- a block with an internal pause
    longer than the detector's window looks like two blocks, and taking the
    first of them as the block's end makes the check pass when it should not.
    What has to be true needs no such matching: AT EVERY CUT THE TRACK IS
    SILENT. A run of sound that straddles a cut is the fault being looked for.
    """
    cuts = reel.voice["cuts"]
    runs = speech_runs(track)
    faults = []

    for index in range(len(cuts) - 1):
        opens, closes = cuts[index], cuts[index + 1]
        inside = [r for r in runs
                  if r[1] > opens + 0.001 and r[0] < closes - 0.001]
        if not inside:
            report("  shot %d  %5.1f-%5.1f   silent" % (index + 1, opens, closes))
            continue

        onset = min(r[0] for r in inside)
        ending = max(r[1] for r in inside)
        early = onset < opens - 0.001
        late = ending > closes + 0.001
        report("  shot %d  %5.1f-%5.1f   voice %5.2f-%5.2f   %s"
               % (index + 1, opens, closes, onset, ending,
                  "CROSSES THE CUT" if early or late else "ok"))
        if early or late:
            faults.append(index + 1)
    return faults
