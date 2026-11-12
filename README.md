# htmlreel

Render a narrated video from an HTML page, and fit the shot cuts to the voice
that was actually recorded.

You write a page that draws the state of the world at millisecond `t`.
htmlreel screenshots it 450 times, assembles the frames, measures where the
narration pauses, places each block of speech inside its own shot, and checks
the finished track to make sure nothing crossed a cut.

No Puppeteer, no Node, no Python dependencies. Chrome and ffmpeg, which you
already have.

```bash
pip install git+https://github.com/iarodrigovigil-cloud/htmlreel
htmlreel build my-reel.json
```

## Why a page that is a function of `t`

The page must take its time from the query string and draw that instant:

```js
function render(t) { /* draw the world at t milliseconds */ }

const query = new URLSearchParams(location.search);
if (query.has('t')) render(Number(query.get('t')));
```

No `setInterval`, no CSS transitions, no `Date.now()`. Every one of those makes
the output depend on *when* a frame happened to be captured.

Give that up and you get three things. The same `t` always produces the same
pixels, so a reel is reproducible months later. Frames are independent, so
they render in parallel and an interrupted run resumes where it stopped —
a frame already on disk is never recaptured. And a frame can be inspected on
its own: open `page.html?t=18400` in a browser and you are looking at exactly
what second 18.4 will contain.

The cost is honest: one browser launch per frame. A 30-second reel at 15 fps
is 450 launches and takes minutes, not seconds. That trade is worth making the
first time you have to fix one shot three weeks after shipping.

## The three commands

### `htmlreel measure recording.mp3 --blocks 5`

Reports every pause in a recording, longest first, and suggests where the
blocks divide.

```
voice.mp3   22.988 s   (speech ends at 22.641)
60 words at 0.377 s per word

  7 gaps, longest first (> marks the suggested boundaries):

  >   5.925 -   6.640   0.715 s
  >   9.140 -   9.840   0.699 s
  >  14.607 -  15.270   0.663 s
  >  11.376 -  11.996   0.621 s
      17.731 -  18.255   0.524 s
      19.494 -  19.907   0.413 s
      15.897 -  16.259   0.362 s
```

**The suggestion is a guess and it is often wrong.** In that very recording it
is: the 0.699 s pause is a full stop in the middle of a block, and one of the
real boundaries is the 0.413 s gap near the bottom of the list. Readers slow
down at the end of a dense sentence and hurry over a boundary they do not
feel, so the two populations overlap and no threshold separates them. The
command prints the table so you can pick; the script tells you how many blocks
there are, and a transcript with word timestamps tells you which words fall on
each side of a boundary.

That last check is not pedantry. It is the difference between a closing shot
that reveals a line as it is spoken and one that reveals it two seconds early.

### `htmlreel render my-reel.json`

Captures the frames and assembles the silent cut, plus a vertical version if
the config asks for one. The vertical is letterboxed onto a coloured canvas,
never cropped: cropping 16:9 to 9:16 throws away two thirds of the width,
which is where the text lives.

### `htmlreel fit my-reel.json`

Places each block of narration at the start of its shot, builds the track,
verifies it, and mixes the final cut.

```
  block 1   5.92 s   shot   0.0-  8.3   voice  0.35- 6.27   slack +2.03
  block 2   4.74 s   shot   8.3- 14.7   voice  8.65-13.39   slack +1.31
  block 3   2.61 s   shot  14.7- 18.8   voice 15.05-17.66   slack +1.14
  block 4   4.22 s   shot  18.8- 25.0   voice 19.15-23.37   slack +1.63
  block 5   2.73 s   shot  25.0- 30.0   voice 25.35-28.08   slack +1.92
```

The voice is never stretched, sped up or pitch-shifted. If a block does not
fit its shot, nothing is written and you are told which one and by how much —
not having the track is a smaller problem than having a wrong one that looks
finished.

