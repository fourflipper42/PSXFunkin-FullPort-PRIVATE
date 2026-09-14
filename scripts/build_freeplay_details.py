"""Original Freeplay widgets, stored in resident atlases and an album frame bank."""
import json, math
from PIL import Image, ImageOps, ImageDraw, ImageFont
from build_menu_art import sparrow
from animateatlas_flatten import AnimateAtlas, IDENTITY, render_leaves_fixed
from png_to_tim import encode_tim

SONGS=('tutorial','bopeebo','fresh','dadbattle','spookeez','south','monster','pico','philly-nice','blammed','satin-panties','high','milf','cocoa','eggnog','winter-horrorland','senpai','roses','thorns','ugh','guns','stress','darnell','lit-up','2hot','blazin')
ALBUMS=('volume1','volume2','volume3','volume4','expansion1','expansion2')

def build_details(root,out,bank,arrays,files):
    images=[];groups={}
    def add(name,frames):
        groups[name]=list(range(len(images),len(images)+len(frames)));images.extend(frames)
    def scaled(path,scale):
        im=Image.open(root/'images'/path).convert('RGBA')
        return im.resize((max(1,round(im.width*scale)),max(1,round(im.height*scale))),Image.Resampling.LANCZOS)
    frames,_=sparrow(root/'images/freeplay/freeplaySelector/freeplaySelector.png',.3)
    add('arrow_left',frames);add('arrow_right',[ImageOps.mirror(f) for f in frames])
    for name,poses in [('arrow_left_press',frames),('arrow_right_press',[ImageOps.mirror(f) for f in frames])]:
        pressed=[]
        for f in poses:
            small=f.resize((f.width//2,f.height//2),Image.Resampling.LANCZOS)
            white=Image.new('RGBA',small.size,'white');white.putalpha(small.getchannel('A'))
            canvas=Image.new('RGBA',f.size);canvas.alpha_composite(white,(f.width//4,f.height//4+2));pressed.append(canvas)
        add(name,pressed)
    frames,g=sparrow(root/'images/freeplay/highscore.png',.21)
    add('highscore',frames)
    add('clearbox',[scaled('freeplay/clearBox.png',.23)])
    percentages=[];font=ImageFont.truetype(str(root/'fonts/5by7.ttf'),8)
    for percent in range(101):
        canvas=Image.new('RGBA',(22,10));draw=ImageDraw.Draw(canvas);draw.fontmode='1'
        draw.text((11,0),str(percent)+'%',font=font,fill='white',anchor='mt');percentages.append(canvas)
    add('completion',percentages)
    backing_font=ImageFont.truetype(str(root/'fonts/5by7.ttf'),16)
    glyphs=[]
    for code in range(32,96):
        canvas=Image.new('RGBA',(12,22));draw=ImageDraw.Draw(canvas);draw.fontmode='1'
        draw.text((0,0),chr(code),font=backing_font,fill='white',anchor='lt');glyphs.append(canvas)
    add('backglyph',glyphs)
    header_font=ImageFont.truetype(str(root/'fonts/vcr.ttf'),11)
    for name,text in [('header','FREEPLAY'),('ost','OFFICIAL OST')]:
        canvas=Image.new('RGBA',(82,14));draw=ImageDraw.Draw(canvas);draw.fontmode='1'
        draw.text((0,0),text,font=header_font,fill='white',anchor='lt');add(name,[canvas])
    week_font=ImageFont.truetype(str(root/'fonts/YoureGone-Regular.otf'),5)
    for i in range(9):
        canvas=Image.new('RGBA',(32,7));draw=ImageDraw.Draw(canvas);draw.fontmode='1'
        if i:draw.text((0,0),f'WEEK {i}' if i<8 else 'WEEKEND 1',font=week_font,fill=(33,36,46),anchor='lt')
        add(f'week_{i}',[canvas])
    arrays.append('static const u8 fp_song_week[] = {0,1,1,1,2,2,2,3,3,3,4,4,4,5,5,5,6,6,6,7,7,7,8,8,8,8};')
    frames,g=sparrow(root/'images/digital_numbers.png',.12)
    for word in ('ZERO','ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE'):
        add('digit_'+word.lower(),[frames[i] for i in g[word+' DIGITAL']])
    for prefix,file in [('rating','bignumbers'),('bpm','smallnumbers')]:
        frames,g=sparrow(root/f'images/freeplay/freeplayCapsule/{file}.png',.23)
        for digit,word in enumerate(('ZERO','ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE')):
            add(f'{prefix}_{digit}',[frames[i] for i in g[word]])
    add('bpmtext',[scaled('freeplay/freeplayCapsule/bpmtext.png',.207)])
    add('difficultytext',[scaled('freeplay/freeplayCapsule/difficultytext.png',.207)])
    frames,_=sparrow(root/'images/freeplay/favHeart.png',.1);add('heart',frames)
    letters=AnimateAtlas(root/'images/freeplay/sortedLetters')
    filter_frames=[];filter_groups=[]
    for name in ('#','fav','ALL','AB','CD','EH','IL','MN','OR','S','T','UZ'):
        timeline=letters.symbols[name+' move']['TL'];frames=[]
        for i in range(letters.timeline_length(timeline)):
            leaves=letters._render_timeline(timeline,i,IDENTITY,1,())
            frames.append(render_leaves_fixed(leaves,(56,56),(.7,0,0,.7,44,45)).resize((28,28),Image.Resampling.LANCZOS))
        still=Image.new('RGBA',(28,28));still.alpha_composite(frames[0].resize((22,22),Image.Resampling.LANCZOS),(3,3))
        add('filter_'+name.replace('#','number').lower(),[still])
        filter_groups.append(list(range(len(filter_frames),len(filter_frames)+len(frames))))
        filter_frames.extend(frames)
    bank('filters',filter_frames)
    for i,g in enumerate(filter_groups):arrays.append(f'static const u16 fp_filter_anim_{i}[] = {{'+','.join(map(str,g))+'};')
    arrays.append('static const u16 *const fp_filter_anims[] = {'+','.join(f'fp_filter_anim_{i}' for i in range(len(filter_groups)))+'};')
    arrays.append('static const u16 fp_filter_anim_counts[] = {'+','.join(str(len(g)) for g in filter_groups)+'};')
    add('separator',[scaled('freeplay/seperator.png',.3)])
    mini=scaled('freeplay/miniArrow.png',.3)
    add('mini_right',[mini]);add('mini_left',[ImageOps.mirror(mini)])
    for index,album in enumerate(ALBUMS):
        frames,g=sparrow(root/f'images/freeplay/albumRoll/{album}-text.png',.3)
        for name in ('idle','switch'):add(f'title_{index}_{name}',[frames[i] for i in g[name]])
    # Crop transparent borders and deduplicate pixels, while retaining every
    # timeline entry and its original offset. No frame sampling or decimation.
    unique=[];lookup={};entries=[]
    for im in images:
        box=im.getbbox() or (0,0,1,1);crop=im.crop(box);key=(crop.size,crop.tobytes())
        if key not in lookup:lookup[key]=len(unique);unique.append(crop)
        entries.append((lookup[key],box[0],box[1]))
    # Upper 32 rows of pages 1/2 belong to the two capsule frame banks.
    # TIMs load first; capsule uploads subsequently replace only those rows.
    pages=[Image.new('RGBA',(256,240)),Image.new('RGBA',(256,256)),Image.new('RGBA',(256,256)),Image.new('RGBA',(128,224))]
    places={};shelves=[[],[[256,0,32]],[[256,0,32]],[]]
    for index in sorted(range(len(unique)),key=lambda i:-unique[i].height):
        im=unique[index];placed=False
        for page,canvas in enumerate(pages):
            for shelf in shelves[page]:
                if im.height<=shelf[2] and shelf[0]+im.width<=canvas.width:
                    x,y=shelf[:2];shelf[0]+=im.width;placed=True;break
            else:
                y=sum(s[2] for s in shelves[page])
                if y+im.height<=canvas.height and im.width<=canvas.width:
                    x=0;shelves[page].append([im.width,y,im.height]);placed=True
            if placed:
                canvas.alpha_composite(im,(x,y));places[index]=(page,x,y,im.width,im.height);break
        if not placed:raise ValueError(f'Freeplay detail atlas overflow: {len(unique)} unique images')
    for i,im in enumerate(pages):
        filename=f'ui{i}.tim';(out/filename).write_bytes(encode_tim(im,8,(896,512,640,960)[i],256 if i==3 else 0,0,501+i));files.append(filename)
    arrays.append('typedef struct {u8 page,x,y,w,h; signed char dx,dy;} FreeplaySprite;')
    arrays.append('static const FreeplaySprite freeplay_sprites[] = {'+','.join('{'+','.join(map(str,(*places[i],x,y)))+'}' for i,x,y in entries)+'};')
    for name,indices in groups.items():arrays.append('static const u16 fp_'+name+'[] = {'+','.join(map(str,indices))+'};')
    arrays.append('static const u16 fp_weeks[] = {'+','.join(str(groups[f'week_{i}'][0]) for i in range(9))+'};')
    for prefix,names in [('digit',('zero','one','two','three','four','five','six','seven','eight','nine')),('rating',map(str,range(10))),('bpm',map(str,range(10))),('filter',('number','fav','all','ab','cd','eh','il','mn','or','s','t','uz'))]:
        names=list(names)
        arrays.append('static const u16 *const fp_'+prefix+'s[] = {'+','.join('fp_'+prefix+'_'+n for n in names)+'};')
        arrays.append('static const u16 fp_'+prefix+'_counts[] = {'+','.join(str(len(groups[prefix+'_'+n])) for n in names)+'};')
    album_atlas=AnimateAtlas(root/'images/freeplay/albumRoll/freeplayAlbum')
    placeholder=album_atlas.symbols['album art placeholder']['TL']['L'][0]['FR'][0]['E'][0]['ASI']['N']
    original_size=album_atlas.sprites[placeholder].size
    album_frames=[];album_groups=[]
    for album in ALBUMS:
        album_atlas.sprites[placeholder]=Image.open(root/f'images/freeplay/albumRoll/{album}.png').convert('RGBA').resize(original_size,Image.Resampling.LANCZOS)
        album_data=json.loads((root/f'data/ui/freeplay/albums/{album}.json').read_text())
        offsets=album_data.get('albumTitleOffsets',[0,0]);parts={}
        for label in album_atlas.labels():
            name=label['name'];indices=[]
            count=label['duration']
            for i in range(count):
                f=label['start']+(i%label['duration'] if name=='idle' else min(i,label['duration']-1))
                canvas=render_leaves_fixed(album_atlas.leaves_for_frame(f),(336,312),(.9,0,0,.9,-240,108)).resize((112,104),Image.Resampling.LANCZOS)
                indices.append(len(album_frames));album_frames.append(canvas)
            parts[name]=indices
        album_groups.append(parts)
    bank('albums',album_frames)
    for i,parts in enumerate(album_groups):
        for name,indices in parts.items():arrays.append(f'static const u16 fp_album_{i}_{name}[] = {{'+','.join(map(str,indices))+'};')
    for name in ('intro','switch','idle'):
        arrays.append('static const u16 *const fp_album_'+name+'[] = {'+','.join(f'fp_album_{i}_{name}' for i in range(len(ALBUMS)))+'};')
        arrays.append('static const u16 fp_album_'+name+'_counts[] = {'+','.join(str(len(g[name])) for g in album_groups)+'};')
    for name in ('switch','idle'):
        arrays.append('static const u16 *const fp_titles_'+name+'[] = {'+','.join(f'fp_title_{i}_{name}' for i in range(len(ALBUMS)))+'};')
        arrays.append('static const u16 fp_titles_'+name+'_counts[] = {'+','.join(str(len(groups[f'title_{i}_{name}'])) for i in range(len(ALBUMS)))+'};')
    offsets=[json.loads((root/f'data/ui/freeplay/albums/{a}.json').read_text()).get('albumTitleOffsets',[0,0]) for a in ALBUMS]
    arrays.append('static const signed char fp_title_offsets[][2] = {'+','.join('{'+','.join(str(round(v*.3)) for v in p)+'}' for p in offsets)+'};')
    metadata=[]
    for song in SONGS:
        data=json.loads((root/f'data/songs/{song}/{song}-metadata.json').read_text());p=data['playData']
        remix_path=root/f'data/songs/{song}/{song}-metadata-erect.json'
        remix=json.loads(remix_path.read_text()) if remix_path.exists() else data
        variations=[data]*3+[remix]*2;diffs=('easy','normal','hard','erect','nightmare')
        metadata.append(([round(v['timeChanges'][0]['bpm']) for v in variations],
                         [ALBUMS.index(v['playData']['album']) for v in variations],
                         [v['playData'].get('ratings',{}).get(d,0) for v,d in zip(variations,diffs)],
                         [int(d in v['playData']['difficulties']) for v,d in zip(variations,diffs)]))
    for i,(ctype,name) in enumerate((('u16','bpm'),('u8','album'),('u8','rating'),('u8','supports'))):
        arrays.append(f'static const {ctype} fp_song_{name}[][5] = {{'+','.join('{'+','.join(map(str,m[i]))+'}' for m in metadata)+'};')
    arrays.append('static const char *const fp_song_names[] = {'+','.join(json.dumps(json.loads((root/f'data/songs/{s}/{s}-metadata.json').read_text())['songName']) for s in SONGS)+'};')
    return dict(detail_timeline_frames=len(images),detail_unique_sprites=len(unique),album_frames=len(album_frames))
