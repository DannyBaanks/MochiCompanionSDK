"""Lector/escritor RIFF-AVI del flavor que usa el DASAI Mega Mochi.

Formato medido en el corpus factory (ver mochisdk/profile.py): MJPEG en el
stream de video, PCM 16-bit 48 kHz mono en el de audio, intercalado 1:1 por
frame (3200 B de audio por frame de 1/30 s).

Lectura en Python puro, sin ffmpeg ni OpenCV: el gate del SDK es "este
contenedor es estructuralmente identico a los assets que el firmware ya
reproduce", y eso se comprueba comparando chunks, no decodificando pixels.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

AVIIF_HASINDEX = 0x00000010
AVIIF_ISINTERLEAVED = 0x00000100
AVIIF_KEYFRAME = 0x00000010
FCC_IDX1 = b"idx1"
FCC_JUNK = b"JUNK"


class AviError(ValueError):
    """El archivo no es un AVI RIFF interpretable."""


def _u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def _u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]


def _i16(b: bytes, o: int) -> int:
    return struct.unpack_from("<h", b, o)[0]


@dataclass
class Chunk:
    fcc: bytes
    size: int
    data: bytes
    offset: int
    body: int

    @property
    def next(self) -> int:
        return self.body + self.size + (self.size & 1)

    def children(self) -> list["Chunk"]:
        """Sub-chunks: salta el fourcc de forma cuando el cuerpo empieza con LIST/RIFF."""
        out: list[Chunk] = []
        d = self.data
        pos = 0
        if self.fcc in (b"RIFF", b"LIST") and len(d) >= 4:
            pos = 4
        while pos + 8 <= len(d):
            fcc = d[pos:pos + 4]
            size = _u32(d, pos + 4)
            if pos + 8 + size > len(d):
                break
            out.append(Chunk(fcc, size, d[pos + 8:pos + 8 + size], self.body + pos, self.body + pos + 8))
            pos += 8 + size + (size & 1)
        return out


def read_chunks(buf: bytes, off: int = 0, end: int | None = None, skip_form: bool = True) -> list[Chunk]:
    """Lista de chunks contiguos en [off, end)."""
    end = len(buf) if end is None else min(end, len(buf))
    out: list[Chunk] = []
    pos = off
    if skip_form and end - off >= 4 and buf[off:off + 4] in (b"AVI ", b"on2 "):
        pos = off + 4
    while pos + 8 <= end:
        fcc = buf[pos:pos + 4]
        size = _u32(buf, pos + 4)
        if pos + 8 + size > end:
            break
        out.append(Chunk(fcc, size, buf[pos + 8:pos + 8 + size], pos, pos + 8))
        pos += 8 + size + (size & 1)
    return out


@dataclass
class StreamHeader:
    """strh medido en el corpus Mochi: 56 bytes, rcFrame empaquetado en int16.

    El estándar Windows AVI define strh en 64 bytes con RECT de LONGs. El
    muxer Synwit escribe 48 bytes de campos + rcFrame de 4 x int16 (8 bytes).
    Es una desviacion medida, no un error de lectura: ver mochisdk/profile.py.
    """
    fcc_type: bytes
    fcc_handler: bytes
    flags: int
    priority: int
    language: int
    initial_frames: int
    scale: int
    rate: int
    start: int
    length: int
    suggested_buf: int
    quality: int
    sample_size: int
    rect: tuple = (0, 0, 0, 0)
    size: int = 0

    @property
    def fps(self) -> float:
        return float(self.rate) / self.scale if self.scale else 0.0


@dataclass
class BitmapInfo:
    """strf de video: BITMAPINFOHEADER."""
    size: int
    width: int
    height: int
    planes: int
    bitcount: int
    compression: bytes
    image_size: int
    xppm: int
    yppm: int
    clr_used: int
    clr_important: int

    @property
    def rgb(self) -> bool:
        return self.bitcount == 24 and self.compression in (b"\x00\x00\x00\x00", b"DIB ")


@dataclass
class PCMFormat:
    """strf de audio: WAVEFORMATEX."""
    format_tag: int
    channels: int
    samples_per_sec: int
    avg_bytes_per_sec: int
    block_align: int
    bits_per_sample: int

    @property
    def bytes_per_sec(self) -> int:
        return self.channels * self.samples_per_sec * (self.bits_per_sample // 8)


@dataclass
class Record:
    fcc: bytes
    flags: int
    data: bytes
    size: int = 0
    data_off: int = -1        # posicion absoluta del payload dentro del archivo
    header_off: int = -1      # posicion absoluta del fourcc del registro

    @property
    def kind(self) -> str:
        return {b"00db": "video", b"00dc": "video", b"01wb": "audio", b"00wb": "audio"}.get(self.fcc, "other")

    @property
    def keyframe(self) -> bool:
        return bool(self.flags & AVIIF_KEYFRAME)


@dataclass
class AviAsset:
    path: str | None
    avih: dict
    streams: list[StreamHeader]
    strf: list[object]
    junk: list[bytes]
    records: list[Record]
    idx1: list[tuple[bytes, int, int, int]]
    total_size: int
    raw_headers: bytes = b""
    movi_offset: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def video(self) -> list[Record]:
        return [r for r in self.records if r.kind == "video"]

    @property
    def audio(self) -> list[Record]:
        return [r for r in self.records if r.kind == "audio"]

    @property
    def audio_bytes(self) -> int:
        return sum(len(r.data) for r in self.audio)

    def pcm(self) -> bytes:
        return b"".join(r.data for r in self.audio)

    def jpeg_frames(self) -> list[bytes]:
        return [r.data for r in self.video]

    @property
    def duration_s(self) -> float:
        st = self.streams[0]
        return st.length / st.fps if st.fps else 0.0


def parse_avi(buf: bytes, path: str | None = None) -> AviAsset:
    buf = bytes(buf)          # acepta memoryview/bytearray: los payloads tienen que ser inmutables
    if buf[:4] != b"RIFF" or buf[8:12] != b"AVI ":
        raise AviError("no es RIFF/AVI: %r" % buf[:12])
    top = read_chunks(buf, 12, skip_form=False)
    hdrl = movi = None
    for c in top:
        if c.fcc == b"LIST" and c.data[:4] == b"hdrl":
            hdrl = c
        elif c.fcc == b"LIST" and c.data[:4] == b"movi":
            movi = c
    if hdrl is None:
        raise AviError("falta LIST hdrl")
    avih_c = next((c for c in hdrl.children() if c.fcc == b"avih"), None)
    if avih_c is None or avih_c.size < 56:
        raise AviError("falta o es corto el chunk avih")
    a = avih_c.data
    avih = {
        "microsec_per_frame": _u32(a, 0),
        "max_bytes_per_sec": _u32(a, 4),
        "padding_granularity": _u32(a, 8),
        "flags": _u32(a, 12),
        "total_frames": _u32(a, 16),
        "initial_streams": _u32(a, 20),
        "streams": _u32(a, 24),
        "suggested_buf_size": _u32(a, 28),
        "width": _u32(a, 32),
        "height": _u32(a, 36),
    }
    for k in (40, 44, 48, 52):
        avih["reserved_%d" % (k // 4)] = _u32(a, k)

    streams: list[StreamHeader] = []
    strf: list[object] = []
    junk: list[bytes] = []
    for sl in hdrl.children():
        if not (sl.fcc == b"LIST" and sl.data[:4] == b"strl"):
            continue
        sh = next((c for c in sl.children() if c.fcc == b"strh"), None)
        sf = next((c for c in sl.children() if c.fcc == b"strf"), None)
        jk = [c for c in sl.children() if c.fcc == FCC_JUNK]
        junk.extend(c.data for c in jk)
        if sh is None or sh.size < 48:
            raise AviError("strl sin strh valido")
        h = sh.data
        streams.append(StreamHeader(
            fcc_type=h[0:4], fcc_handler=h[4:8], flags=_u32(h, 8),
            priority=_u16(h, 12), language=_u16(h, 14), initial_frames=_u32(h, 16),
            scale=_u32(h, 20), rate=_u32(h, 24), start=_u32(h, 28), length=_u32(h, 32),
            suggested_buf=_u32(h, 36), quality=_i32_or_u32(h, 40), sample_size=_u32(h, 44),
            rect=_read_rect(h, 48), size=sh.size))
        if sf is None:
            raise AviError("strl sin strf")
        if h[0:4] == b"vids":
            f = sf.data
            strf.append(BitmapInfo(_u32(f, 0), _i32_or_u32(f, 4), _i32_or_u32(f, 8), _u16(f, 12),
                                   _u16(f, 14), f[16:20], _u32(f, 20), _u32(f, 24), _u32(f, 28),
                                   _u32(f, 32), _u32(f, 36)))
        elif h[0:4] == b"auds":
            f = sf.data
            strf.append(PCMFormat(_u16(f, 0), _u16(f, 2), _u32(f, 4), _u32(f, 8), _u16(f, 12), _u16(f, 14)))
        else:
            strf.append(f"raw:{sf.data.hex()}")

    records: list[Record] = []
    movi_off = 0
    if movi is not None:
        movi_off = movi.body + 4
        records = _read_movi(buf, movi_off, min(movi.body + movi.size, len(buf)))
    idx1 = _read_idx1(buf)
    _apply_idx1_flags(records, idx1, movi_off - 4)

    return AviAsset(path=path, avih=avih, streams=streams, strf=strf, junk=junk, records=records,
                    idx1=idx1, total_size=len(buf), movi_offset=movi_off)


def _apply_idx1_flags(records: list[Record], idx1: list[tuple[bytes, int, int, int]], anchor: int) -> None:
    """Los flags (AVIIF_KEYFRAME etc.) viven en idx1, no en el registro de movi.

    dwOffset del idx1 se mide desde la etiqueta 'movi' (no desde el primer
    chunk), asi que el primer registro figura en offset 4. Medido en el corpus.
    """
    i = 0
    pos = anchor + 4
    for r in records:
        while i < len(idx1) and idx1[i][2] < pos - anchor:
            i += 1
        if i < len(idx1):
            fcc, flags, off, size = idx1[i]
            if fcc == r.fcc and off == pos - anchor and size == r.size:
                r.flags = flags
                i += 1
        pos += 8 + r.size + (r.size & 1)


def _read_rect(b: bytes, o: int) -> tuple:
    """rcFrame: 4 x int16 en el strh de 56 bytes del muxer Synwit, 4 x int32 en el de 64."""
    if len(b) - o >= 16:
        return tuple(_i32_or_u32(b, o + 4 * i) for i in range(4))
    return tuple(_i16(b, o + 2 * i) for i in range(4) if o + 2 * i + 2 <= len(b))


def _i32_or_u32(b: bytes, o: int) -> int:
    v = _u32(b, o)
    return v - (1 << 32) if v >= (1 << 31) else v


def load_avi(path: str) -> AviAsset:
    with open(path, "rb") as fh:
        buf = fh.read()
    return parse_avi(buf, path=path)


def _read_movi(buf: bytes, off: int, end: int) -> list[Record]:
    """Registros de movi: fourcc + size + datos, con relleno a par.

    En AVI v1 el propio registro no lleva flags; los pone el idx1.
    Un size que desborde el movi corta el listado (marker de truncamiento).
    """
    out: list[Record] = []
    pos = off
    while pos + 8 <= end:
        fcc = buf[pos:pos + 4]
        size = _u32(buf, pos + 4)
        if pos + 8 + size > end:
            break
        out.append(Record(fcc=fcc, flags=0, data=buf[pos + 8:pos + 8 + size], size=size,
                          data_off=pos + 8, header_off=pos))
        pos += 8 + size + (size & 1)
    return out


def _read_idx1(buf: bytes) -> list[tuple[bytes, int, int, int]]:
    pos = buf.rfind(FCC_IDX1)
    if pos < 0:
        return []
    size = _u32(buf, pos + 4)
    body = buf[pos + 8:pos + 8 + size]
    if len(body) < size:
        return []
    out = []
    for i in range(0, size - size % 16, 16):
        c = body[i:i + 4]
        out.append((c, _u32(body, i + 4), _u32(body, i + 8), _u32(body, i + 12)))
    return out
