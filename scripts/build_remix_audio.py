#!/usr/bin/env python3
"""Build the 17 v0.8.4 Erect mixes and runtime routes for 1x PS1 XA playback.

Each pair is full mix / player-muted mix. Opponent vocals remain audible on a
miss. Eight interleaved 18.9 kHz stereo 4-bit channels consume 75 sectors/sec.
Reference: Funkin v0.8.4 Song.build*VoiceList/buildVocals and SongOffsets.
"""
from __future__ import annotations
import argparse
import json
import math
import subprocess
import tempfile
import wave
import xml.etree.ElementTree as ET
from pathlib import Path
from build_v084_legacy_charts import MAPPING
from add_v084_chart_entries import EXTRA
from build_weekend1_audio import enc, interleave, run, sectors, SECTOR
from build_weekend1_movies import raw_cd_stream

SONGS = [(s, w, i) for s, w, i in MAPPING if (w, i) in EXTRA] + [('darnell', 8, 1)]


def resolve_voices(folder, characters, role, variation='erect'):
    suffix = '-' + variation if variation not in ('', 'default', None) else ''
    explicit = characters.get(role + 'Vocals')
    if explicit is not None:
        paths = [folder / f'Voices-{name}{suffix}.ogg' for name in explicit]
        if all(p.is_file() for p in paths):
            return paths
    character = characters[role]
    candidate = character
    while candidate:
        path = folder / f'Voices-{candidate}{suffix}.ogg'
        if path.is_file():
            return [path]
        candidate = candidate.rpartition('-')[0]
    # Preserve 0.8.4's implementation: the first fallback omits the variation;
    # subsequent suffix-stripped attempts append it again (Song.hx:937/989).
    path = folder / f'Voices-{character}.ogg'
    if path.is_file():
        return [path]
    candidate = character.rpartition('-')[0]
    while candidate:
        path = folder / f'Voices-{candidate}{suffix}.ogg'
        if path.is_file():
            return [path]
        candidate = candidate.rpartition('-')[0]
    return []


def vocal_offset(offsets, character, instrumental):
    if instrumental is None:
        return float(offsets.get('vocals', {}).get(character, 0))
    return float(offsets.get('altVocals', {}).get(instrumental, {}).get(character, 0))


def describe(root, song, week, index, variation='erect'):
    suffix = '-' + variation if variation else ''
    data = root / 'data/songs' / song
    meta = json.loads((data / f'{song}-metadata{suffix}.json').read_text())
    chart = json.loads((data / f'{song}-chart{suffix}.json').read_text())
    chars = meta['playData']['characters']
    inst_id = chars.get('instrumental', '')
    folder = root / 'songs' / song
    inst = folder / ('Inst' + ('-' + inst_id if inst_id else '') + '.ogg')
    if not inst.is_file():
        raise ValueError(f'Missing instrumental: {inst}')
    offsets = meta.get('offsets', {})
    inst_offset = offsets.get('altInstrumentals', {}).get(inst_id, offsets.get('instrumental', 0))
    # These pinned remixes have no instrumental offset. Refuse new metadata
    # until the runtime song-clock offset is supported instead of shifting all audio.
    if inst_offset:
        raise ValueError(f'{song}: unsupported instrumental clock offset {inst_offset}')
    player = resolve_voices(folder, chars, 'player', variation)
    opponent = resolve_voices(folder, chars, 'opponent', variation)
    if (not player or not opponent) and song != 'blazin':
        raise ValueError(f'{song}: expected separate player and opponent vocals')
    difficulties = ('erect', 'nightmare') if variation == 'erect' else ('easy', 'normal', 'hard')
    speed = [float(chart['scrollSpeed'].get(d, chart['scrollSpeed'].get('default', 1)))
             for d in difficulties]
    if any(not math.isfinite(s) or not 0 < s < 32 for s in speed):
        raise ValueError(f'{song}: invalid scroll speed {speed}')
    return dict(song=song, week=week, index=index, instrumental=inst,
                player=player, opponent=opponent, speeds=speed,
                player_offset=vocal_offset(offsets, chars['player'], inst_id),
                opponent_offset=vocal_offset(offsets, chars['opponent'], inst_id))


