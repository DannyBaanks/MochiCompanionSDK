# MochiCompanionSDK

**Give your DASAI Mega Mochi new animations — generated straight from your AI agent.**

Type a spec, get a 480×480 / 30 fps MJPEG clip that the firmware accepts, and put it on the
toy through a gate that refuses anything it cannot prove is safe. No ffmpeg, no OpenCV, no
cloud service, no firmware flashing, no `pip install`.

```bash
./mochic build examples/demo-thinking.json                        # spec -> AVI (writes only in build/)
./mochic plan /media/$USER/MEGAMOCHI examples/demo-thinking.json   # read-only -> token
./mochic apply build/plan-<token>.json --token <token>             # the only command that writes
./mochic rollback .mochisdk-backup/journal-<stamp>-<token>.json    # undo it
```

Spanish operator guide (step by step, with every real output): [`GUIA.md`](GUIA.md).

---

## What it is for

The Mega Mochi ships 62 animation clips on a USB Mass-Storage volume plus a boot clip. The
volume is ordinary FAT — you can drop files in — but the firmware is picky about the container,
and nobody publishes the format it expects. This SDK reverse-engineered it by measuring all 63
shipped files and turned the result into three things:

1. **A generator** that writes AVIs matching that measurement byte-for-byte in the header.
2. **A validator** that grades any candidate file against it before it ever touches the device.
3. **A deploy gate** that requires a token, backs the original up outside the volume, writes
   atomically, re-reads the SHA-256 it just wrote, and restores the backup if the hash disagrees.

Then it puts an agent on the other end: the Mochi's companion daemon emits
`companion-event-v1` events, and `mochic watch` turns each one into a rendered clip and a plan.
The agent path can *never* write to the device — only a human running `apply` can.

## Requirements

| | |
|---|---|
| Python | 3.10+ (everything here was actually run on 3.12.3) |
| Required | Pillow 12.x, numpy 2.x |
| Optional | PyYAML — only for `.yaml`/`.yml` specs |
| Art | A Companion pet pack (a folder with one GIF per animation, e.g. `malbolgato-idle.gif`) — or any GIF you point a spec at |
| Device | A DASAI Mega Mochi plugged in over USB, mounted read-write |

Clone and run in place; `./mochic` puts the repo root on `sys.path`:

```bash
git clone https://github.com/DannyBaanks/MochiCompanionSDK.git
cd MochiCompanionSDK
python3 -m venv .venv && . .venv/bin/activate
pip install pillow numpy pyyaml
./mochic version
```

## Quickstart

**1 — Make sure the tool agrees with your toy.** `profile --control` replays every factory rule
over the 62 clips already on the device. If this is green, the rules describe *your* firmware,
not a guess:

```
$ ./mochic profile --control --texto
perfil                   mochi-factory-v1
fuente                   ~/megamochi-backup/volume_files/video
corpus_sha256            0c05fea119d21611cb938b6485ddf093392ea4f34d4442b20bc8baa9b1c1d338
hechos                   n_archivos               62
bytes_corpus             113450456
fps                        - 30.0
dims                       -   - 480   - 480
handler_video              - MJPG
interleave_head          vavavavavava             62
suggested_buf_eq_max_frame true                     62
frame_max_absoluto       31893
real_max                 745702.0
control_positivo         archivos                 62
rechazados               0
veredicto                PASS
motivo                   un asset factory rechazado implica regla mala, no asset malo
```

**2 — Describe the clip you want.** A spec is a small JSON file; `examples/demo-thinking.json`
renders the `thinking` animation of a pet pack at 60 frames:

```json
{
 "spec": "mochi-anim-v1",
 "id": "demo-thinking",
 "nombre": "thinking -> Squint.avi",
 "fuente": {
  "tipo": "companion_pack",
  "pack": "../Companion/packs/malbolge-cat",
  "animacion": "thinking",
  "fotogramas": 60,
  "fondo": [8, 6, 14],
  "budget_bytes_por_frame": 24000,
  "resample": "lanczos",
  "audio": null
 },
 "destino": { "nombre_video": "Squint.avi", "salida": "build/demo-thinking.avi" }
}
```

