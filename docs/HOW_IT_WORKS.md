# How it works

## The game's reward code (US `SLUS_014.11`)

After a duel win the game does this, once:

1. `PickWeightedCard` (0x80021810) rolls a number 1-2048 and walks the opponent's 722-entry weight table
   to choose a card. It then applies a per-duelist "guaranteed card" override (table at 0x801db330); when the
   override applies, the pick is replaced by that card.
2. The caller stores the pick in the duel state, and later calls `GrantCard` (0x80021894), which increments
   the owned-copies counter for that card and pushes it into a "recently obtained" list.

## The patch

One hook plus one small routine ("cave"), stored in unused zero padding of the executable
(0x801db038, source in [`asm/cave.s`](../asm/cave.s)):

- **Hook** at 0x80021c68 (right after the original pick): the game's `lw $a0, 0x2e0($gp)` is replaced by a jump to
  the cave, which reproduces that instruction's effect (reloads `$a0`) just before handing control back.
- **Cave**: saves *all* general registers and HI/LO on the stack, then repeats **N-1** times:
  `PickWeightedCard` (the game's own picker, override included) → if the result is a real card (1-722)
  `GrantCard` it. Finally it restores every register, reloads `$a0` as the stolen instruction would have, and
  resumes the game. The game's own single grant then happens as usual → N cards in total.
- The drop count N is one byte at the start of the cave; the tool writes it. Nothing else is configurable.

### Why "invalid picks are skipped"

`GrantCard(0)` is not harmless: the counter for "card 0" sits at the byte right before card 1's counter, which
is the high byte of the **last deck slot**. Granting 0 adds 256 to that slot's card number and produces a
garbage card that crashes the game when selected. The game's override table only has entries for duel contexts
0-39; other contexts read past its end and can produce out-of-range numbers, so the cave never grants anything
outside 1-722. (These contexts were never seen reaching the reward code in the memory dumps we looked at; the guard is insurance.)

### Why the cave saves every register

The hook sits in the middle of a compiled function, so the code that follows expects its registers
(`$v0`, `$v1`, `$a0`, `$s0`, ...) exactly as they were. The functions the cave calls freely change several of
them (some even clobber callee-saved registers), so the cave restores the full register file. This is checked by
[`tools/emulator_check.py`](../tools/emulator_check.py): over hundreds of randomized machine states, all 32
registers and HI/LO at the resume point are identical to the unpatched game, `GrantCard` never receives an
invalid id, and nothing writes into the deck array. The only memory written is the card counters, the
recently-obtained list, the RNG seed and stack scratch below `$sp`.

Pitfalls found while developing this, kept as regression checks in [`tools/static_checks.py`](../tools/static_checks.py):
the PS1's R3000 CPU has a load-delay slot (a loaded register cannot be used by the very next instruction, and
emulators such as Unicorn do not model it), and hand-written assembly with `.set noreorder` must fill every
branch delay slot itself.

## Disc handling

- Images are raw 2352-byte sectors. The tool parses ISO9660 to find `SLUS_014.11` (its sector differs between
  discs), reads it, and accepts it only if it is byte-identical to the unmodified US executable once this
  tool's own patch (if present) is reverted. That is a SHA-256 check, so no reference file is needed.
- Only sectors whose data actually change are rewritten (the hook's and the cave's), and their EDC and ECC
  are recomputed. The EDC/ECC code was validated against real sectors (all 201 sampled sectors from an
  unmodified image reproduced bit for bit).
- Some source discs contain a sector with an invalid checksum already; untouched sectors are left as they are.

## Known limits

- Only the US release (`SLUS_014.11`) with an unmodified executable is recognised.
- The game's own original grant is left exactly as the game does it (no extra validation).
- Real-hardware behaviour is untested.