def make_pair(ffmpeg, record, full, muted, rate=18900):
    inputs = [(record['instrumental'], 0)]
    inputs += [(p, record['opponent_offset']) for p in record['opponent']]
    inputs += [(p, record['player_offset']) for p in record['player']]
    cmd = [ffmpeg, '-y', '-loglevel', 'error']
    for path, _ in inputs:
        cmd += ['-i', path]
    filters = []
    for i, (_, offset) in enumerate(inputs):
        if not math.isfinite(offset):
            raise ValueError('Non-finite vocal offset')
        timing = f'adelay={offset}:all=1,' if offset > 0 else (
            f'atrim=start={-offset / 1000},asetpts=PTS-STARTPTS,' if offset < 0 else '')
        filters.append(f'[{i}:a]{timing}aresample={rate},aformat=channel_layouts=stereo[a{i}]')
    # Split the shared stems, so both mixes have exactly the same gain/timing.
    shared = 1 + len(record['opponent'])
    for i in range(shared):
        filters.append(f'[a{i}]asplit=2[f{i}][m{i}]')
    full_inputs = ''.join(f'[f{i}]' if i < shared else f'[a{i}]' for i in range(len(inputs)))
    mute_inputs = ''.join(f'[m{i}]' for i in range(shared))
    filters += [f'{full_inputs}amix=inputs={len(inputs)}:duration=longest:normalize=0[full]',
                f'{mute_inputs}amix=inputs={shared}:duration=longest:normalize=0[muted]']
    # PCM16 matches the XA encoder's input precision. Neither mix is independently
    # normalized, avoiding a volume jump when the player vocal channel switches.
    run(cmd + ['-filter_complex', ';'.join(filters), '-map', '[full]', '-c:a', 'pcm_s16le', full,
               '-map', '[muted]', '-c:a', 'pcm_s16le', muted])
    # Match durations even if the player stem outlasts the instrumental/opponent.
    paths = [full, muted]
    counts = []
    for path in paths:
        with wave.open(str(path), 'rb') as stream:
            counts.append(stream.getnframes())
    for path, count in zip(paths, counts):
        if count == max(counts):
            continue
        with wave.open(str(path), 'rb') as stream:
            params, pcm = stream.getparams(), stream.readframes(count)
        with wave.open(str(path), 'wb') as stream:
            stream.setparams(params)
            stream.writeframes(pcm + bytes((max(counts) - count) * params.nchannels * params.sampwidth))
    return max(counts)


def write_header(path, records, array_name='stage_music_defs'):
    lines = ['/* Generated by build_remix_audio.py; do not edit. */',
             f'static const StageMusicDef {array_name}[] = {{']
    for r in records:
        speeds = ', '.join(str(int(s * 1024)) for s in r['speeds'])
        first, last = (('StageDiff_Easy', 'StageDiff_Hard') if len(r['speeds']) == 3
                       else ('StageDiff_Erect', 'StageDiff_Nightmare'))
        cd_path = '\\MUSIC\\' + r['file'].upper() + ';1'
        lines.append(f'    {{StageId_{r["week"]}_{r["index"]}, {json.dumps(cd_path)}, '
                     f'{r["physical_sectors"]}u, {r["channel"]}, {first}, {last}, {{{speeds}}}}},')
    lines.append('};')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n')


def add_manifest(path, names):
    tree = ET.parse(path)
    music = tree.find('.//dir[@name="music"]')
    if music is None:
        raise ValueError('Missing music directory in disc manifest')
    for name in names:
        existing = music.find(f'file[@name="{name}"]')
        if existing is not None:
            music.remove(existing)
        ET.SubElement(music, 'file', name=name, type='xa', source=f'iso/music/{name}')
    ET.indent(tree, space='\t')
    tree.write(path, encoding='unicode')


