"""Reading silencedetect's output, and dividing a recording into blocks.

The sample below is real ffmpeg output from the recording the README quotes:
five blocks of narration whose longest internal pause is longer than one of
the real boundaries. It is kept because that is the case that matters.
"""

import unittest

from htmlreel import measure

REPORT = """
[Parsed_silencedetect_0 @ 000001] silence_start: 5.924535
[Parsed_silencedetect_0 @ 000001] silence_end: 6.639569 | silence_duration: 0.715034
[Parsed_silencedetect_0 @ 000001] silence_start: 9.140385
[Parsed_silencedetect_0 @ 000001] silence_end: 9.839501 | silence_duration: 0.699116
[Parsed_silencedetect_0 @ 000001] silence_start: 11.37551
[Parsed_silencedetect_0 @ 000001] silence_end: 11.996463 | silence_duration: 0.620952
[Parsed_silencedetect_0 @ 000001] silence_start: 14.606757
[Parsed_silencedetect_0 @ 000001] silence_end: 15.269546 | silence_duration: 0.662789
[Parsed_silencedetect_0 @ 000001] silence_start: 15.897256
[Parsed_silencedetect_0 @ 000001] silence_end: 16.259456 | silence_duration: 0.3622
[Parsed_silencedetect_0 @ 000001] silence_start: 17.731293
[Parsed_silencedetect_0 @ 000001] silence_end: 18.254989 | silence_duration: 0.523696
[Parsed_silencedetect_0 @ 000001] silence_start: 19.4939
[Parsed_silencedetect_0 @ 000001] silence_end: 19.906757 | silence_duration: 0.412857
"""

SPEECH_END = 22.641


class Parsing(unittest.TestCase):
    def test_every_pair_is_read(self):
        found = measure.parse_silences(REPORT, SPEECH_END)
        self.assertEqual(len(found), 7)
        self.assertAlmostEqual(found[0][0], 5.924535, places=5)
        self.assertAlmostEqual(found[0][1], 6.639569, places=5)

    def test_output_with_no_silences_reads_as_none(self):
        self.assertEqual(measure.parse_silences("ffmpeg version 7.0\n", 10.0),
                         [])

    def test_a_silence_that_never_closes_runs_to_the_end(self):
        dangling = REPORT + "silence_start: 21.0\n"
        found = measure.parse_silences(dangling, SPEECH_END)
        self.assertEqual(found[-1], (21.0, SPEECH_END))


def gaps_from_report():
    found = []
    for start, stop in measure.parse_silences(REPORT, SPEECH_END):
        found.append({"after": round(start, 3), "before": round(stop, 3),
                      "length": round(stop - start, 3)})
    return found


class Splitting(unittest.TestCase):
    def test_a_chosen_split_produces_one_more_block_than_boundaries(self):
        found = gaps_from_report()
        chosen = [g for g in found
                  if g["after"] in (5.925, 11.376, 15.897, 19.494)]
        blocks, _ = measure.split(found, SPEECH_END, chosen)
        self.assertEqual(len(blocks), 5)

    def test_the_true_split_of_this_recording(self):
        """The boundaries a transcript confirms, not the ones length suggests."""
        found = gaps_from_report()
        chosen = [g for g in found
                  if g["after"] in (5.925, 11.376, 14.607, 19.494)]
        blocks, inside = measure.split(found, SPEECH_END, chosen)
        self.assertEqual(
            [(round(a, 3), round(b, 3)) for a, b in blocks],
            [(0.0, 5.925), (6.64, 11.376), (11.996, 14.607),
             (15.27, 19.494), (19.907, 22.641)])
        # Block 2 keeps the 0.70 s full stop; block 4 keeps two pauses.
        self.assertEqual([len(p) for p in inside], [0, 1, 0, 2, 0])

    def test_longest_gaps_get_this_recording_wrong(self):
        """The guess the tool refuses to make silently.

        Four of the longest gaps are picked, and one of them -- 9.140, the
        full stop inside block 2 -- is not a boundary at all, while the real
        boundary at 19.494 is too short to make the cut.
        """
        found = gaps_from_report()
        guessed = {g["after"] for g in measure.longest(found, 4)}
        self.assertIn(9.14, guessed)
        self.assertNotIn(19.494, guessed)


if __name__ == "__main__":
    unittest.main()
