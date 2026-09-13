"""Remix stem selection/mixing and actual C routing with a stub CD backend."""
import array
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_remix_audio as remix

class RemixAudio(unittest.TestCase):
    def test_explicit_voices_and_character_fallbacks(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            for name in ('bf', 'bf-christmas', 'parents-christmas', 'pico'):
                (folder / f'Voices-{name}-erect.ogg').touch()
            chars = dict(player='bf-christmas', playerVocals=['bf-christmas'])
            self.assertEqual([p.name for p in remix.resolve_voices(folder, chars, 'player')],
                             ['Voices-bf-christmas-erect.ogg'])
            chars = dict(player='pico-playable', playerVocals=['missing'])
            self.assertEqual([p.name for p in remix.resolve_voices(folder, chars, 'player')],
                             ['Voices-pico-erect.ogg'])
            chars['playerVocals'] = []
            self.assertEqual(remix.resolve_voices(folder, chars, 'player'), [])
            chars = dict(player='bf-dark')
            self.assertEqual([p.name for p in remix.resolve_voices(folder, chars, 'player')],
                             ['Voices-bf-erect.ogg'])

    def test_offsets_use_selected_instrumental_table(self):
        offsets = dict(vocals={'dad': -8}, altVocals={'erect': {'bf': 12}})
        self.assertEqual(remix.vocal_offset(offsets, 'dad', 'erect'), 0)
        self.assertEqual(remix.vocal_offset(offsets, 'dad', None), -8)
        self.assertEqual(remix.vocal_offset(offsets, 'bf', 'erect'), 12)

    def test_muting_preserves_opponent_gain_and_full_length(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            self.skipTest('ffmpeg unavailable')
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            # Constant PCM makes gains, delay and mute behavior independently measurable.
            def pcm(name, value, count):
                path = folder / (name + '.wav')
                with wave.open(str(path), 'wb') as stream:
                    stream.setparams((2, 2, 18900, 0, 'NONE', 'not compressed'))
                    stream.writeframes(array.array('h', [value, value] * count).tobytes())
                return path
            record = dict(instrumental=pcm('inst', 1000, 1890),
                          opponent=[pcm('opp', 2000, 1890)],
                          player=[pcm('player', 4000, 3780)],
                          player_offset=20, opponent_offset=0)
            full, mute = folder / 'full.wav', folder / 'mute.wav'
            count = remix.make_pair(ffmpeg, record, full, mute)
            def read(path):
                with wave.open(str(path), 'rb') as stream:
                    self.assertEqual(stream.getnframes(), count)
                    return array.array('h', stream.readframes(count))
            a, b = read(full), read(mute)
            self.assertEqual(a[200], 3000)  # Before delayed player entry.
            self.assertEqual(a[1000], 7000)
            self.assertEqual(b[1000], 3000) # Instrumental + opponent, same gain.
            self.assertEqual(a[5000], 4000)
            self.assertEqual(b[5000], 0)    # Shorter muted mix padded to full duration.
            self.assertEqual(count, 4158)

    def test_interleave_padding_and_manifest_idempotence(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            paths, silence = [], []
            for ch in range(8):
                p = folder / f'{ch}.xa'
                p.write_bytes(bytes([ch]) * remix.SECTOR * (ch + 1))
                paths.append(p)
                silence.append(bytes([ch + 100]) * remix.SECTOR)
            out = folder / 'mix.xa'
            self.assertEqual(remix.interleave(out, paths, silence), 64)
            blocks = remix.sectors(out)
            for cycle in range(8):
                for ch in range(8):
                    self.assertEqual(blocks[cycle * 8 + ch][0], ch if cycle <= ch else ch + 100)
            xml = folder / 'funkin.xml'
            xml.write_text('<project><dir name="music"><file name="week1.xa" /></dir></project>')
            remix.add_manifest(xml, ['rmx00.xa'])
            once = xml.read_text()
            remix.add_manifest(xml, ['rmx00.xa'])
            self.assertEqual(xml.read_text(), once)
            self.assertIn('week1.xa', once)

    def test_reject_incomplete_or_misrouted_xa(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'bad.xa'
            path.write_bytes(bytes(remix.SECTOR))
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                remix.verify_xa(path)
            path.write_bytes(bytes(remix.SECTOR * 8))
            with self.assertRaisesRegex(ValueError, 'invalid XA sector'):
                remix.verify_xa(path)

    def test_actual_runtime_routes_retry_and_return_to_base(self):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            for name in ('stage_music.c', 'stage_music.h'):
                shutil.copy(ROOT / 'overlay/src' / name, folder / name)
            (folder / 'stage.h').write_text(r'''
#ifndef STAGE_H
#define STAGE_H
#include <stddef.h>
#include <stdint.h>
typedef uint32_t u32; typedef uint8_t u8; typedef int fixed_t;
typedef enum {StageId_1_1, StageId_8_1, StageId_8_2, StageId_1_4} StageId;
typedef enum {StageDiff_Easy, StageDiff_Normal, StageDiff_Hard, StageDiff_Erect, StageDiff_Nightmare} StageDiff;
typedef struct {u32 size; int pos;} CdlFILE;
typedef struct {int music_track; u8 music_channel;} StageDef;
typedef struct {StageId stage_id; StageDiff stage_diff; const StageDef *stage_def; CdlFILE music_file; u8 music_channel; int music_separate_vocals;} Stage;
#define IO_SECT_SIZE 2048
void IO_FindFile(CdlFILE *, const char *);
void IO_SeekFile(CdlFILE *);
#endif
''')
            (folder / 'audio.h').write_text('void Audio_GetXAFile(CdlFILE *, int);\n')
            remix.write_header(folder / 'remix_audio_generated.h', [
                dict(week=1, index=1, file='rmx00.xa', physical_sectors=800, channel=4, speeds=[2.2, 2.8]),
                dict(week=8, index=1, file='rmx04.xa', physical_sectors=1600, channel=0, speeds=[3, 3.2])])
            remix.write_header(folder / 'base_audio_generated.h', [
                dict(week=1, index=4, file='rmx00.xa', physical_sectors=400, channel=2,
                     speeds=[1, 1.5, 2])], 'base_music_defs')
            (folder / 'test.c').write_text(r'''
#include <assert.h>
#include <string.h>
#include "stage_music.c"
int base_calls, remix_calls, seeks;
void IO_FindFile(CdlFILE *file, const char *path) {
    remix_calls++;
    assert(!strcmp(path,"\\MUSIC\\RMX00.XA;1") || !strcmp(path,"\\MUSIC\\RMX04.XA;1"));
    file->pos=555; file->size=999999;
}
void IO_SeekFile(CdlFILE *file) {seeks++;assert(file->size>0);}
void Audio_GetXAFile(CdlFILE *file,int track) {
    base_calls++;assert(track==7);file->size=2048*20;file->pos=333;
}
int main(void) {
    StageDef def={7,6};Stage state={StageId_1_1,StageDiff_Erect,&def,{0,0},0,0};
    StageMusic_Load(&state);
    assert(state.music_separate_vocals && state.music_channel==4 && state.music_file.size==800*2048 && state.music_file.pos==555);
    StageMusic_Load(&state);assert(remix_calls==2 && base_calls==0 && seeks==2);
    assert(StageMusic_Speed(StageId_1_1,StageDiff_Erect,100)==2252);
    assert(StageMusic_Speed(StageId_1_1,StageDiff_Nightmare,100)==2867);
    state.stage_id=StageId_8_1;state.stage_diff=StageDiff_Nightmare;StageMusic_Load(&state);
    assert(state.music_channel==0 && state.music_file.size==1600*2048);
    for(int d=StageDiff_Easy;d<=StageDiff_Hard;d++) {
        state.stage_diff=d;StageMusic_Load(&state);
        assert(!state.music_separate_vocals && state.music_channel==6 && state.music_file.pos==333 && state.music_file.size==20*2048);
        assert(StageMusic_Speed(StageId_8_1,d,1777)==1777);
    }
    state.stage_id=StageId_8_2;state.stage_diff=StageDiff_Erect;StageMusic_Load(&state);
    assert(state.music_channel==6 && base_calls==4 && seeks==7);
    assert(StageMusic_Speed(StageId_8_2,StageDiff_Erect,99)==99);
    assert(StageMusic_Speed(StageId_1_1,(StageDiff)99,99)==99);
    state.stage_id=StageId_1_4;state.stage_diff=StageDiff_Normal;StageMusic_Load(&state);
    assert(state.music_separate_vocals && state.music_channel==2 && state.music_file.size==400*2048);
    assert(StageMusic_Speed(StageId_1_4,StageDiff_Easy,99)==1024);
    assert(StageMusic_Speed(StageId_1_4,StageDiff_Normal,99)==1536);
    assert(StageMusic_Speed(StageId_1_4,StageDiff_Hard,99)==2048);
    return 0;
}
''')
            binary = folder / 'test'
            subprocess.run([cc, '-std=c99', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            '-fno-pie', '-no-pie', str(folder / 'test.c'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'}, check=True)

if __name__ == '__main__':
    unittest.main()
