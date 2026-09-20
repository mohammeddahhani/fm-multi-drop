# Development

```
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
python -m unittest discover -s tests -v            # no game files needed (synthetic discs)
```

## Layout

| Path | Purpose |
|---|---|
| `src/fm_multi_drop/sector.py` | CD-ROM XA Mode 2 Form 1 EDC / ECC |
| `src/fm_multi_drop/disc.py` | raw-image reader/writer with ISO9660 lookup |
| `src/fm_multi_drop/patch.py` | executable detection (SHA-256), apply / revert patch |
| `src/fm_multi_drop/cave_data.py` | **generated** patch bytes (from `asm/cave.s`) |
| `src/fm_multi_drop/cli.py` | command line, safe copy + verification |
| `asm/` | patch source + linker script |
| `tools/` | maintainer tools (below) |
| `tests/` | unit + CLI tests on synthetic images |

## Changing the patch

Needs the MIPS binutils (`apt install binutils-mips-linux-gnu`). Edit `asm/cave.s`, then:

```
python tools/build_cave.py          # regenerates src/fm_multi_drop/cave_data.py
python -m unittest discover -s tests
```

The test suite rebuilds the assembly and fails if `cave_data.py` is out of date. Keep the loop entry at
0x801db03c (the hook jumps there) and use the load-delay rules described in `HOW_IT_WORKS.md`.

## Checking a build against your own discs

The following use game files, so run them locally; **never commit their output**.

```
python tools/extract_slus.py "your unmodified disc.iso" /tmp/vanilla.slus
python tools/extract_slus.py "output.10drops.iso"        /tmp/patched.slus
python tools/static_checks.py /tmp/patched.slus                       # delay slots / load hazards
pip install unicorn                                                   # in a venv
python tools/emulator_check.py /tmp/patched.slus --vanilla /tmp/vanilla.slus --runs 500
```

`emulator_check.py` must pass (exit 0) for a good build. Note the sanity control: a cave that grants card 0 fails it.

## Keeping game data out of the repository

`.gitignore` blocks disc/save/BIOS file types. `tests/test_repo_hygiene.py` (and `tools/check_no_game_files.py`)
fail if any non-ignored file looks like game data. To also block it at commit time:

```
ln -s ../../tools/pre-commit .git/hooks/pre-commit
```
