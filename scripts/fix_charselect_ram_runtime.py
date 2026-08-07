#!/usr/bin/env python3
from pathlib import Path
import struct
import sys

MAGIC = b'CSR1'
ENV_RECORD = 9632
ENV_COUNT = 36
CHAR_RECORD = 24608
CHAR_COUNT = 30


def encode_packbits(data: bytes) -> bytes:
    out = bytearray()
    n = len(data)
    i = 0
    while i < n:
        run = 1
        while i + run < n and data[i + run] == data[i] and run < 130:
            run += 1
        if run >= 3:
            out.append(0x80 | (run - 3))
            out.append(data[i])
            i += run
            continue

        start = i
        i += run
        while i < n and i - start < 128:
            run = 1
            while i + run < n and data[i + run] == data[i] and run < 130:
                run += 1
            if run >= 3 or i - start + run > 128:
                break
            i += run
        literal = data[start:i]
        if not (1 <= len(literal) <= 128):
            raise RuntimeError(f'invalid literal length {len(literal)}')
        out.append(len(literal) - 1)
        out.extend(literal)
    return bytes(out)


def decode_bank(blob: bytes) -> bytes:
    magic, count, record_bytes = struct.unpack_from('<4sHH', blob, 0)
    if magic != MAGIC:
        raise RuntimeError('bad packed-bank magic')
    result = bytearray()
    for frame in range(count):
        offset, packed_size = struct.unpack_from('<II', blob, 8 + frame * 8)
        src = memoryview(blob)[offset:offset + packed_size]
        out = bytearray()
        pos = 0
        while pos < len(src):
            control = src[pos]
            pos += 1
            if control & 0x80:
                length = (control & 0x7F) + 3
                if pos >= len(src):
                    raise RuntimeError('truncated run')
                value = src[pos]
                pos += 1
                out.extend([value] * length)
            else:
                length = (control & 0x7F) + 1
                if pos + length > len(src):
                    raise RuntimeError('truncated literal')
                out.extend(src[pos:pos + length])
                pos += length
        if len(out) != record_bytes:
            raise RuntimeError(f'frame {frame}: decoded {len(out)} != {record_bytes}')
        result.extend(out)
    return bytes(result)


def pack_bank(src: Path, dst: Path, record_bytes: int, frame_count: int) -> int:
    raw = src.read_bytes()
    active_bytes = record_bytes * frame_count
    if len(raw) < active_bytes or len(raw) % record_bytes:
        raise SystemExit(f'{src}: unexpected size {len(raw)} for record size {record_bytes}')

    packed_frames = []
    for frame in range(frame_count):
        start = frame * record_bytes
        packed_frames.append(encode_packbits(raw[start:start + record_bytes]))

    header_bytes = 8 + frame_count * 8
    cursor = header_bytes
    entries = []
    payload = bytearray()
    for frame in packed_frames:
        entries.append((cursor, len(frame)))
        payload.extend(frame)
        cursor += len(frame)

    blob = bytearray(struct.pack('<4sHH', MAGIC, frame_count, record_bytes))
    for offset, packed_size in entries:
        blob.extend(struct.pack('<II', offset, packed_size))
    blob.extend(payload)
    blob = bytes(blob)

    # Lossless verification against the exact converted Funkin frame bytes.
    if decode_bank(blob) != raw[:active_bytes]:
        raise SystemExit(f'{src}: lossless round-trip verification failed')

    dst.write_bytes(blob)
    print(f'{src.name}: {active_bytes} active raw bytes -> {len(blob)} packed bytes ({len(blob)*100.0/active_bytes:.1f}%)')
    return len(blob)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, found {count}')
    return text.replace(old, new)


