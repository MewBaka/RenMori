# Threat model (read this before promising anything)

renmori is honest about what client-side protection can and cannot do. This
document is the reference for the claims the project — and its marketing — are
allowed to make.

## The premise you cannot escape

A Ren'Py game runs on the player's machine. To run, the engine must read its own
assets, so:

- the decryption logic ships with the game, and
- the key material is derivable on the client (it has to be — nothing else can
  decrypt), and
- the final rendered frames and the decoded audio exist in memory and on screen.

Therefore **no client-side tool can make a game uncrackable.** A skilled,
determined attacker with the shipped binary, a debugger, and enough time will
eventually extract any single asset from any single game. This is the white-box
problem, and every local DRM scheme in history has eventually fallen to it.
Anyone who tells you otherwise is selling snake oil.

## What renmori actually changes

The realistic levers, in order of value:

1. **Defeat the off-the-shelf tools.** `unrpa`, `rpatool`, `RenPack`,
   `RenpyEx`, `unrpyc` (incl. `--try-harder` and `un.rpyc` injection) fail on a
   protected build. This matters because the overwhelming majority of real
   "asset rip" and "script leak" incidents are just someone running one of these.
   An agent that only knows how to call these tools is in the same bucket.

2. **Make breaks non-portable.** Per-build polymorphism means reverse
   engineering one game produces a tool for *that game, that version* — not a
   reusable unpacker. There is no "renmori unpacker" to be shared on a forum.

3. **Make old breaks age out.** Each release rotates the scheme, so a leaked or
   reversed older build doesn't help against new ones.

4. **No plaintext on disk.** At no point is any file (fonts included) sitting
   decrypted on the filesystem.

## Attacks renmori does NOT stop

State these plainly to customers:

- **Screen capture / video capture** of what's displayed. Unstoppable by
  definition.
- **Memory ripping** by a skilled attacker (e.g. NinjaRipper-class tools against
  the running process). Lazy chunked decryption raises the cost but does not
  prevent it.
- **A dedicated expert** targeting one specific game and willing to spend the
  time. They can win against that one game/version. They just can't turn the win
  into a universal tool.

Truly stopping injected extractors would require kernel-level anti-cheat, which
is out of scope, hostile to players, and incompatible with the performance-first
and Steam-Deck/Proton goals.

## The claim the project is allowed to make

> renmori makes every standard Ren'Py unpacking and decompiling tool fail, leaves
> no plaintext on disk, and makes every build different so that no universal
> unpacker can exist. It raises the cost of extraction to dedicated, per-game,
> per-version expert effort. It does not and cannot make a game uncrackable.

Anything stronger than that is not supportable and must not appear in docs,
README, or marketing. The EULA carries a matching no-warranty-of-unbreakability
clause.
