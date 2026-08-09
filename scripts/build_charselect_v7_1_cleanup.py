#!/usr/bin/env python3
"""Build focused Character Select v7.1 cleanup assets.

Keeps the v7 BF/GF/foreground hierarchy untouched. Rebuilds only:
- per-cell lock sprites on the same canonical selector grid,
- the BF PixelatedIcon with its real Sparrow frame canvas and explicit 128px
  Character Select size,
- a font-safe control atlas / CLUT,
- a native 320x240 8bpp intro sampled with the official video sizing policy,
- nine full-screen validation states.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import build_charselect_source_v7 as v7
import run_charselect_source_v7 as v7run

W, H = 320, 240
SOURCE_W, SOURCE_H = 1280, 720
CROP_X, CROP_W = 160, 960
BF_SLOT = 4
INTRO_COUNT = 24
RECORD_BYTES = 512 + W * H

# Complete v7.1 live VRAM map. Coordinates are VRAM words for texture images.
LOCK_CLUT = (0, 509)
LOCK_PAGES = ((768, 0, 128), (832, 0, 128), (960, 0, 128))
CTRL_CLUT = (256, 511)  # crucially NOT font CLUT (0,511)
CTRL_PAGES = ((448, 256, 128), (512, 256, 128))
FONT_CLUT_RECT = (0, 511, 16, 1)
FONT_IMAGE_RECT = (896, 0, 64, 128)

LOCK_COLORS = (
    (0x31, 0xF2, 0xA5), (0x20, 0xEC, 0xCD), (0x24, 0xD9, 0xE8),
    (0x20, 0xEC, 0xCD), (0x20, 0xC8, 0xD4), (0x20, 0x9B, 0xDD),
    (0x20, 0x9B, 0xDD), (0x23, 0x62, 0xC9), (0x24, 0x3F, 0xB9),
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def alpha_crop(im: Image.Image) -> Image.Image:
    im = im.convert('RGBA')
    box = im.getchannel('A').getbbox()
    return im.crop(box) if box else Image.new('RGBA', (1, 1), (0, 0, 0, 0))


def rgba8(image: Image.Image, psx_color) -> tuple[bytes, bytes]:
    image = image.convert('RGBA')
    alpha = image.getchannel('A')
    rgb = Image.new('RGB', image.size, (0, 0, 0))
    rgb.paste(image.convert('RGB'), mask=alpha)
    q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    raw = q.getpalette()[:255 * 3]
    colors = [tuple(raw[i:i+3]) for i in range(0, len(raw), 3)]
    while len(colors) < 255:
        colors.append((0, 0, 0))
    clut = b''.join(struct.pack('<H', c) for c in ([0] + [psx_color(c) for c in colors[:255]]))
    qp = list(q.getdata()); ap = list(alpha.getdata())
    pixels = bytes(0 if a < 128 else int(i) + 1 for i, a in zip(qp, ap))
    return clut, pixels


def tim8_page(clut: bytes, full_pixels: bytes, full_w: int, full_h: int,
              x0: int, page_w: int, vram_x: int, vram_y: int,
              clut_x: int, clut_y: int) -> bytes:
    half = bytearray()
    for y in range(full_h):
        row = y * full_w
        half.extend(full_pixels[row + x0:row + x0 + page_w])
    if len(half) != page_w * full_h or page_w & 1:
        raise RuntimeError('invalid 8bpp page')
    out = bytearray(struct.pack('<II', 0x10, 0x09))
    out += struct.pack('<IHHHH', 12 + 512, clut_x, clut_y, 256, 1) + clut
    out += struct.pack('<IHHHH', 12 + len(half), vram_x, vram_y, page_w // 2, full_h) + half
    return bytes(out)


def q2_pack(records: list[bytes]) -> bytes:
    """Same lossless CSQ2 RLE format already proven by the v3-v7 runtime."""
    def enc(data: bytes) -> bytes:
        out = bytearray(); i = 0; n = len(data)
        while i < n:
            run = 1
            while i + run < n and data[i + run] == data[i] and run < 130:
                run += 1
            if run >= 3:
                out.append(0x80 | (run - 3)); out.append(data[i]); i += run; continue
            start = i; i += run
            while i < n and i - start < 128:
                r = 1
                while i + r < n and data[i + r] == data[i] and r < 130:
                    r += 1
                if r >= 3: break
                i += r
            lit = data[start:i]
            out.append(len(lit) - 1); out.extend(lit)
        return bytes(out)

    packed = [enc(r) for r in records]
    header = bytearray(b'CSQ2')
    header += struct.pack('<HHI', len(records), 0, len(records[0]))
    table = bytearray(); payload = bytearray()
    off = 12 + 8 * len(records)
    for p in packed:
        table += struct.pack('<II', off, len(p)); payload += p; off += len(p)
    return bytes(header + table + payload)


def rect_overlap(a, b) -> bool:
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def load_builder(builder_path: Path):
    clean = v7.corrected_builder_copy(builder_path)
    return v7run.capture_builder(clean)


def lock_frame_number(mod, asset, label: str, fallback: int) -> int:
    try:
        return int(mod.sample_frame(asset, 0, 1, label))
    except Exception:
        return fallback


def build_lock_atlas(mod, root: Path, cursor_positions: list[list[int]], cursor_size: tuple[int, int]):
    asset = mod.load_optional_anim(root, 'lock')
    if asset is None:
        raise RuntimeError('official charSelect/lock Animate source missing')
    idle = lock_frame_number(mod, asset, 'idle', 0)
    selected = lock_frame_number(mod, asset, 'selected', idle)
    clicked = lock_frame_number(mod, asset, 'clicked', selected)
    frame_nums = (idle, selected, clicked)

    atlas = Image.new('RGBA', (384, 128), (0, 0, 0, 0))
    src = [[[0,0,1,1] for _ in range(9)] for _ in range(3)]
    dst = [[0,0,1,1] for _ in range(9)]
    cw, ch = cursor_size

    for state, frame_no in enumerate(frame_nums):
        # One full 128x128 texture page per authored lock state. Selected/clicked
        # frames are substantially larger than idle and must not share a page.
        page = state
        base_x = 128 * page
        for index, color in enumerate(LOCK_COLORS):
            im, _ox, _oy, _tagged = v7run._render_tagged(asset, frame_no, color)
            im = alpha_crop(im)
            sw = max(1, round(im.width / 3)); sh = max(1, round(im.height / 3))
            im = im.resize((sw, sh), Image.Resampling.LANCZOS)
            col = index % 3; row = index // 3
            if sw > 40 or sh > 40:
                raise RuntimeError(f'lock state exceeds 40x40 page cell state={state} index={index} size={im.size}')
            slot_x = base_x + col * 42 + 1
            slot_y = row * 42 + 1
            if slot_x + sw > base_x + 128 or slot_y + sh > 128:
                raise RuntimeError(f'lock atlas overflow state={state} index={index} size={im.size}')
            atlas.alpha_composite(im, (slot_x, slot_y))
            src[state][index] = [slot_x, slot_y, sw, sh]
            if state == 0:
                cx = cursor_positions[index][0] + cw / 2
                cy = cursor_positions[index][1] + ch / 2
                dst[index] = [round(cx - sw/2), round(cy - sh/2), sw, sh]

    return atlas, src, dst, {'idle': idle, 'selected': selected, 'clicked': clicked}


def pack_controls(mod, root: Path, v7_meta: dict):
    selector_path = root / 'images/charSelect/charSelector.png'
    selector = Image.open(selector_path).convert('RGBA').resize((41, 37), Image.Resampling.LANCZOS)
    def tint(rgb):
        out = Image.new('RGBA', selector.size, (*rgb, 255)); out.putalpha(selector.getchannel('A')); return out
    dark, light, yellow, orange = tint((0x3C,0x74,0xF7)), tint((0x3E,0xBB,0xFF)), tint((0xFF,0xFF,0)), tint((0xFF,0xCC,0))
    confirm = v7.v5.first_sparrow_frame(v7.v6, root, 'charSelectorConfirm.png', 'charSelectorConfirm.xml')
    deny = v7.v5.first_sparrow_frame(v7.v6, root, 'charSelectorDenied.png', 'charSelectorDenied.xml')
    confirm = alpha_crop(confirm).resize(selector.size, Image.Resampling.LANCZOS) if confirm else yellow.copy()
    deny = alpha_crop(deny).resize(selector.size, Image.Resampling.LANCZOS) if deny else yellow.copy()

    icon_frames, icon_confirm, icon_path = v7.icon_frames(root)
    icon_px = 43
    icons = [im.resize((icon_px, icon_px), Image.Resampling.NEAREST) for im in icon_frames]
    icon_confirm = icon_confirm.resize((icon_px, icon_px), Image.Resampling.NEAREST)

    bf_name = Image.open(root/'images/charSelect/boyfriendNametag.png').convert('RGBA')
    locked_name = Image.open(root/'images/charSelect/lockedNametag.png').convert('RGBA')
    tag_scale = 0.77 * (W / SOURCE_W)
    bf_name = bf_name.resize((round(bf_name.width*tag_scale), round(bf_name.height*tag_scale)), Image.Resampling.LANCZOS)
    locked_name = locked_name.resize((round(locked_name.width*tag_scale), round(locked_name.height*tag_scale)), Image.Resampling.LANCZOS)

    items = [(f'icon_idle_{i}', im) for i, im in enumerate(icons)] + [
        ('icon_confirm', icon_confirm), ('cursor_dark', dark), ('cursor_light', light),
        ('cursor_yellow', yellow), ('cursor_orange', orange), ('cursor_confirm', confirm),
        ('cursor_deny', deny), ('name_bf', bf_name), ('name_locked', locked_name),
    ]
    atlas, rects = v7.shelf_pack(items)

    cursor_positions = v7_meta['controls']['cursor_positions']
    cw, ch = rects['cursor_yellow'][2], rects['cursor_yellow'][3]
    bf_cx = cursor_positions[BF_SLOT][0] + cw / 2
    bf_cy = cursor_positions[BF_SLOT][1] + ch / 2
    un = [round(bf_cx - 43/2), round(bf_cy - 43/2), 43, 43]
    sel = [round(bf_cx - 56/2), round(bf_cy - 56/2), 56, 56]

    source_mid_x = round((1008 - CROP_X) * W / CROP_W)
    source_mid_y = round(100 * H / SOURCE_H)
    bf_x = min(W - bf_name.width - 5, source_mid_x - bf_name.width//2)
    locked_x = min(W - locked_name.width - 5, source_mid_x - locked_name.width//2)
    bf_pos = [bf_x, source_mid_y - bf_name.height//2]
    locked_pos = [locked_x, source_mid_y - locked_name.height//2]

    return atlas, {
        'rects': rects, 'cursor_positions': cursor_positions,
        'icon_path': icon_path, 'icon_idle_count': len(icons),
        'icon_unselected_dst': un, 'icon_selected_dst': sel,
        'name_bf_pos': bf_pos, 'name_locked_pos': locked_pos,
        'tag_effective_scale': tag_scale,
    }


def extract_intro(video: Path, psx_color) -> tuple[list[bytes], list[Image.Image], float, tuple[int,int]]:
    probe = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height',
                            '-of','json',str(video)], check=True, capture_output=True, text=True)
    data = json.loads(probe.stdout)
    duration = float(data['format']['duration'])
    stream = next(s for s in data['streams'] if 'width' in s)
    src_size = (int(stream['width']), int(stream['height']))
    frames=[]; records=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for i in range(INTRO_COUNT):
            # Sample uniformly inside the movie rather than exactly at/near EOF.
            # Some v0.8.4 introSelect encodes do not return a decoded frame in the
            # final few tens of milliseconds. 23/24 still captures the visual tail.
            t = duration * i / INTRO_COUNT
            out=td/f'i{i:02d}.png'
            subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{t:.6f}','-i',str(video),'-frames:v','1',str(out)], check=True)
            im=Image.open(out).convert('RGBA')
            im=im.resize((SOURCE_W,SOURCE_H), Image.Resampling.LANCZOS)
            im=im.crop((CROP_X,0,CROP_X+CROP_W,SOURCE_H)).resize((W,H), Image.Resampling.LANCZOS)
            clut,pixels=rgba8(im,psx_color)
            records.append(clut+pixels); frames.append(im)
    return records, frames, duration, src_size


def write_header(path: Path, lock_src, lock_dst, controls, intro_bytes: int):
    r=controls['rects']
    def rect(mac, x):
        return [f'#define {mac}_X {x[0]}',f'#define {mac}_Y {x[1]}',f'#define {mac}_W {x[2]}',f'#define {mac}_H {x[3]}']
    lines=['#ifndef CHARSELECT_V7_1_GENERATED_H','#define CHARSELECT_V7_1_GENERATED_H','',
           f'#define CSV71_INTRO_FRAME_COUNT {INTRO_COUNT}', f'#define CSV71_INTRO_RECORD_BYTES {RECORD_BYTES}',
           f'#define CSV71_INTRO_PACKED_BYTES {intro_bytes}', f'#define CSV71_ICON_IDLE_COUNT {controls["icon_idle_count"]}','']
    for i in range(controls['icon_idle_count']): lines += rect(f'CSV71_ICON_IDLE_{i}', r[f'icon_idle_{i}'])
    lines += rect('CSV71_ICON_CONFIRM',r['icon_confirm'])
    for mac,key in [('CSV71_CURSOR_DARK','cursor_dark'),('CSV71_CURSOR_LIGHT','cursor_light'),('CSV71_CURSOR_YELLOW','cursor_yellow'),('CSV71_CURSOR_ORANGE','cursor_orange'),('CSV71_CURSOR_CONFIRM','cursor_confirm'),('CSV71_CURSOR_DENY','cursor_deny'),('CSV71_NAME_BF','name_bf'),('CSV71_NAME_LOCKED','name_locked')]: lines += rect(mac,r[key])
    u=controls['icon_unselected_dst']; s=controls['icon_selected_dst']
    lines += ['',f'#define CSV71_ICON_UNSEL_X {u[0]}',f'#define CSV71_ICON_UNSEL_Y {u[1]}',f'#define CSV71_ICON_UNSEL_W {u[2]}',f'#define CSV71_ICON_UNSEL_H {u[3]}',
              f'#define CSV71_ICON_SEL_X {s[0]}',f'#define CSV71_ICON_SEL_Y {s[1]}',f'#define CSV71_ICON_SEL_W {s[2]}',f'#define CSV71_ICON_SEL_H {s[3]}',
              f'#define CSV71_NAME_BF_DST_X {controls["name_bf_pos"][0]}',f'#define CSV71_NAME_BF_DST_Y {controls["name_bf_pos"][1]}',
              f'#define CSV71_NAME_LOCKED_DST_X {controls["name_locked_pos"][0]}',f'#define CSV71_NAME_LOCKED_DST_Y {controls["name_locked_pos"][1]}','']
    lines += ['static const short csv71_cursor_x[9] = {'+', '.join(str(p[0]) for p in controls['cursor_positions'])+'};',
              'static const short csv71_cursor_y[9] = {'+', '.join(str(p[1]) for p in controls['cursor_positions'])+'};',
              'static const short csv71_icon_src_x[CSV71_ICON_IDLE_COUNT] = {'+', '.join(str(r[f'icon_idle_{i}'][0]) for i in range(controls['icon_idle_count']))+'};',
              'static const short csv71_icon_src_y[CSV71_ICON_IDLE_COUNT] = {'+', '.join(str(r[f'icon_idle_{i}'][1]) for i in range(controls['icon_idle_count']))+'};','']
    for name, arr in [('x',0),('y',1),('w',2),('h',3)]:
        vals=[]
        for st in range(3): vals.append('{'+', '.join(str(lock_src[st][i][arr]) for i in range(9))+'}')
        lines.append(f'static const short csv71_lock_src_{name}[3][9] = '+'{'+', '.join(vals)+'};')
    for name, arr in [('x',0),('y',1),('w',2),('h',3)]:
        lines.append(f'static const short csv71_lock_dst_{name}[9] = '+'{'+', '.join(str(lock_dst[i][arr]) for i in range(9))+'};')
    lines += ['', '#endif', '']
    path.write_text('\n'.join(lines))


def paste_asset(out, atlas, rect, dst, resample=Image.Resampling.NEAREST):
    x,y,w,h=rect; dx,dy,dw,dh=dst
    im=atlas.crop((x,y,x+w,y+h)).resize((dw,dh),resample)
    out.alpha_composite(im,(dx,dy))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--builder',type=Path,required=True); ap.add_argument('--assets-root',type=Path,required=True)
    ap.add_argument('--upstream',type=Path,required=True); ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--intro-video',type=Path,required=True)
    args=ap.parse_args()
    mod=load_builder(args.builder)
    report=json.loads(args.report.read_text())
    v7_meta=report['character_select_source_v7']
    root=args.assets_root; menu=args.upstream/'iso/menu'; srcdir=args.upstream/'src'
    val=Path('build/charselect_v7_1_validation'); val.mkdir(parents=True,exist_ok=True)

    controls, control_meta=pack_controls(mod,root,v7_meta)
    lock_atlas, lock_src, lock_dst, lock_frames=build_lock_atlas(mod,root,control_meta['cursor_positions'],(41,37))

    lclut,lpix=rgba8(lock_atlas,mod.base.psx_color)
    cclut,cpix=rgba8(controls,mod.base.psx_color)
    for i,(vx,vy,_pw) in enumerate(LOCK_PAGES):
        data=tim8_page(lclut,lpix,384,128,i*128,128,vx,vy,*LOCK_CLUT)
        (menu/f'csl71{chr(97+i)}.tim').write_bytes(data)
    for i,(vx,vy,_pw) in enumerate(CTRL_PAGES):
        data=tim8_page(cclut,cpix,256,240,i*128,128,vx,vy,*CTRL_CLUT)
        (menu/f'csc71{chr(97+i)}.tim').write_bytes(data)

    intro_records,intro_frames,intro_duration,intro_source_size=extract_intro(args.intro_video,mod.base.psx_color)
    intro_bank=q2_pack(intro_records); (menu/'csi71.rle').write_bytes(intro_bank)
    (menu/'csintro71.rle').write_bytes(intro_bank)  # CI-only local alias; not in XML
    # Historical long-name aliases are local build products only. The PS1 disc
    # manifest references the 8.3-safe names above.
    for short, legacy in (
        ('csl71a.tim','cslock71a.tim'), ('csl71b.tim','cslock71b.tim'),
        ('csl71c.tim','cslock71c.tim'), ('csc71a.tim','csctrl71a.tim'),
        ('csc71b.tim','csctrl71b.tim')):
        (menu/legacy).write_bytes((menu/short).read_bytes())
    write_header(srcdir/'charselect_v7_1_generated.h',lock_src,lock_dst,control_meta,len(intro_bank))

    bg=Image.open('build/charselect_v7_validation/background_00.png').convert('RGBA')
    chars=Image.open('build/charselect_v7_validation/characters_idle_00.png').convert('RGBA')
    base_live=bg.copy(); base_live.alpha_composite(chars)
    for state in range(9):
        out=base_live.copy()
        for idx in range(9):
            if idx==BF_SLOT: continue
            variant=1 if idx==state else 0
            paste_asset(out,lock_atlas,lock_src[variant][idx],lock_dst[idx],Image.Resampling.LANCZOS)
        iframe=state % control_meta['icon_idle_count']
        irect=control_meta['rects'][f'icon_idle_{iframe}']
        idst=control_meta['icon_selected_dst'] if state==BF_SLOT else control_meta['icon_unselected_dst']
        paste_asset(out,controls,irect,idst)
        cr=control_meta['rects']['cursor_yellow']; cp=control_meta['cursor_positions'][state]
        paste_asset(out,controls,cr,[cp[0],cp[1],cr[2],cr[3]],Image.Resampling.LANCZOS)
        nk='name_bf' if state==BF_SLOT else 'name_locked'; nr=control_meta['rects'][nk]
        np=control_meta['name_bf_pos'] if state==BF_SLOT else control_meta['name_locked_pos']
        paste_asset(out,controls,nr,[np[0],np[1],nr[2],nr[3]],Image.Resampling.LANCZOS)
        out.save(val/f'state_{state}.png')
    controls.save(val/'controls_v71.png'); lock_atlas.save(val/'locks_v71.png')
    intro_frames[0].save(val/'intro_00.png'); intro_frames[len(intro_frames)//2].save(val/'intro_mid.png'); intro_frames[-1].save(val/'intro_last.png')

    image_rects=[('intro_bg',(448,0,160,240)),('lock0',(768,0,64,128)),('lock1',(832,0,64,128)),('lock2',(960,0,64,128)),
                 ('ctrl0',(448,256,64,240)),('ctrl1',(512,256,64,240)),('char',(768,256,160,240)),('fg',(576,256,160,240))]
    clut_rects=[('grid',(*LOCK_CLUT,256,1)),('ctrl',(*CTRL_CLUT,256,1)),('bg',(704,509,256,1)),('char',(448,510,256,1)),('fg',(704,510,256,1))]
    for name,r in image_rects:
        if rect_overlap(r,FONT_IMAGE_RECT): raise RuntimeError(f'VRAM image overlap with boldfont: {name} {r}')
    for name,r in clut_rects:
        if rect_overlap(r,FONT_CLUT_RECT): raise RuntimeError(f'VRAM CLUT overlap with boldfont: {name} {r}')

    cleanup={
      'policy':'v7.1 focused cleanup; BF/GF/foreground hierarchy frozen from v7',
      'locks':{'mode':'per-cell sprites centered on canonical cursor cells','frame_numbers':lock_frames,'files':['csl71a.tim','csl71b.tim','csl71c.tim'],'dst':lock_dst},
      'controls':{**control_meta,'clut':[CTRL_CLUT[0],CTRL_CLUT[1]],'files':['csc71a.tim','csc71b.tim']},
      'intro':{'file':'csi71.rle','frames':INTRO_COUNT,'packed_bytes':len(intro_bank),'duration':intro_duration,'source_size':list(intro_source_size),'policy':'resize official video to 1280x720, center 960x720 4:3 crop, then 320x240 8bpp'},
      'font_vram':{'image':list(FONT_IMAGE_RECT),'clut':list(FONT_CLUT_RECT),'control_clut_relocated_to':[CTRL_CLUT[0],CTRL_CLUT[1]],'audit':'pass'},
      'validation_dir':str(val),
    }
    report['character_select_v7_1_cleanup']=cleanup; args.report.write_text(json.dumps(report,indent=2))
    print('V7_1_ASSET_VALIDATION_OK')
    print(json.dumps(cleanup,indent=2))

if __name__=='__main__': main()