`slack` is the breathing room at the end of each shot. Keep it comfortably
above your crossfade length, and give the closing shot more than the rest, or
the reel ends a tenth of a second after the last word.

## The config

```json
{
  "name": "launch",
  "page": "scene.html",
  "fps": 15,
  "duration": 30.0,
  "width": 1920,
  "height": 1080,
  "out": "out/launch",
  "vertical": { "background": "0x0F172A" },

  "voice": {
    "source": "voice.mp3",
    "music": "bed.wav",
    "music_volume": 0.55,
    "lead": 0.35,
    "cuts": [0.0, 8.3, 14.7, 18.8, 25.0, 30.0],
    "blocks": [
      { "start": 0.000, "end":  5.925 },
      { "start": 6.640, "end": 11.376 },
      { "start": 11.996, "end": 14.607 },
      { "start": 15.270, "end": 19.494 },
      { "start": 19.907, "end": 22.641, "note": "the address" }
    ]
  }
}
```

`cuts` holds the start of every shot plus the end of the reel, so it always
has one more entry than `blocks`. `lead` is how long after a cut the voice
comes in; it can be overridden per block. Paths are resolved relative to the
config file.

A block can have a pause shortened, when and only when it will not otherwise
fit:

```json
{ "start": 6.640, "end": 11.376, "trim": [[9.140, 9.840, 0.35]] }
```

That replaces the 0.70 s pause at 9.140 with 0.35 s. Reach for it last.
Internal pauses are the rhythm of the delivery, and cutting one is how a
piece starts to sound rushed.

## Try it

```bash
git clone https://github.com/iarodrigovigil-cloud/htmlreel
cd htmlreel
python -m htmlreel render examples/countdown/countdown.json
```

Five seconds, 75 frames, about a minute. Output lands in
`examples/countdown/out/`.

## Things that cost a day to find out

Written down because none of them are in anyone's documentation.

**Measure the voice before you fix the cuts.** Two takes of the same script by
the same voice differed by more than 20% — 0.337 against 0.409 seconds per
word. Cuts chosen before the recording exists are guesses, and a guess that is
wrong by half a second costs a full re-render. A word count tells you whether
a script *fits*. It tells you nothing you can cut on.

**Spoken numbers are faster than they look.** "One hundred and seventy-seven
thousand five hundred and seventy-three" is nine words and reads in 2.5
seconds — quicker per word than ordinary prose, not slower.

**Never pass `-v error` to a silencedetect command.** It suppresses the
filter's own output along with the banner. The command succeeds, prints
nothing, and you conclude there are no silences.

**`adelay` is the obvious way to offset a track and it silently did nothing.**
Generating the gaps as explicit silence and concatenating always works.

**Generated silence must be mono.** Concatenate stereo silence with a mono
recording and the result comes out about 3 dB below everything else you have
published — the kind of fault nobody notices until the whole series is out.

**Verify at the cuts, not at the blocks.** Matching runs of sound back to
blocks is guesswork: a block whose internal pause is longer than the
detector's window looks like two blocks, and treating the first as the block's
end makes the check pass when it should fail. What must be true needs no
matching — *the track is silent at every cut*.

**Three browsers at a time, not eight.** At eight the machine saturated and
launches began to hang. Slower per frame, but it finishes.

## Requirements

Python 3.8+, and Chrome, Chromium or Edge plus ffmpeg on `PATH`. Override the
lookup with `HTMLREEL_CHROME`, `HTMLREEL_FFMPEG` and `HTMLREEL_FFPROBE`.

## What this is not

Not a motion-graphics tool and not a timeline editor. There is no scene
graph, no easing library and no preview scrubber — your page is the scene
graph and your browser is the preview. It suits short, text-heavy, mostly
typographic pieces where the layout is easier to write as HTML and CSS than to
build by hand, and where the same piece gets re-cut repeatedly.

If you need keyframed motion or compositing, use a tool built for that.

## Licence

MIT.