def verify_xa(path, ffprobe='ffprobe', rate=18900):
    """Validate every channel sector and decode every padded channel to EOF."""
    channels = 8 if rate == 18900 else 4
    coding = 0x05 if rate == 18900 else 0x01
    blocks = sectors(path)
    if not blocks or len(blocks) % channels:
        raise ValueError(f'{path}: incomplete XA interleave cycle')
    for i, block in enumerate(blocks):
        # Duplicated subheader, file 1, interleaved channels, audio+form2,
        # stereo / half-rate / four-bit coding. EOF/EOR flags may vary.
        if (block[:4] != block[4:8] or block[0] != 1 or block[1] != i % channels
                or block[2] & 0x24 != 0x24 or block[3] != coding):
            raise ValueError(f'{path}: invalid XA sector {i}')
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / 'verify.xa'
        raw_cd_stream(path, raw)
        result = subprocess.run([ffprobe, '-v', 'error', '-f', 'psxstr', '-count_frames',
                                 '-show_entries', 'stream=codec_name,sample_rate,channels,nb_read_frames',
                                 '-of', 'json', str(raw)], capture_output=True, text=True, check=True)
    if result.stderr.strip():
        raise ValueError(f'{path}: XA decode errors: {result.stderr}')
    streams = json.loads(result.stdout)['streams']
    expected = len(blocks) // channels
    if len(streams) != channels or any(s.get('codec_name') != 'adpcm_xa'
            or int(s.get('sample_rate', 0)) != rate or s.get('channels') != 2
            or int(s.get('nb_read_frames', 0)) != expected for s in streams):
        raise ValueError(f'{path}: incomplete XA decode: {streams}')
    return dict(decoded_channels=channels, decoded_sectors_per_channel=expected)


def build(root, upstream, encoder, ffmpeg, report):
    records = [describe(root, *entry) for entry in SONGS]
    files = []
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        silent = temp / 'silence.wav'
        run([ffmpeg, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i',
             'anullsrc=r=18900:cl=stereo', '-t', '1', silent])
        silence, silent_paths = [], []
        for ch in range(8):
            path = temp / f'sil{ch}.xa'
            enc(encoder, silent, path, ch)
            silent_paths.append(path)
            silence.append(sectors(path)[0])
        for r in records:
            r['samples'] = make_pair(ffmpeg, r, temp / (r['song'] + '-full.wav'),
                                     temp / (r['song'] + '-muted.wav'))
        # Similar lengths share a file to limit silent padding without dropping audio.
        ordered = sorted(records, key=lambda r: (r['samples'], r['song']))
        for group_start in range(0, len(ordered), 4):
            name = f'rmx{group_start // 4:02d}.xa'
            paths = silent_paths.copy()
            for slot, r in enumerate(ordered[group_start:group_start + 4]):
                for side, label in enumerate(('full', 'muted')):
                    ch = slot * 2 + side
                    paths[ch] = temp / f'{r["song"]}-{label}.xa'
                    enc(encoder, temp / f'{r["song"]}-{label}.wav', paths[ch], ch)
                r.update(file=name, channel=slot * 2,
                         physical_sectors=max(paths[slot * 2].stat().st_size,
                                              paths[slot * 2 + 1].stat().st_size) // SECTOR * 8)
                encoded_samples = r['physical_sectors'] // 8 * 2016
                if not 0 <= encoded_samples - r['samples'] < 2016:
                    raise ValueError(f'{r["song"]}: truncated or overlong XA audio')
            out = upstream / 'iso/music' / name
            count = interleave(out, paths, silence)
            files.append(dict(file=name, physical_sectors=count, bytes=out.stat().st_size,
                              **verify_xa(out)))
    write_header(upstream / 'src/remix_audio_generated.h', records)
    add_manifest(upstream / 'funkin.xml', [f['file'] for f in files])
    for r in records:
        r['instrumental'] = str(r['instrumental'].relative_to(root))
        for role in ('player', 'opponent'):
            r[role] = [str(p.relative_to(root)) for p in r[role]]
    result = dict(sample_rate=18900, stereo=True, bits=4, interleave=8,
                  songs=records, files=files, physical_sectors=sum(f['physical_sectors'] for f in files))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Encoded {len(records)} remixes in {len(files)} files: {result["physical_sectors"]} sectors')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--psxavenc', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, default=Path('ffmpeg'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.upstream, args.psxavenc, args.ffmpeg, args.report)
