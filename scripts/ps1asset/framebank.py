#!/usr/bin/env python3
"""Full-frame, 256-color animation banks with lossless RLE and frame deduplication.

Every input frame retains a directory entry, including repeated/held frames.
Palette reduction is explicit; compression never drops frames or changes pixels.
"""
from __future__ import annotations
import struct
from PIL import Image
from png_to_tim import psx_color

MAGIC = b'FBK1'
HEADER = struct.Struct('<4sIHHHH')

def rle_encode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        run = 1
        while i + run < len(data) and run < 128 and data[i + run] == data[i]:
            run += 1
        if run >= 3:
            out.extend((0x80 | (run - 1), data[i]))
            i += run
            continue
        start = i
        i += run
        while i < len(data) and i - start < 128:
            if i + 2 < len(data) and data[i] == data[i+1] == data[i+2]:
                break
            i += 1
        out.append(i - start - 1)
        out.extend(data[start:i])
    return bytes(out)

def rle_decode(data: bytes, size: int) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        command = data[i]
        i += 1
        count = (command & 127) + 1
        if len(out) + count > size:
            raise ValueError('RLE exceeds frame buffer')
        if command & 128:
            if i == len(data): raise ValueError('truncated RLE run')
            out.extend(bytes([data[i]]) * count)
            i += 1
        else:
            if i + count > len(data): raise ValueError('truncated RLE literal')
            out.extend(data[i:i+count])
            i += count
    if len(out) != size: raise ValueError('incomplete RLE frame')
    return bytes(out)

def pack_indices(width: int, height: int, palette: list[int], frames: list[bytes]) -> bytes:
    if width < 1 or height < 1 or width > 256 or height > 256 or width % 2:
        raise ValueError('8-bit texture dimensions must fit 256x256; width must be even')
    if len(palette) != 256 or not 1 <= len(frames) <= 65535:
        raise ValueError('expected 256 palette entries and 1..65535 frames')
    start = HEADER.size + 512 + 8 * len(frames)
    table = bytearray()
    payload = bytearray()
    seen = {}
    for frame in frames:
        if len(frame) != width * height: raise ValueError('frame dimensions differ')
        if frame not in seen:
            encoded = rle_encode(frame)
            if rle_decode(encoded, len(frame)) != frame: raise ValueError('codec verification failed')
            seen[frame] = (start + len(payload), len(encoded))
            payload.extend(encoded)
        table.extend(struct.pack('<II', *seen[frame]))
    return (HEADER.pack(MAGIC, start + len(payload), width, height, len(frames), 256)
            + struct.pack('<256H', *palette) + table + payload)

def unpack_indices(data: bytes) -> tuple[int, int, list[int], list[bytes]]:
    magic, total, width, height, count, colors = HEADER.unpack_from(data)
    if magic != MAGIC or total != len(data) or colors != 256 or not count:
        raise ValueError('invalid frame bank')
    start = HEADER.size + 512 + count * 8
    palette = list(struct.unpack_from('<256H', data, HEADER.size))
    frames = []
    for i in range(count):
        offset, size = struct.unpack_from('<II', data, HEADER.size + 512 + i * 8)
        if offset < start or offset + size > len(data): raise ValueError('invalid frame range')
        frames.append(rle_decode(data[offset:offset+size], width * height))
    return width, height, palette, frames

def encode_images(frames: list[Image.Image]) -> tuple[bytes, dict]:
    if not frames or any(f.size != frames[0].size for f in frames):
        raise ValueError('all frames must share a canvas')
    width, height = frames[0].size
    rgba = [f.convert('RGBA') for f in frames]
    # One palette for the entire bank prevents per-frame palette flicker.
    contact = Image.new('RGB', (width * 8, height * ((len(rgba)+7)//8)))
    for i, frame in enumerate(rgba):
        contact.paste(frame.convert('RGB'), ((i % 8)*width, (i // 8)*height))
    quantized = contact.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rgb = (quantized.getpalette() or [])
    rgb = (rgb + [0] * 768)[:768]
    palette = [0] + [psx_color(*rgb[i*3:i*3+3], 255) for i in range(255)]
    indexed = []
    for i, frame in enumerate(rgba):
        tile = quantized.crop(((i % 8)*width, (i // 8)*height, (i % 8+1)*width, (i // 8+1)*height))
        indexed.append(bytes(c + 1 if a >= 128 else 0 for c, a in zip(tile.tobytes(), frame.getchannel('A').tobytes())))
    bank = pack_indices(width, height, palette, indexed)
    _, _, _, decoded = unpack_indices(bank)
    if decoded != indexed: raise ValueError('frame-bank verification failed')
    return bank, {'frames': len(frames), 'unique_frames': len(set(indexed)),
                  'width': width, 'height': height, 'palette_colors': 256,
                  'decoded_pixel_bytes': width*height*len(frames), 'bank_bytes': len(bank),
                  'frames_dropped': 0, 'compression': 'lossless RLE after palette conversion'}