`mochic spec --pack <dir> --animacion thinking --fotogramas 60 -o mine.json` writes one for you.

**3 — Build it.** The renderer resamples to 480×480, searches per-frame JPEG quality so each
frame lands under the budget, muxes PCM audio at 48 kHz, and then runs the validator on its own
output before reporting success:

```
$ ./mochic build examples/demo-thinking.json
{
  "animacion": "thinking",
  "budget_por_frame": 24000,
  "bytes_avi": 1594526,
  "duracion_s": 2.0,
  "frame_bytes": { "max": 23543, "min": 22419, "total": 1389572 },
  "frames": 60,
  "jpeg_quality": { "max": 93, "mediana": 92, "min": 91 },
  "nombre_video_destino": "Squint.avi",
  "ruta": "build/demo-thinking.avi",
  "sha256": "77a9df099345f584edfb1c6f31d9972b19d617bd11fe9b0885e006486eef6601",
  "siguiente_paso": "mochic plan VOLUMEN examples/demo-thinking.json",
  "validacion": { "duros": 0, "suaves": 1, "valido": true }
}
exit=0
```

The one soft finding is honest and expected: at 24 000 B/frame this clip streams at 797 263 B/s,
above the **745 702 B/s** peak observed on factory files. Soft findings never block you; hard
findings do. Lower `budget_bytes_por_frame` if you want it clean.

**4 — Plan, then apply.** `plan` opens the volume read-only, records the current SHA-256 of every
destination, and hands you a token bound to exactly those bytes:

```
./mochic plan /media/$USER/MEGAMOCHI --par build/demo-thinking.avi video/Squint.avi --salida plan.json
./mochic apply plan.json --token <token de plan.json> --copia ~/megamochi-backup/deploy_$(date +%F)
```

`apply` refuses if the destination changed since the plan, copies the original outside the volume
and verifies that copy byte-for-byte, writes `tmp` + `fsync` + `os.replace`, then re-reads the
destination. Any mismatch restores the backup and exits non-zero. Each applied write leaves its
own journal — `journal-<utc-stamp>-<token>.json` inside the backup folder, or wherever you point
`--diario` — and that journal is what `rollback` consumes.

To replace the boot clip instead, target `startup.avi`. It plays on power-up, which makes it the
fastest way to see your own render on stock firmware — no playlist edits needed.

## Put an agent on it

`emit` fakes an event for testing, `watch` consumes a real companion inbox:

```bash
./mochic emit state --value thinking --inbox ./inbox.jsonl
./mochic watch --pack ../Companion/packs/malbolge-cat --volumen /media/$USER/MEGAMOCHI --outbox ./outbox.jsonl
./mochic map --mostrar            # which animation maps to which shipped slot
```

`mochic map --mostrar` shows the table the bridge uses: `idle → Blink.avi`,
`thinking → Squint.avi`, `working → Revs.avi`, `waiting → Sleepy.avi`, `success → Smile.avi`,
`error → Crying.avi`, `drag → UpsideDown.avi`, `running-left → Look Left.avi`,
`running-right → Look Right.avi`. `watch` renders and plans per event and posts status back to a
local outbox. **It never writes the volume** — that split is enforced in code, not by convention.

## How the pieces fit

```
   Companion event (companion-event-v1)            you, at a terminal
            │                                        │
            ▼                                        ▼
      mochisdk/bridge.py ──────► spec mochi-anim-v1 ◄── mochic spec
                                       │
                                       ▼
                                mochisdk/render.py ── 480×480, 30 fps
                                 JPEG budget search   MJPEG + PCM 48 kHz
                                       │                    ▲
                                       ▼                    │
                                mochisdk/writer.py ─────────┘
                              (header byte-exact vs. the factory corpus)
                                       │
                                       ▼
                profile.validate ──► deploy.plan (token) ──► deploy.apply ──► rollback
                 hard rules                read-only            only writer        journal
```

