# fm-multi-drop

Get **N cards per duel win** in *Yu-Gi-Oh! Forbidden Memories* (US) instead of one.

Give it a disc image of the normal **Kuriboh mod** (or the stock US game) and a number, and it writes a
**new** disc image where every duel win hands out that many cards. Your original file is never modified.

```
fm-multi-drop "YFM MOD KURIBOH.iso" --drops 10
```

> This repository contains **no game data**: no disc images, no executables, no BIOS files.
> You must supply your own copy of the game/mod. See [Legal](#legal).

## What you get

- **`--drops N`** = total cards per win, *including* the game's normal drop (`--drops 10` → 10 cards).
- The game's own reward logic is reused for every extra card, so its rules stay intact:
  wins that give a guaranteed "signature" card give **N copies** of it; other wins give N cards from the
  opponent's normal drop table.
- Nothing else about the game changes. Check your card list after a win to see everything you received.
  (The game stores at most 250 copies of any card.)

## Requirements

- **Python 3.9 or newer** (no other packages are needed).
- **Your own disc image** in raw 2352-byte/sector format (usually `.iso` or `.bin`) of the
  Kuriboh mod (normal mode) or the stock US release.
- About **1 GB free disk space** (the output is a full copy with two sectors changed).
- An emulator to play it (for example DuckStation).

## Setup

**Option A: clone and run the setup script** (checks your Python, creates a virtual environment, installs):

```
git clone https://github.com/mohammeddahhani/fm-multi-drop
cd fm-multi-drop
./setup.sh          # Linux / macOS / WSL
setup.bat           # Windows (double-click or run in a terminal)
```

If Python is missing or too old, the script tells you what to install and stops.
After setup, run the tool with `.venv/bin/fm-multi-drop` (Windows: `.venv\Scripts\fm-multi-drop.exe`),
or activate the environment first (`source .venv/bin/activate` / `.venv\Scripts\activate`) and use
`fm-multi-drop`.

**Option B: install straight from GitHub** with [pipx](https://pipx.pypa.io/):

```
pipx install git+https://github.com/mohammeddahhani/fm-multi-drop
```

**Option C: no install at all** (from a clone of the repo):

```
PYTHONPATH=src python3 -m fm_multi_drop --help                 # Linux / macOS / WSL
$env:PYTHONPATH="src"; python -m fm_multi_drop --help          # Windows PowerShell
```

Check the installation any time with `fm-multi-drop --self-test`.

## Usage

```
fm-multi-drop DISC --drops N [-o OUTPUT] [--force]
fm-multi-drop DISC --check
```

| Option | Meaning |
|---|---|
| `DISC` | your disc image (raw 2352-byte/sector `.iso` / `.bin`; for a `.cue/.bin` pair give the `.bin`) |
| `-n`, `--drops N` | cards per duel win, 1 to 255 (sensible values are roughly 2 to 20) |
| `-o`, `--output FILE` | where to write the result (default: `<DISC>.<N>drops.<ext>` next to the input) |
| `-f`, `--force` | overwrite the output if it already exists |
| `--check` | only check whether the disc can be patched; writes nothing |
| `--self-test` | verify the installation |

Examples:

```
fm-multi-drop "YFM MOD KURIBOH.iso" --check
fm-multi-drop "YFM MOD KURIBOH.iso" --drops 10
fm-multi-drop "YFM MOD KURIBOH.10drops.iso" --drops 5 -o "YFM MOD KURIBOH.5drops.iso"   # change the number
```

It usually takes well under a minute: it copies the image, patches it, then re-reads it to verify.

## What is supported

| Disc | Result |
|---|---|
| Kuriboh mod, **normal** mode | supported |
| Stock US *Forbidden Memories* (SLUS_014.11) | supported |
| Output of this tool | supported (run it again to change N) |
| Kuriboh **Pharaoh (Hard)** / **GOD** discs, other mods with a modified game executable | **refused** with an explanation (their executable is different) |
| Other regions, 2048-byte-sector ISOs | refused |

The tool recognises the game executable by its SHA-256, so it needs no reference files and will not touch
anything it does not recognise.

## Safety

- The input file is never written to. The output is built as `<output>.partial` and only renamed once it passed
  verification; on any error nothing is left behind.
- Verification re-reads the result and checks that the patch is present, that the rewritten sectors have valid
  checksums (EDC/ECC), and that **only** the intended sectors differ (two out of about 220,000).
- **Back up your memory card / save files** before using a new disc image with a save you care about.
- Untested on real hardware; use an emulator.

## Status

Beta. The patch logic has been checked with unit tests, an emulator-based register/memory test, and byte-for-byte
comparison against the earlier research build. An earlier revision of the same patch (without the
invalid-card guard) was played in DuckStation on the normal Kuriboh mod; please open an issue if something looks
wrong in your game.

`setup.sh` was tested on Linux (Ubuntu under WSL, Python 3.12). `setup.bat` has not been tested on Windows yet.

More detail: [How it works](docs/HOW_IT_WORKS.md) · [Development](docs/DEVELOPING.md)

## Legal

This is an unofficial fan tool, not affiliated with or endorsed by Konami or by the authors of the Kuriboh mod.
It contains no copyrighted game data: it edits a disc image **that you provide** and that you have the right to
use. Do not ask for, or share, game files or BIOS images in this repository's issues. The Kuriboh mod is the work
of its own authors; this tool only changes how many cards a win gives.

Licensed under the [MIT License](LICENSE).
