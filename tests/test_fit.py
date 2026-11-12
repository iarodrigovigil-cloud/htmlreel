"""The placement arithmetic: which block lands where, and what refuses to.

These run without Chrome or ffmpeg, because the part worth protecting is the
decision to refuse, not the encoding.
"""

import json
import os
import tempfile
import unittest

from htmlreel import config, fit


def reel(**overrides):
    """A three-shot reel whose blocks fit comfortably, unless overridden."""
    data = {
        "name": "t",
        "page": "scene.html",
        "duration": 12.0,
        "voice": {
            "source": "voice.mp3",
            "lead": 0.35,
            "cuts": [0.0, 4.0, 8.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 3.0},
                {"start": 3.5, "end": 6.5},
                {"start": 7.0, "end": 10.0},
            ],
        },
    }
    data.update(overrides)
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "t.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    for name in ("scene.html", "voice.mp3"):
        open(os.path.join(folder, name), "w").close()
    return config.Reel(path)


class Placement(unittest.TestCase):
    def test_each_block_starts_a_lead_after_its_cut(self):
        rows, _ = fit.plan(reel())
        self.assertEqual([round(r["voice"][0], 3) for r in rows],
                         [0.35, 4.35, 8.35])

    def test_slack_is_what_is_left_of_the_shot(self):
        rows, _ = fit.plan(reel())
        # 4 s shot, 0.35 lead, 3 s of speech.
        self.assertAlmostEqual(rows[0]["slack"], 0.65, places=3)

    def test_a_block_may_set_its_own_lead(self):
        spec = reel().voice
        del spec
        r = reel(voice={
            "source": "voice.mp3", "lead": 0.35,
            "cuts": [0.0, 4.0, 8.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 3.0, "lead": 1.0},
                {"start": 3.5, "end": 6.5},
                {"start": 7.0, "end": 10.0},
            ],
        })
        rows, _ = fit.plan(r)
        self.assertAlmostEqual(rows[0]["voice"][0], 1.0, places=3)


class Refusal(unittest.TestCase):
    def test_a_block_longer_than_its_shot_is_refused(self):
        r = reel(voice={
            "source": "voice.mp3", "lead": 0.35,
            "cuts": [0.0, 4.0, 8.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 3.9},   # 0.35 + 3.9 = 4.25 > 4.0
                {"start": 4.5, "end": 7.5},
                {"start": 8.0, "end": 11.0},
            ],
        })
        with self.assertRaises(fit.DoesNotFit) as caught:
            fit.plan(r)
        self.assertIn("block 1", str(caught.exception))

    def test_the_complaint_names_every_block_at_fault(self):
        r = reel(voice={
            "source": "voice.mp3", "lead": 0.35,
            "cuts": [0.0, 4.0, 8.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 3.9},
                {"start": 4.0, "end": 8.0},
                {"start": 8.0, "end": 11.0},
            ],
        })
        with self.assertRaises(fit.DoesNotFit) as caught:
            fit.plan(r)
        self.assertIn("block 1", str(caught.exception))
        self.assertIn("block 2", str(caught.exception))


class Trimming(unittest.TestCase):
    def test_trimming_a_pause_shortens_the_block(self):
        plain = reel(voice={
            "source": "voice.mp3", "lead": 0.35,
            "cuts": [0.0, 5.0, 9.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 4.0},
                {"start": 4.5, "end": 7.5},
                {"start": 8.0, "end": 10.0},
            ],
        })
        trimmed = reel(voice={
            "source": "voice.mp3", "lead": 0.35,
            "cuts": [0.0, 5.0, 9.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 4.0, "trim": [[1.0, 1.8, 0.2]]},
                {"start": 4.5, "end": 7.5},
                {"start": 8.0, "end": 10.0},
            ],
        })
        before = fit.plan(plain)[0][0]["length"]
        after = fit.plan(trimmed)[0][0]["length"]
        # An 0.8 s pause replaced by 0.2 s takes 0.6 s off the block.
        self.assertAlmostEqual(before - after, 0.6, places=3)

    def test_a_trim_keeps_the_speech_on_both_sides(self):
        r = reel(voice={
            "source": "voice.mp3", "lead": 0.35,
            "cuts": [0.0, 5.0, 9.0, 12.0],
            "blocks": [
                {"start": 0.0, "end": 4.0, "trim": [[1.0, 1.8, 0.2]]},
                {"start": 4.5, "end": 7.5},
                {"start": 8.0, "end": 10.0},
            ],
        })
        _, placed = fit.plan(r)
        kinds = [kind for kind, _, _ in placed[0][1]]
        self.assertEqual(kinds, ["speak", "pause", "speak"])


if __name__ == "__main__":
    unittest.main()