| Module | Job |
|---|---|
| `container.py` | strict pure-Python RIFF/AVI reader/walk — the measuring instrument |
| `writer.py` | muxer that reproduces the factory flavor (62/62 byte-exact round-trip) |
| `profile.py` | validator; hard rules are **derived relations**, soft rules cite their sample size |
| `playlist.py` | `playlist.lst` = 62 × 128 B fixed records, byte-exact round-trip |
| `spec.py` | `mochi-anim-v1`, the declarative recipe |
| `render.py` | pack/GIF → frames → JPEG budget search → AVI, then validates its own output |
| `deploy.py` | `plan` / `apply` / `rollback`, with the token gate and the journal |
| `bridge.py` | `companion-event-v1` → spec → render → plan; cannot write |
| `cli.py` + `mochic` | stable command surface and exit codes |
| `tools/` | foreign-file diagnostics, single-field repair, sealed evidence capture |

## The container you get (and how it was measured)

Every constant comes from measuring the files that ship on the device — 62 videos
(113 450 456 B) plus `startup.avi` — never from a datasheet or a guess.

| Property | Value | Backing |
|---|---|---|
| Video codec | MJPEG, baseline SOF0, 8-bit, 4:2:0 | 9 650/9 650 frames walked |
| Resolution / rate | 480×480, `strh` scale 1 / rate 30 (exactly 30 fps) | 63/63 |
| Audio | PCM 16-bit, 48 kHz | 63/63 |
| Channels | mono in the 62 playlist clips, **stereo** in the factory boot clip | 63 files |
| Audio per frame | `avg_bytes_per_sec / fps` → 3200 B mono, 6400 B stereo | 63/63 |
| Interleave | one video chunk + one audio chunk per frame, trailing zero-size `01wb` | 63/63 |
| Index | complete `idx1`, one entry per record, every frame a keyframe | 63/63 |
| `strh.vids.suggested_buf` | equals the largest JPEG frame in that file | 63/63 |
| Header tree | one blueprint across all 63; 8 constant chunk payloads measured over the 62 | RIFF walk |
| `max_bytes_per_sec` | 121000 (playlist) / 217000 (boot) — a placeholder either way; real peak 745 702 B/s | measured |
| Largest frame ever played | 31 893 B | measured |

Those relations earned their keep twice. The validator rejected the factory's own boot clip
because "mono" was a 62-of-63 coincidence dressed up as an invariant — the bug was in our rule,
and it is now a derived relation (`block_align == channels·bits/8`, `strh.rate ==
samples_per_sec`, `suggested_buf == largest frame`, and the rest). A separate self-inconsistency
in one third-party file's header was diagnosed the same way and repaired by `tools/fix_suggested_buf.py`
rather than by loosening the gate.

## Safety model

- **DENY by default.** Nothing writes to the device except `mochic apply`, with an explicit
  destination and a matching token. Tests and demos use `mktemp` fake volumes.
- **Two steps, one human.** `plan` is read-only and produces the token; `apply` consumes it and
  re-checks that the destination still matches. `exit 4` means the token gate stopped you.
- **Backup before write, verify after.** Outside the volume, byte-verified both ways. Backups are
  named `destination__previous-hash`, and `rollback` checks the backup against the state it is
  supposed to restore *before* copying it — so two writes to the same slot stay independently
  reversible, and a journal whose backup was tampered with refuses to write anything.
- **No playlist growth.** Adding entries to `playlist.lst` is refused (exit 5): the firmware has
  never been observed with any number of entries other than 62.
- **No firmware contact.** This tool only ever talks to a FAT volume. It does not flash, patch,
  or execute anything from the device, and USB MSC is storage — not a control channel. A file
  landing on the volume is not proof the toy did anything.
- **Exit codes are a contract.** `0` OK · `1` hard finding · `2` usage · `3` unreadable input ·
  `4` token mismatch · `5` refused because not demonstrated.

## Proven on hardware

Claims are scoped, and unproven ones say so. Each row traces to a hashed evidence pack —
`manifest.json` with SHA-256 of every artifact, `stdout.raw.txt` never rewritten, `VERDICT.md`
with hypotheses, controls and a claims table.

