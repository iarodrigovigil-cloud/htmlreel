"""What a reel file must say, and what it is refused for not saying."""

import json
import os
import tempfile
import unittest

from htmlreel import config

MINIMAL = {"name": "t", "page": "scene.html", "duration": 6.0}


def write(data, extra_files=("scene.html",)):
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "t.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    for name in extra_files:
        open(os.path.join(folder, name), "w").close()
    return path


class Basics(unittest.TestCase):
    def test_paths_resolve_against_the_config_file(self):
        path = write(MINIMAL)
        reel = config.Reel(path)
        self.assertEqual(os.path.dirname(reel.page), os.path.dirname(path))

    def test_frame_count_follows_fps_and_duration(self):
        reel = config.Reel(write(dict(MINIMAL, fps=15, duration=30.0)))
        self.assertEqual(reel.frame_count, 450)

    def test_a_reel_needs_a_page(self):
        data = dict(MINIMAL)
        del data["page"]
        with self.assertRaises(config.ConfigError):
            config.Reel(write(data))

    def test_broken_json_says_so(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "t.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        with self.assertRaises(config.ConfigError):
            config.Reel(path)


def with_voice(**voice):
    spec = {"source": "voice.mp3", "cuts": [0.0, 3.0, 6.0],
            "blocks": [{"start": 0.0, "end": 2.0},
                       {"start": 2.5, "end": 4.5}]}
    spec.update(voice)
    return write(dict(MINIMAL, voice=spec), ("scene.html", "voice.mp3"))


class Voice(unittest.TestCase):
    def test_a_well_formed_voice_section_loads(self):
        reel = config.Reel(with_voice())
        self.assertEqual(len(reel.voice["blocks"]), 2)

    def test_cuts_must_have_one_more_entry_than_blocks(self):
        """The mistake that would otherwise put two blocks on one shot."""
        with self.assertRaises(config.ConfigError) as caught:
            config.Reel(with_voice(cuts=[0.0, 2.0, 4.0, 6.0]))
        self.assertIn("blocks", str(caught.exception))

    def test_cuts_must_increase(self):
        with self.assertRaises(config.ConfigError):
            config.Reel(with_voice(cuts=[0.0, 6.0, 3.0]))

    def test_a_block_may_not_end_before_it_starts(self):
        with self.assertRaises(config.ConfigError):
            config.Reel(with_voice(
                blocks=[{"start": 2.0, "end": 1.0},
                        {"start": 2.5, "end": 4.5}]))

    def test_a_trim_needs_three_numbers(self):
        with self.assertRaises(config.ConfigError):
            config.Reel(with_voice(
                blocks=[{"start": 0.0, "end": 2.0, "trim": [[1.0, 1.5]]},
                        {"start": 2.5, "end": 4.5}]))

    def test_no_blocks_points_at_measure(self):
        with self.assertRaises(config.ConfigError) as caught:
            config.Reel(with_voice(blocks=[]))
        self.assertIn("measure", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
