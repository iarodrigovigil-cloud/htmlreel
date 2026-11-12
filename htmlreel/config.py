"""Reading and validating a reel's JSON file.

Every path inside the file is resolved against the directory the file lives
in, so a reel directory can be moved or checked out anywhere.
"""

import json
import os


class ConfigError(Exception):
    pass


DEFAULTS = {
    "fps": 15,
    "duration": 30.0,
    "width": 1920,
    "height": 1080,
    "parallelism": 3,
    "crf": 16,
}

VERTICAL_DEFAULTS = {
    "width": 1080,
    "height": 1920,
    "background": "black",
    "crf": 18,
}

VOICE_DEFAULTS = {
    "music": None,
    "music_volume": 0.55,
    "lead": 0.35,
    "fade_in": 0.0,
    "sample_rate": 44100,
}


class Reel:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.root = os.path.dirname(self.path)
        with open(self.path, encoding="utf-8") as handle:
            try:
                raw = json.load(handle)
            except ValueError as error:
                raise ConfigError("%s is not valid JSON: %s" % (path, error))

        self.name = raw.get("name") or os.path.splitext(
            os.path.basename(self.path))[0]

        for key, fallback in DEFAULTS.items():
            setattr(self, key, raw.get(key, fallback))

        if "page" not in raw:
            raise ConfigError('%s has no "page": name the HTML file to render.'
                              % self.path)
        self.page = self.resolve(raw["page"])

        self.out = self.resolve(raw.get("out", self.name))
        self.frames_dir = self.resolve(raw.get("frames", "_frames-%s" % self.name))

        self.vertical = None
        if raw.get("vertical"):
            self.vertical = dict(VERTICAL_DEFAULTS)
            if isinstance(raw["vertical"], dict):
                self.vertical.update(raw["vertical"])

        self.voice = None
        if raw.get("voice"):
            self.voice = self._read_voice(raw["voice"])

        self.frame_count = int(round(self.fps * self.duration))
        if self.frame_count < 1:
            raise ConfigError("fps x duration must be at least one frame.")

    def resolve(self, path):
        return path if os.path.isabs(path) else os.path.join(self.root, path)

    def _read_voice(self, raw):
        voice = dict(VOICE_DEFAULTS)
        voice.update(raw)

        if "source" not in raw:
            raise ConfigError('"voice" has no "source": name the audio file.')
        voice["source"] = self.resolve(raw["source"])
        if voice["music"]:
            voice["music"] = self.resolve(voice["music"])

        cuts = voice.get("cuts")
        if not cuts or len(cuts) < 2:
            raise ConfigError('"voice.cuts" needs the start of every shot plus '
                              'the end of the reel: [0, ..., duration].')
        if list(cuts) != sorted(cuts):
            raise ConfigError('"voice.cuts" must increase.')
        voice["cuts"] = [float(c) for c in cuts]

        blocks = []
        for index, block in enumerate(voice.get("blocks") or [], start=1):
            if "start" not in block or "end" not in block:
                raise ConfigError("block %d needs a start and an end." % index)
            start, end = float(block["start"]), float(block["end"])
            if end <= start:
                raise ConfigError("block %d ends before it starts." % index)
            trims = []
            for trim in block.get("trim", []):
                if len(trim) != 3:
                    raise ConfigError(
                        "block %d: every trim is [start, end, new_length]."
                        % index)
                trims.append(tuple(float(v) for v in trim))
            blocks.append({
                "start": start,
                "end": end,
                "trim": sorted(trims),
                "lead": float(block.get("lead", voice["lead"])),
                "note": block.get("note", ""),
            })

        if not blocks:
            raise ConfigError('"voice.blocks" is empty. Run "htmlreel measure" '
                              "on the recording to get the block edges.")
        if len(blocks) != len(voice["cuts"]) - 1:
            raise ConfigError(
                "%d blocks but %d shots. Every block is spoken over one shot, "
                "so cuts must have exactly one more entry than blocks."
                % (len(blocks), len(voice["cuts"]) - 1))

        voice["blocks"] = blocks
        return voice

    def output(self, suffix="", extension=".mp4"):
        return "%s%s%s" % (self.out, suffix, extension)