| Pack | Claim | Status |
|---|---|---|
| `evidence/profile_v1/` | the container measurement; the profile is byte-reproducible from the corpus | PASS |
| `evidence/cli_v0/` | the command surface, the event bridge, deploy + rollback on tmp volumes | PASS |
| `evidence/refusals_v0/` | exit codes 1 / 2 / 5, each with a positive control beside the rejection | PASS |
| `evidence/foreign_startup_v0/` | the white-screen experiment, inputs frozen by SHA-256 before analysis | PASS |
| `evidence/startup_write_v0/` | the first authorized device write, through the gate, backup verified | PASS |
| `evidence/boot_play_v0/` | stock firmware plays a non-factory AVI at the boot slot | CONDITIONAL_PASS |
| `evidence/our_build_v0/` | three authorized writes through the gate; the install chain is deterministic; budget/quality trade-off measured | PASS |
| `evidence/our_build_v1/` | the bytes on the device are byte-for-byte what `spec → build` produces here, reproduced hours later | PASS |
| `evidence/our_build_v1/` | an AVI built by this SDK plays at boot — the operator watched it; no camera capture sealed | CONDITIONAL_PASS |
| `evidence/our_build_v1/` | **refuted:** two writes to the same slot used to share one backup file, which silently destroyed the first journal's rollback target | FAIL, fixed + controlled |
| — | that the audio track of the boot clip we installed was actually audible | NOT_DEMONSTRATED |
| — | which physical stimulus triggers each of the 62 animations | NOT_DEMONSTRATED |
| — | that a *playlist* slot built by this SDK plays (the file is on the device; its trigger is unknown) | NOT_DEMONSTRATED |

Re-verify any pack:

```bash
SKILL=<path>/openisy-researcher/scripts/evidence_tool.py
python3 "$SKILL" verify evidence/profile_v1
python3 "$SKILL" verify evidence/cli_v0
```

`evidence/profile_v0/` deliberately reports **FAIL**: three hash mismatches document drift that
its `CORRECCIONES.md` explains. It is superseded, not broken — don't "fix" it.

## Tests

```bash
python3 -m pytest tests/ -q      # 184 passed
./mochic profile --control       # 62 factory files, 0 rejected
python3 tools/capture_refusals.py # the exit-code 1/2/5 evidence, re-run
```

The suite never mounts or touches a real device: every deploy test runs against a `mktemp`
volume. The byte-exact round-trip over the 62 factory files is the regression control — a change
to `writer.py` that keeps tests green but alters a header byte *is* a regression.

## Layout

```
mochic              one entrypoint, no install
mochisdk/           container, writer, profile, playlist, spec, render, deploy, bridge, cli
profiles/           mochi-factory-v1.json — the measured source of truth
examples/           a runnable spec
tests/              184 tests, tmp volumes only
tools/              diagnostics, single-field repair, sealed evidence capture
evidence/           hashed packs: the raw output behind every number in this file
GUIA.md             Spanish operator guide — every command, with its real output
```

## Honest limits

- **Storage, not control.** The Mochi is a FAT volume to this SDK. It cannot make the toy play
  something, query its state, or change its behaviour. Dropping a file and watching it appear on
  screen are two different claims, and this README keeps them separate.
- **Trigger logic unknown.** Which stimulus maps to which of the 62 clips has not been
  established; replacing a file in a slot is safe *because* the slot still exists, but you cannot
  force the toy to show it on demand.
- **Overwrite only.** One existing slot per generated clip. New animations need a playlist entry,
  and that is refused until the firmware's tolerance is measured.
- **Audio comes from WAV.** 16-bit PCM 48 kHz, mono or stereo; the renderer resamples and pads, it
  does not synthesize.
- **Real ceilings unmeasured.** Frame size and bitrate are bounded by what factory files already
  play (31 893 B / 745 702 B/s observed), not by any known hardware limit.
- **Hot-unplug wedges MSC.** Unplugging the toy while powered can leave the volume unreadable
  (`-71` enumeration loop). Recovery is a power-off, 60 s unplug, reconnect, power on with the
  side switch in the right position. Details in `GUIA.md`.
- **FAT stays dirty.** Nothing here runs `fsck.vfat`; it is not needed to write files, and
  repairing the volume was never authorized.

## License

MIT — see [`LICENSE`](LICENSE).
