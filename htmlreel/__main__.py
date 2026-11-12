"""Command line: htmlreel measure | render | fit | build"""

import argparse
import json
import os
import sys

from . import config, fit, measure, render, tools


def cmd_measure(args):
    """Report the gaps in a recording and, on request, a suggested split."""
    found, end = measure.gaps(args.audio, args.threshold, args.minimum)
    total = tools.duration(args.audio)

    print("\n%s   %.3f s   (speech ends at %.3f)"
          % (os.path.basename(args.audio), total, end))
    if args.words:
        print("%d words at %.3f s per word" % (args.words, end / args.words))

    if not found:
        print("\nNo gap of at least %.2f s. Lower --minimum, or the reader "
              "ran the whole script together." % args.minimum)
        return 1

    picked = []
    if args.blocks:
        if args.blocks - 1 > len(found):
            print("\nOnly %d gaps found, so the recording cannot hold %d "
                  "blocks." % (len(found), args.blocks))
            return 1
        picked = measure.longest(found, args.blocks - 1)

    print("\n  %d gaps, longest first%s:\n"
          % (len(found), " (> marks the suggested boundaries)" if picked
             else ""))
    for gap in sorted(found, key=lambda g: -g["length"]):
        print("  %s %7.3f - %7.3f   %.3f s"
              % (">" if gap in picked else " ",
                 gap["after"], gap["before"], gap["length"]))

    if not picked:
        print("\nPass --blocks N -- N is the number of blank-line-separated")
        print("paragraphs in the script -- to see a suggested split.")
        return 0

    blocks, inside = measure.split(found, end, picked)
    print("\n  the split that gives:\n")
    for index, (start, stop) in enumerate(blocks):
        print("  block %d   %7.3f - %7.3f   (%.3f s)%s"
              % (index + 1, start, stop, stop - start,
                 "   %d pause(s) kept inside" % len(inside[index])
                 if inside[index] else ""))

    print("\nFor the reel file:\n")
    print(json.dumps({"blocks": [{"start": s, "end": e} for s, e in blocks]},
                     indent=2))

    print("\nCHECK THIS AGAINST THE SCRIPT BEFORE USING IT. Picking the")
    print("longest gaps is a guess, and on real recordings it is often wrong:")
    print("readers slow down at the end of a dense sentence and hurry over a")
    print("boundary they do not feel, so a pause inside a block can be longer")
    print("than a real one between two. Read the first few words after each")
    print("boundary off a transcript and move any that landed mid-sentence.")
    return 0


def cmd_render(args):
    reel = config.Reel(args.reel)
    failed = render.frames(reel)
    if failed:
        print("  %d frames could not be captured: %s"
              % (len(failed), failed[:12]))
        return 1
    silent = render.assemble(reel)
    render.to_vertical(reel, silent)
    return 0


def cmd_fit(args):
    reel = config.Reel(args.reel)
    if not reel.voice:
        print('This reel has no "voice" section; there is nothing to fit.')
        return 1

    try:
        rows, placed = fit.plan(reel)
    except fit.DoesNotFit as error:
        print("\nThe narration does not fit the shots:\n%s" % error)
        print("\nNothing was written. Move a cut, or trim a pause inside the")
        print("block that overruns -- do not shorten the shot it spills into.")
        return 1

    print("\n%s" % reel.name)
    for row in rows:
        print("  block %d  %5.2f s   shot %5.1f-%5.1f   voice %5.2f-%5.2f"
              "   slack %+.2f%s"
              % (row["n"], row["length"], row["shot"][0], row["shot"][1],
                 row["voice"][0], row["voice"][1], row["slack"],
                 "   " + row["note"] if row["note"] else ""))

    track = fit.build_track(reel, placed)

    print("\n  checking the track that was written")
    faults = fit.verify(reel, track)
    if faults:
        print("  blocks %s cross a cut in the finished track."
              % ", ".join(str(f) for f in faults))
        return 1

    made = 0
    for suffix in ("", "-vertical"):
        silent = reel.output("-silent" + suffix)
        if not os.path.exists(silent):
            continue
        fit.mix(reel, silent, track, reel.output(suffix))
        made += 1
    if not made:
        print("  no silent cut to mix with. Run \"htmlreel render\" first.")
        return 1
    return 0


def cmd_build(args):
    code = cmd_render(args)
    if code:
        return code
    # A reel with no narration is finished once the silent cut exists. That is
    # not a failure to fit anything.
    if not config.Reel(args.reel).voice:
        print('  no "voice" section: the silent cut is the finished reel.')
        return 0
    return cmd_fit(args)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="htmlreel",
        description="Render a narrated video from an HTML page that is a "
                    "pure function of time.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("measure", help="find the block edges of a recording")
    p.add_argument("audio")
    p.add_argument("--threshold", type=float, default=-35.0,
                   help="dB below which audio counts as silence "
                        "(default: -35)")
    p.add_argument("--minimum", type=float, default=0.25,
                   help="shortest silence worth reporting, in seconds "
                        "(default: 0.25)")
    p.add_argument("--blocks", type=int,
                   help="how many blocks the script has; shows a suggested "
                        "split at the longest gaps")
    p.add_argument("--words", type=int,
                   help="word count, to report seconds per word")
    p.set_defaults(run=cmd_measure)

    p = sub.add_parser("render", help="capture the frames and build the "
                                      "silent cut")
    p.add_argument("reel")
    p.set_defaults(run=cmd_render)

    p = sub.add_parser("fit", help="place the voice and mix the final cut")
    p.add_argument("reel")
    p.set_defaults(run=cmd_fit)

    p = sub.add_parser("build", help="render, then fit")
    p.add_argument("reel")
    p.set_defaults(run=cmd_build)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (tools.MissingTool, config.ConfigError, FileNotFoundError) as error:
        print("%s" % error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
