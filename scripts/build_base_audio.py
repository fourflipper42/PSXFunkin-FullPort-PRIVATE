#!/usr/bin/env python3
"""Replace legacy recordings with official v0.8.4 default-song stems."""
from __future__ import annotations
import argparse
import json
import tempfile
from pathlib import Path
from build_remix_audio import describe, make_pair, write_header, verify_xa
from build_weekend1_audio import enc, interleave, run, sectors, SECTOR
from build_v084_legacy_charts import MAPPING

GROUPS = {
    'week1a': ['bopeebo', 'fresh'], 'week1b': ['dadbattle', 'tutorial'],
    'week2a': ['spookeez', 'south'], 'week2b': ['monster'],
    'week3a': ['pico', 'philly-nice'], 'week3b': ['blammed'],
    'week4a': ['satin-panties', 'high'], 'week4b': ['milf'],
    'week5a': ['cocoa', 'eggnog'], 'week5b': ['winter-horrorland'],
    'week6a': ['senpai', 'roses'], 'week6b': ['thorns'],
    'week7a': ['ugh', 'guns'], 'week7b': ['stress'],
    'week8': ['darnell', 'lit-up', '2hot', 'blazin'],
}
WEEKEND = [('darnell', 8, 1), ('lit-up', 8, 2), ('2hot', 8, 3), ('blazin', 8, 4)]


def preserve_legacy_channel(blocks, channel):
    stream = [sector for sector in blocks if sector[0] == 1 and sector[1] == channel]
    if not stream:
        raise ValueError('Missing legacy Test XA channel')
    for index, sector in enumerate(stream):
        if sector[:4] == sector[4:8]:
            continue
        # The pinned legacy encoder set EOF in only the first copy of the
        # final subheader. Repair that exact defect without altering ADPCM data.
        if (index != len(stream) - 1 or sector[:2] != sector[4:6]
                or sector[3] != sector[7] or sector[2] ^ sector[6] != 0x80):
            raise ValueError('Unexpected legacy XA subheader mismatch')
        stream[index] = sector[:4] + sector[:4] + sector[8:]
    return b''.join(stream)


def build(root, upstream, encoder, ffmpeg, report):
    records = {song: describe(root, song, week, index, variation='')
               for song, week, index in MAPPING + WEEKEND}
    files = []
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        # Preserve the hidden legacy Test song in WEEK4B channels 2/3.
        legacy_test = sectors(upstream / 'iso/music/week4b.xa')
        test_paths = []
        for channel in (2, 3):
            path = temp / f'test{channel}.xa'
            path.write_bytes(preserve_legacy_channel(legacy_test, channel))
            test_paths.append(path)

        for name, songs in GROUPS.items():
            rate = 18900 if name == 'week8' else 37800
            channel_count = 8 if rate == 18900 else 4
            silent = temp / f'silence-{rate}.wav'
            run([ffmpeg, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i',
                 f'anullsrc=r={rate}:cl=stereo', '-t', '1', silent])
            paths, padding = [], []
            for channel in range(channel_count):
                path = temp / f'{name}-sil{channel}.xa'
                enc(encoder, silent, path, channel, rate)
                paths.append(path)
                padding.append(sectors(path)[0])

            for slot, song in enumerate(songs):
                record = records[song]
                full = temp / f'{song}-full.wav'
                muted = temp / f'{song}-muted.wav'
                record['samples'] = make_pair(ffmpeg, record, full, muted, rate)
                for side, wav in enumerate((full, muted)):
                    channel = slot * 2 + side
                    paths[channel] = temp / f'{name}-{channel}.xa'
                    enc(encoder, wav, paths[channel], channel, rate)
                sector_count = max(paths[slot * 2].stat().st_size,
                                   paths[slot * 2 + 1].stat().st_size) // SECTOR
                if not 0 <= sector_count * 2016 - record['samples'] < 2016:
                    raise ValueError(f'{song}: truncated or overlong XA audio')
                record.update(file=name + '.xa', channel=slot * 2,
                              physical_sectors=sector_count * channel_count,
                              sample_rate=rate)

            if name == 'week4b':
                paths[2:] = test_paths
            output = upstream / 'iso/music' / (name + '.xa')
            total = interleave(output, paths, padding)
            files.append(dict(file=output.name, physical_sectors=total,
                              bytes=output.stat().st_size, sample_rate=rate,
                              **verify_xa(output, rate=rate)))
            print(f'{name}: {", ".join(songs)} ({total} sectors)', flush=True)

    record_list = list(records.values())
    write_header(upstream / 'src/base_audio_generated.h', record_list, 'base_music_defs')
    defines = [f'#define W1_XA_{song.upper().replace("-", "_")}_SECTORS '
               f'{records[song]["physical_sectors"]}u' for song, _, _ in WEEKEND]
    (upstream / 'src/weekend1_audio_generated.h').write_text(
        '#ifndef WEEKEND1_AUDIO_GENERATED_H\n#define WEEKEND1_AUDIO_GENERATED_H\n' +
        '\n'.join(defines) + '\n#endif\n')
    for record in record_list:
        record['instrumental'] = str(record['instrumental'].relative_to(root))
        for role in ('player', 'opponent'):
            record[role] = [str(path.relative_to(root)) for path in record[role]]
    result = dict(songs=record_list, files=files,
                  physical_sectors=sum(item['physical_sectors'] for item in files))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Encoded {len(record_list)} default songs: {result["physical_sectors"]} sectors')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--psxavenc', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, default=Path('ffmpeg'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.upstream, args.psxavenc, args.ffmpeg, args.report)
