"""Build instrumental-only Freeplay previews with official fractional bounds."""
import argparse,json,math,subprocess,tempfile,wave
from pathlib import Path
from build_freeplay_details import SONGS
from build_weekend1_audio import enc,interleave,run,sectors,SECTOR
from build_remix_audio import add_manifest,verify_xa

def preview_bounds(play_data,duration):
    start=play_data.get('previewStart',0);end=play_data.get('previewEnd',.2)
    if start>=end or start>1:start=0
    if play_data.get('previewStart',0)>=end or end>1:end=.2
    if not 0<=start<end<=1 or not math.isfinite(duration) or duration<=0:raise ValueError('Invalid preview bounds/duration')
    return start*duration,end*duration

def duration(path):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,text=True,check=True)
    return float(json.loads(r.stdout)['format']['duration'])

def build(root,upstream,encoder,ffmpeg,report):
    records=[];mapping=[];files=[]
    for song in SONGS:
        indices=[]
        for variant in ('','-erect'):
            metadata=root/f'data/songs/{song}/{song}-metadata{variant}.json'
            if not metadata.exists():indices.append(indices[0]);continue
            data=json.loads(metadata.read_text());p=data['playData'];inst=p['characters'].get('instrumental','')
            source=root/f'songs/{song}/Inst{("-"+inst) if inst else ""}.ogg'
            start,end=preview_bounds(p,duration(source))
            indices.append(len(records));records.append(dict(song=song,variant=variant,source=source,start=start,end=end))
        mapping.append(indices)
    random_index=len(records);random_source=root/'music/freeplayRandom/freeplayRandom.ogg'
    records.append(dict(song='Random',variant='',source=random_source,start=0,end=duration(random_source)))
    with tempfile.TemporaryDirectory() as td:
        temp=Path(td);silent=temp/'silence.wav'
        run([ffmpeg,'-y','-loglevel','error','-f','lavfi','-i','anullsrc=r=37800:cl=stereo','-t','1',silent])
        silence=[];silent_paths=[]
        for channel in range(4):
            path=temp/f'sil{channel}.xa';enc(encoder,silent,path,channel,37800)
            silent_paths.append(path);silence.append(sectors(path)[0])
        for i,r in enumerate(records):
            length=r['end']-r['start'];fade=min(2,length/2)
            filters=f"atrim=start={r['start']}:end={r['end']},asetpts=PTS-STARTPTS,afade=t=in:d={fade}"
            if r['song']!='Random':filters+=f',afade=t=out:st={length-fade}:d={fade}'
            wav=temp/f'{i}.wav';run([ffmpeg,'-y','-loglevel','error','-i',r['source'],'-af',filters,'-ar','37800','-ac','2',wav])
            with wave.open(str(wav),'rb') as w:r['samples']=w.getnframes()
            if not r['samples']:raise ValueError('Empty preview')
        ordered=sorted(range(len(records)),key=lambda i:records[i]['samples'])
        for first in range(0,len(ordered),4):
            name=f'fp{first//4:02d}.xa';paths=silent_paths.copy()
            for channel,index in enumerate(ordered[first:first+4]):
                r=records[index];path=temp/f'{index}.xa';enc(encoder,temp/f'{index}.wav',path,channel,37800);paths[channel]=path
                count=path.stat().st_size//SECTOR
                if not 0<=count*2016-r['samples']<2016:raise ValueError('Preview samples were truncated')
                r.update(file=len(files),channel=channel,sectors=count*4)
            output=upstream/'iso/music'/name;count=interleave(output,paths,silence)
            files.append(dict(name=name,sectors=count,**verify_xa(output,rate=37800)))
    arrays=['#ifndef FREEPLAY_MUSIC_GENERATED_H','#define FREEPLAY_MUSIC_GENERATED_H']
    arrays.append('static const char *const fp_music_files[] = {'+','.join(json.dumps('\\MUSIC\\'+f['name'].upper()+';1') for f in files)+'};')
    arrays.append('static const struct {unsigned int file,channel,sectors;} fp_music_routes[] = {'+','.join('{'+','.join(str(r[k]) for k in ('file','channel','sectors'))+'}' for r in records)+'};')
    arrays.append('static const unsigned char fp_music_map[26][2] = {'+','.join('{'+','.join(map(str,p))+'}' for p in mapping)+'};')
    arrays.extend([f'#define FP_MUSIC_RANDOM {random_index}','#endif'])
    (upstream/'src/freeplay_music_generated.h').write_text('\n'.join(arrays)+'\n')
    add_manifest(upstream/'funkin.xml',[f['name'] for f in files])
    for r in records:r['source']=str(r['source'].relative_to(root))
    result=dict(sample_rate=37800,stereo=True,instrumental_only=True,records=records,files=files,sectors=sum(f['sectors'] for f in files))
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(previews=len(records),sectors=result['sectors'])))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('root','upstream','psxavenc','report'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--ffmpeg',default='ffmpeg');a=p.parse_args()
    build(a.root,a.upstream,a.psxavenc,a.ffmpeg,a.report)