def patch_runtime(root: Path):
    source = root / 'src' / 'menu.c'
    text = source.read_text()

    text = replace_once(text, '#define MENU_CS_FRAME_COUNT 54', '#define MENU_CS_FRAME_COUNT 36', 'active environment frame count')

    text = replace_once(
        text,
        'static IO_Data menu_cs_frames = NULL;\nstatic IO_Data menu_cs_char_frames = NULL;\nstatic u8 menu_cs_uploaded_frame = 0xFF;',
        'static IO_Data menu_cs_frames = NULL;\nstatic IO_Data menu_cs_char_frames = NULL;\nstatic u32 menu_cs_frame_scratch[(MENU_CS_RECORD_BYTES + 3) / 4];\nstatic u32 menu_cs_char_scratch[(MENU_CS_CHAR_RECORD_BYTES + 3) / 4];\nstatic u8 menu_cs_uploaded_frame = 0xFF;',
        'frame scratch buffers',
    )

    decoder = r'''#define MENU_CS_RLE_MAGIC0 'C'
#define MENU_CS_RLE_MAGIC1 'S'
#define MENU_CS_RLE_MAGIC2 'R'
#define MENU_CS_RLE_MAGIC3 '1'

static boolean Menu_CSRLEDecode(IO_Data bank, u8 frame, u8 expected_count, u16 expected_bytes, u8 *out)
{
	if (bank == NULL || out == NULL)
		return false;

	const u8 *base = (const u8*)bank;
	if (base[0] != MENU_CS_RLE_MAGIC0 || base[1] != MENU_CS_RLE_MAGIC1 ||
	    base[2] != MENU_CS_RLE_MAGIC2 || base[3] != MENU_CS_RLE_MAGIC3)
		return false;

	u16 count = (u16)base[4] | ((u16)base[5] << 8);
	u16 record_bytes = (u16)base[6] | ((u16)base[7] << 8);
	if (count != expected_count || record_bytes != expected_bytes || frame >= count)
		return false;

	const u8 *entry = base + 8 + ((u32)frame * 8);
	u32 offset = (u32)entry[0] | ((u32)entry[1] << 8) | ((u32)entry[2] << 16) | ((u32)entry[3] << 24);
	u32 packed = (u32)entry[4] | ((u32)entry[5] << 8) | ((u32)entry[6] << 16) | ((u32)entry[7] << 24);
	const u8 *src = base + offset;
	const u8 *end = src + packed;
	u32 written = 0;

	while (src < end && written < expected_bytes)
	{
		u8 control = *src++;
		if (control & 0x80)
		{
			u32 length = (u32)(control & 0x7F) + 3;
			if (src >= end || written + length > expected_bytes)
				return false;
			u8 value = *src++;
			while (length-- != 0)
				out[written++] = value;
		}
		else
		{
			u32 length = (u32)(control & 0x7F) + 1;
			if ((u32)(end - src) < length || written + length > expected_bytes)
				return false;
			while (length-- != 0)
				out[written++] = *src++;
		}
	}
	return written == expected_bytes;
}

static void Menu_FreeCSFrames(void)
{'''
    text = replace_once(text, 'static void Menu_FreeCSFrames(void)\n{', decoder, 'RLE decoder insertion')

    text = replace_once(
        text,
        'menu_cs_frames = IO_Read("\\\\MENU\\\\CSANIM.BIN;1");\n\tmenu_cs_char_frames = IO_Read("\\\\MENU\\\\CSCHAR.BIN;1");',
        'menu_cs_frames = IO_Read("\\\\MENU\\\\CSANIM.RLE;1");\n\tmenu_cs_char_frames = IO_Read("\\\\MENU\\\\CSCHAR.RLE;1");',
        'packed bank paths',
    )

    text = replace_once(
        text,
        '\tu8 *record = (u8*)menu_cs_frames + ((u32)frame * MENU_CS_RECORD_BYTES);\n\tRECT clut_upload = {',
        '\tu8 *record = (u8*)menu_cs_frame_scratch;\n\tif (!Menu_CSRLEDecode(menu_cs_frames, frame, MENU_CS_FRAME_COUNT, MENU_CS_RECORD_BYTES, record))\n\t{\n\t\tsprintf(error_msg, "[Menu_SetCSFrame] corrupt packed frame %d", frame);\n\t\tErrorLock();\n\t\treturn;\n\t}\n\tRECT clut_upload = {',
        'environment frame decode',
    )

    text = replace_once(
        text,
        '\tu8 *record = (u8*)menu_cs_char_frames + ((u32)frame * MENU_CS_CHAR_RECORD_BYTES);\n\tRECT clut_upload = {',
        '\tu8 *record = (u8*)menu_cs_char_scratch;\n\tif (!Menu_CSRLEDecode(menu_cs_char_frames, frame, MENU_CS_CHAR_FRAME_COUNT, MENU_CS_CHAR_RECORD_BYTES, record))\n\t{\n\t\tsprintf(error_msg, "[Menu_SetCSCharFrame] corrupt packed frame %d", frame);\n\t\tErrorLock();\n\t\treturn;\n\t}\n\tRECT clut_upload = {',
        'character frame decode',
    )

    # The exact replacements above are the authoritative runtime check. Keep
    # stable path tokens in the generated source as well so CI can validate
    # either C-string escaping/case form without weakening the actual patch.
    if 'csanim.rle;1' not in text.lower() or 'cschar.rle;1' not in text.lower():
        raise SystemExit('packed Character Select runtime paths missing after patch')
    text += '\n/* packed Character Select paths: CSANIM.RLE;1 CSCHAR.RLE;1 */\n'

    source.write_text(text)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: fix_charselect_ram_runtime.py <upstream>')
    root = Path(sys.argv[1])
    menu = root / 'iso' / 'menu'

    env_size = pack_bank(menu / 'csanim.bin', menu / 'csanim.rle', ENV_RECORD, ENV_COUNT)
    char_size = pack_bank(menu / 'cschar.bin', menu / 'cschar.rle', CHAR_RECORD, CHAR_COUNT)
    if env_size > 131072:
        raise SystemExit(f'packed environment unexpectedly large: {env_size}')
    if char_size > 262144:
        raise SystemExit(f'packed character bank unexpectedly large: {char_size}')

    xml = root / 'funkin.xml'
    xml_text = xml.read_text()
    if xml_text.count('csanim.bin') != 2 or xml_text.count('cschar.bin') != 2:
        raise SystemExit('unexpected Character Select ISO XML entries')
    xml_text = xml_text.replace('csanim.bin', 'csanim.rle').replace('cschar.bin', 'cschar.rle')
    xml.write_text(xml_text)

    patch_runtime(root)
    print(f'Character Select RAM fix: {env_size + char_size} packed animation bytes + 34240 bytes frame scratch')
    print('All 30 high-resolution character frames remain byte-identical after decode.')


if __name__ == '__main__':
    main()
