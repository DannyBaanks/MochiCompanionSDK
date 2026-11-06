# MochiCompanionSDK — nested agent contract

Scope: this directory only. It overrides the ISyCo root contract where it is
stricter, and never where it is looser.

## What this repo is

A generator + validator for the DASAI Mega Mochi's AVI assets, driven from
Companion agent events. Source of truth for its own numbers:
`profiles/mochi-factory-v1.json`, measured from the 62 factory videos.

## Hard boundaries (unchanged since MOCHI-REA-02)

1. **DENY by default for any write to the device.** No edits to `ui.bin`,
   `playlist.lst`, `video/*.avi`, firmware or partitions. No flashing,
   formatting, repairing or updating.
2. Never execute binaries extracted from the device.
3. Never change the mount state of the volume without explicit authorization.
4. Never install system tooling without explicit authorization. This package
   is driven as `./mochic` from the repo root — do not `pip install` it.
5. USB MSC storage is **not** an interactive control channel. Do not present
   file-copy success as "the device did something".
6. Stop and ask for specific authorization when the next action requires a
   device write, a firmware change, an install, or anything irreversible.
7. `deploy.apply` is the only function that writes, and only into a path a
   human passed explicitly with a matching plan token. Tests and demos use
   `mktemp` fake volumes — keep it that way.

## Evidence discipline

* No hash / no raw output ⇒ not a fact. New measurements go to
  `evidence/<slug>_vN/` with `manifest.json` + `stdout.raw.txt` + a claims
  table, and must pass `evidence_tool.py verify`.
* Never reuse an evidence output path. Never rewrite a sealed pack: supersede
  it with `vN+1` and say what changed.
* Regenerating `profiles/*.json` rewrites an embedded UTC timestamp, which
  invalidates the SHA-256 recorded in older packs. If you re-run
  `tools/measure_corpus.py`, re-seal the pack that references it.
* Numbers in a claim must exist in a hashed artifact in the same pack.
* `guard_out()` in `tools/capture_cli.py` is the reason a re-run cannot destroy
  a sealed raw: a capture refuses to write into a pack directory that already
  has `manifest.json` unless `--fuerza` is passed. The 2026-11-06 incident
  (raw re-generated 6 min after sealing, 24 → 26 blocks, old bytes
  unrecoverable because this tree is not versioned) is documented in
  `evidence/cli_v0/CORRECCIONES.md`. Convention: open `evidence/<slug>_v1/`,
  mark the old pack `SUPERSEDED`, never rewrite a raw.

## Code rules

* Pure Python + PIL + numpy. No ffmpeg, no OpenCV in the read/validate path:
  the gate is structural identity with assets the firmware already plays, and
  that is checked on chunks, not on decoded pixels.
* Any constant in `writer.py`, `profile.py`, `render.py` or `bridge.py` must
  cite the measurement that produced it, in the comment or docstring. A
  constant without a measurement is a policy, and must say so.
* The container deviations that break a textbook AVI v1 parser are documented
  in `container.py` (56-byte `strh` with SHORT rects, 16-byte audio `strf`,
  `vprp` only on the video stream, record flags only in `idx1`, JPEG segment
  lengths big-endian). Do not "fix" them toward the spec.
* CLI exit codes are part of the contract (0 OK, 1 hard finding, 2 usage,
  3 unreadable input, 4 token gate, 5 refused because NOT_DEMONSTRATED).
  Changing one breaks every caller that branches on it.

## Verification before claiming done

```
python3 -m pytest tests/ -q          # must be green; 62 byte-exact round-trips
./mochic profile --control           # must report 0 factory files rejected
python3 tools/capture_refusals.py    # re-runs the exit-code 1/2/5 evidence
```

`GUIA.md`, `README.md` and `AGENTS.md` are hashed artifacts of
`evidence/cli_v0`: editing one of them invalidates that seal, so re-seal with
`evidence_tool.py build --force` (same claims, refreshed hashes) and append a
note to `evidence/cli_v0/CORRECCIONES.md`. Never touch a `stdout.raw.txt`.

A change to `writer.py` or `container.py` that keeps tests green but alters a
byte of the header is a regression: the byte-exact round-trip is the control.

## Open, do not assume

* Which stimulus plays which animation (MOCHI-REA-03, awaiting the physical
  B0–B6 captures).
* Whether the firmware accepts a generated file at all.
* The real frame-size and bitrate ceiling (only 31893 B / 745702 B/s observed).

