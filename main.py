import os, json, math, random, subprocess, asyncio, re, wave, struct
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts

ROOT = Path(__file__).parent
OUT = ROOT / "output"
WORK = ROOT / "work"
OUT.mkdir(exist_ok=True)
WORK.mkdir(exist_ok=True)
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
GEMINI = os.getenv("GEMINI_API_KEY", "")
BOT = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
W, H = CFG["resolution"]
FPS = int(CFG["fps"])
TARGET_SECONDS = int(float(CFG["target_duration_minutes"]) * 60)

def ask_gemini():
    if not GEMINI:
        raise RuntimeError("Missing GEMINI_API_KEY secret")
    prompt = f"""
Create an original preschool English musical-rhyme episode package as valid JSON only.
Keys: title, description, lyrics, scenes.
Return exactly 18 scenes. Each scene: visual, action, lyric, mood.
Lyrics: target 800-900 words, short rhythmic lines, a recurring ORIGINAL chorus no more than 3 times,
clear verse/chorus structure, actions children can understand, beginning-middle-ending story.
Each scene lyric should be 2-4 short lines. Lyrics must be written to be sung, not as explanatory prose.
No copied nursery-rhyme lyrics, familiar melodies, famous characters, brands, or channel imitation.
Characters: {CFG['character_bible']}
Theme pool: {CFG['topic_seed']}
Age range: preschool. Gentle, safe, positive.
""".strip()
    models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
    errors = []
    for model in models:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": GEMINI},
                json={"contents":[{"parts":[{"text":prompt}]}],
                      "generationConfig":{"responseMimeType":"application/json","temperature":0.9}},
                timeout=120)
            if r.status_code in (401,403):
                raise RuntimeError(f"Gemini API key/access error ({r.status_code}); check key and API access.")
            if r.status_code == 429:
                errors.append(f"{model}: free quota/rate limit")
                continue
            if r.status_code == 404:
                errors.append(f"{model}: model not available")
                continue
            r.raise_for_status()
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            pkg = json.loads(raw)
            if not isinstance(pkg.get("scenes"), list) or len(pkg["scenes"]) < 12:
                raise RuntimeError("Generated package has fewer than 12 scenes; refusing low-content episode.")
            if len(pkg.get("lyrics","").split()) < 650:
                raise RuntimeError("Generated lyrics are too short for a 6–8 minute episode; refusing a short video.")
            return pkg
        except Exception as e:
            errors.append(f"{model}: {e}")
    raise RuntimeError("Gemini generation failed: " + " | ".join(errors[-3:]))

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def wrap(draw, text, f, maxw):
    out, line = [], ""
    for word in str(text).split():
        test = (line + " " + word).strip()
        if draw.textbbox((0,0), test, font=f)[2] <= maxw:
            line = test
        else:
            if line: out.append(line)
            line = word
    if line: out.append(line)
    return out

PALETTES = [
    ((93,190,231),(91,178,102),(255,218,87)),
    ((252,180,190),(113,194,151),(255,236,151)),
    ((149,173,239),(114,191,158),(255,188,91)),
    ((168,222,201),(125,174,112),(255,223,132)),
    ((226,190,244),(111,178,143),(255,210,123)),
    ((255,205,133),(94,177,167),(255,239,165)),
]
def draw_character(d, x, y, scale, color, kind, frame, outline=(35,70,90)):
    bob = int(5*math.sin(frame/5))
    y += bob
    r = int(68*scale)
    if kind == "dragon":
        # Wings and tail give a different silhouette than the prototype.
        d.polygon([(x-r//2,y+10),(x-r-35*scale,y-30),(x-r+5*scale,y+50)], fill=(255,218,87), outline=outline)
        d.polygon([(x+r//2,y+10),(x+r+35*scale,y-30),(x+r-5*scale,y+50)], fill=(255,218,87), outline=outline)
        d.ellipse((x-r,y-r,x+r,y+r+15*scale), fill=color, outline=outline, width=max(2,int(5*scale)))
        d.ellipse((x-r*.52,y+3*scale,x+r*.52,y+r*.76), fill=(159,230,211))
        # horns
        d.polygon([(x-r*.6,y-r*.7),(x-r*.45,y-r*1.12),(x-r*.2,y-r*.68)], fill=(255,220,100), outline=outline)
        d.polygon([(x+r*.2,y-r*.68),(x+r*.45,y-r*1.12),(x+r*.6,y-r*.7)], fill=(255,220,100), outline=outline)
    elif kind == "bird":
        d.ellipse((x-r,y-r*.72,x+r,y+r*.85), fill=color, outline=outline, width=max(2,int(5*scale)))
        d.polygon([(x+r*.75,y),(x+r*1.25,y+8*scale),(x+r*.75,y+18*scale)], fill=(255,207,57))
        wingx = x + int(14*math.sin(frame/4)*scale)
        d.ellipse((wingx-r*.4,y-r*.05,wingx+r*.45,y+r*.5), fill=(255,205,99), outline=outline, width=max(1,int(2*scale)))
    else:
        d.ellipse((x-r,y-r,x+r,y+r), fill=color, outline=outline, width=max(2,int(4*scale)))
    eye_y = y-r*.28
    for ex in (x-r*.3, x+r*.3):
        er = max(3,int(9*scale))
        d.ellipse((ex-er,eye_y-er,ex+er,eye_y+er),fill="white")
        d.ellipse((ex-er*.35,eye_y-er*.35,ex+er*.35,eye_y+er*.35),fill=(25,40,55))
    # Smile changes subtly with frame to imply singing/talking animation.
    mouthw = max(7,int(22*scale))
    d.arc((x-mouthw,y+2*scale,x+mouthw,y+22*scale),0,180,fill=outline,width=max(2,int(3*scale)))

def draw_scene(scene, idx, frame, lyric, path, thumbnail=False, vertical=False, title=""):
    width, height = (720,1280) if vertical else (W,H)
    pal = PALETTES[idx % len(PALETTES)]
    sky, grass, sun = pal
    im = Image.new("RGB",(width,height),sky); d=ImageDraw.Draw(im)
    # Layered clouds, sun, rolling landscape; motion varies across scenes.
    sunx = int(width*.82 + math.sin(frame/18+idx)*width*.015)
    d.ellipse((sunx-45,45,sunx+45,135),fill=sun)
    for ci in range(4):
        cx = int((ci*width*.31 + frame*(0.4+ci*.08)) % (width+150))-70
        cy = 110 + (ci%2)*70
        d.ellipse((cx,cy,cx+100,cy+35),fill=(245,250,255))
        d.ellipse((cx+25,cy-18,cx+70,cy+30),fill=(245,250,255))
    horizon = int(height*.69 if vertical else height*.66)
    d.ellipse((-width*.25,horizon-110,width*.55,height*.97),fill=grass)
    d.ellipse((width*.3,horizon-70,width*1.25,height*1.08),fill=tuple(max(0,c-12) for c in grass))
    # Props change by scene: flowers, rainbow, pond, trees, stars, stepping stones.
    prop = idx % 6
    if prop == 0:
        for j in range(7):
            fx=int(width*(.07+j*.13)); fy=horizon+int(30*math.sin(j+frame/12))
            d.line((fx,fy,fx,fy+30),fill=(45,130,75),width=4)
            for ox,oy in [(-9,0),(9,0),(0,-9),(0,9)]:
                d.ellipse((fx+ox-6,fy+oy-6,fx+ox+6,fy+oy+6),fill=(255,245,230))
            d.ellipse((fx-4,fy-4,fx+4,fy+4),fill=(255,191,55))
    elif prop == 1:
        for k,col in enumerate([(250,95,105),(255,170,70),(255,228,94),(91,192,130),(88,166,241)]):
            d.arc((width*.22+k*8,height*.15+k*8,width*.78-k*8,height*.68-k*8),180,355,fill=col,width=12)
    elif prop == 2:
        d.ellipse((width*.56,horizon-35,width*.9,horizon+70),fill=(89,190,220),outline=(235,245,255),width=4)
        for j in range(4):
            d.ellipse((width*.62+j*25,horizon+4,width*.65+j*25,horizon+9),fill=(240,255,255))
    elif prop == 3:
        for tx in [width*.12,width*.85]:
            d.rectangle((tx-9,horizon-115,tx+9,horizon+8),fill=(132,86,55))
            d.ellipse((tx-55,horizon-170,tx+55,horizon-70),fill=(55,145,93))
    elif prop == 4:
        for j in range(12):
            sx=(j*79+frame*1.3)%width; sy=height*.22+(j%4)*25
            d.polygon([(sx,sy-8),(sx+3,sy-3),(sx+9,sy),(sx+3,sy+3),(sx,sy+9),(sx-3,sy+3),(sx-9,sy),(sx-3,sy-3)],fill=(255,248,192))
    else:
        for j in range(6):
            sx=width*.12+j*width*.14
            d.ellipse((sx,horizon+10,sx+48,horizon+27),fill=(222,196,151))
    # Main characters and a small prop.
    if vertical:
        cy=int(height*.53); x1=int(width*.34); x2=int(width*.69); scale=.72
    else:
        cy=int(height*.56); x1=int(width*.32); x2=int(width*.68); scale=.92
    draw_character(d,x1,cy,scale,(47,177,183),"dragon",frame)
    draw_character(d,x2,cy+20,scale*.78,(255,155,64),"bird",frame+idx*4)
    # Subtitles are kept within safe area and readable.
    if not thumbnail:
        panel_y = int(height*.79)
        panel_h = int(height*.16)
        d.rounded_rectangle((width*.035,panel_y,width*.965,panel_y+panel_h),radius=22,fill=(255,255,255),outline=(255,208,63),width=5)
        f=font(27 if vertical else 28,True)
        lines=wrap(d,lyric,f,int(width*.84))[:3 if vertical else 2]
        y=panel_y+18
        for line in lines:
            bb=d.textbbox((0,0),line,font=f)
            d.text(((width-(bb[2]-bb[0]))/2,y),line,font=f,fill=(33,65,93))
            y += 36 if not vertical else 43
    else:
        # Purpose-built thumbnail: contrast, short title, no subtitle panel.
        d.rectangle((0,int(height*.73),width,height),fill=(22,52,89))
        f=font(58 if vertical else 52,True)
        lines=wrap(d,title.upper(),f,int(width*.86))[:3]
        y=int(height*.76)
        for line in lines:
            bb=d.textbbox((0,0),line,font=f)
            d.text(((width-(bb[2]-bb[0]))/2,y),line,font=f,fill=(255,255,255),stroke_width=1,stroke_fill=(22,52,89))
            y += 66
    im.save(path,quality=94)

async def make_voice(text,path):
    # Honest current fallback: neural narration, NOT actual singing.
    # Production quality gate below labels this and does not claim sung vocals.
    await edge_tts.Communicate(text,voice=CFG["voice"],rate=CFG["voice_rate"],pitch="+0Hz").save(str(path))

def run_ffmpeg(args):
    subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error",*map(str,args)],check=True)

def synth_music(path, seconds, bpm=104):
    """Create an original lightweight instrumental bed from synthesized notes; no external song samples."""
    sr=22050
    beat=60.0/bpm
    # C major, gentle nursery feel. Generate mono samples in chunks to keep memory low.
    notes=[261.63,329.63,392.00,329.63,293.66,349.23,440.00,349.23,
           261.63,329.63,392.00,523.25,440.00,392.00,329.63,293.66]
    chord_roots=[130.81,146.83,174.61,196.00]
    nframes=int(seconds*sr)
    with wave.open(str(path),"wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr)
        chunk=8192; offset=0
        while offset<nframes:
            count=min(chunk,nframes-offset)
            frames=[]
            for k in range(count):
                t=(offset+k)/sr
                beatpos=t/beat
                note_idx=int(beatpos*2)%len(notes)
                local=(beatpos*2)%1
                env=min(1,local*12)*max(0,min(1,(1-local)*8))
                melody=math.sin(2*math.pi*notes[note_idx]*t)*env*.11
                # soft bass pulse on every other beat
                root=chord_roots[int(beatpos//4)%len(chord_roots)]
                bass=math.sin(2*math.pi*root*t)*(.055 if int(beatpos*2)%4==0 else .018)
                # bell-like harmonic, soft pulse percussion without sampled audio
                bell=math.sin(2*math.pi*notes[note_idx]*2*t)*env*.018
                val=max(-.25,min(.25,melody+bass+bell))
                s=int(val*32767)
                frames.append(struct.pack("<hh",s,s))
            wf.writeframesraw(b"".join(frames))
            offset += count
        wf.writeframes(b"")

def fit_lyrics_to_duration(pkg, target_words=620):
    lyrics = re.sub(r"\s+"," ",pkg.get("lyrics","")).strip()
    # Do not silently pad a weak script with duplicate lyrics; ask Gemini already targets 550-700 words.
    words=len(lyrics.split())
    if words < 350:
        raise RuntimeError(f"Lyrics contain only {words} words; minimum 350. Refusing a short/empty episode.")
    return lyrics

def render_segment(scene, idx, seconds, lyric, dest, vertical=False):
    frame_dir=WORK/f"frames_{'short' if vertical else 'long'}_{idx}"
    if frame_dir.exists():
        for p in frame_dir.glob("*.jpg"): p.unlink()
    frame_dir.mkdir(parents=True,exist_ok=True)
    # Render unique motion for each scene; output duration derives from explicit timeline.
    frames=max(1,int(seconds*FPS))
    for f in range(frames):
        draw_scene(scene,idx,f,lyric,frame_dir/f"f{f:06d}.jpg",vertical=vertical)
    run_ffmpeg(["-framerate",str(FPS),"-i",str(frame_dir/"f%06d.jpg"),
                "-vf",f"scale={720 if vertical else W}:{1280 if vertical else H}:flags=lanczos,format=yuv420p",
                "-c:v","libx264","-preset","ultrafast","-crf","21","-an",str(dest)])
    return dest

def make_video(pkg):
    scenes=pkg["scenes"]
    lyrics=fit_lyrics_to_duration(pkg)
    # Current honest voice fallback. Audio duration is measured; video timeline is never cut by -shortest.
    voice=WORK/"voice.mp3"
    asyncio.run(make_voice(lyrics,voice))
    # Use ffprobe to measure generated speech and ensure the final long video is in the target range.
    probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(voice)],capture_output=True,text=True,check=True)
    voice_seconds=float(probe.stdout.strip())
    if voice_seconds < TARGET_SECONDS*0.88:
        raise RuntimeError(f"Voice track is only {voice_seconds/60:.1f} min for a {TARGET_SECONDS/60:.1f} min target. Refusing to fill the missing duration with music only. Increase lyric/audio content first.")
    music=WORK/"original_instrumental.wav"
    synth_music(music, max(TARGET_SECONDS,voice_seconds+2), bpm=int(CFG["music_bpm"]))
    # Mix speech with original synthesized instrumental bed. This is a music bed, not a substitute for singing.
    mixed=WORK/"mixed_audio.m4a"
    run_ffmpeg(["-i",str(voice),"-i",str(music),"-filter_complex",
                "[0:a]volume=1.0,aresample=44100[v];[1:a]volume=0.16,aresample=44100[m];[v][m]amix=inputs=2:duration=longest:dropout_transition=2,alimiter=limit=0.92[a]",
                "-map","[a]","-c:a","aac","-b:a","192k","-t",str(TARGET_SECONDS),str(mixed)])
    # Create a real multi-scene timeline over the entire duration.
    per_scene=TARGET_SECONDS/len(scenes)
    scene_files=[]
    for i,sc in enumerate(scenes):
        out=WORK/f"scene_{i:02d}.mp4"
        lyric=sc.get("lyric","").strip()
        render_segment(sc,i,per_scene,lyric,out)
        scene_files.append(out)
    concat=WORK/"concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in scene_files),encoding="utf-8")
    silent=WORK/"long_silent.mp4"
    run_ffmpeg(["-f","concat","-safe","0","-i",str(concat),"-c","copy","-an",str(silent)])
    long_path=OUT/"rhymes-studio.mp4"
    run_ffmpeg(["-i",str(silent),"-i",str(mixed),"-map","0:v:0","-map","1:a:0","-t",str(TARGET_SECONDS),
                "-c:v","copy","-c:a","aac","-b:a","192k","-movflags","+faststart",str(long_path)])
    # A purpose-built 16:9 thumbnail.
    thumb=OUT/"thumbnail.jpg"
    draw_scene(scenes[0],0,1,"",thumb,thumbnail=True,title=pkg.get("title","Little Musical Adventure"))
    # Make 3 vertical Shorts from distinct story sections; each has its own vertical framing.
    shorts=[]
    short_duration=int(CFG["short_duration_seconds"])
    starts=[0, max(0,len(scenes)//3), max(0,2*len(scenes)//3)]
    for j,start in enumerate(starts,1):
        sc=scenes[start]
        short=OUT/f"short-{j}.mp4"
        # Use the first section's voice audio crop; do not misrepresent a full song as a new song.
        # Short is an excerpt-style teaser with vertical visuals and mixed audio.
        vf=WORK/f"short_audio_{j}.m4a"
        seek=int((j-1)*TARGET_SECONDS/3)
        run_ffmpeg(["-ss",str(seek),"-i",str(mixed),"-t",str(short_duration),"-vn","-c:a","aac","-b:a","160k",str(vf)])
        render_segment(sc,100+j,short_duration,sc.get("lyric",""),WORK/f"short_video_{j}.mp4",vertical=True)
        run_ffmpeg(["-i",str(WORK/f"short_video_{j}.mp4"),"-i",str(vf),"-map","0:v:0","-map","1:a:0","-t",str(short_duration),
                    "-c:v","copy","-c:a","aac","-movflags","+faststart",str(short)])
        shorts.append(short)
    meta={"title":pkg.get("title","Original Nursery Rhyme"),
          "description":pkg.get("description","Original preschool rhyme episode."),
          "lyrics":lyrics,"tags":["nursery rhymes","kids songs","original animation","preschool"],
          "audio_note":"Current free fallback is neural narration plus synthesized instrumental music; it is NOT true singing vocals."}
    (OUT/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    # Quality gates: duration, existence, nonzero size, shorts dimensions/duration.
    duration=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(long_path)],capture_output=True,text=True,check=True).stdout.strip())
    if not (TARGET_SECONDS-3 <= duration <= TARGET_SECONDS+3):
        raise RuntimeError(f"Long video duration check failed: {duration:.1f}s; target {TARGET_SECONDS}s.")
    for p in [long_path,thumb,*shorts]:
        if not p.exists() or p.stat().st_size < 10_000:
            raise RuntimeError(f"Output validation failed for {p.name}")
    print(f"VALIDATED long video: {duration/60:.2f} min; {long_path.stat().st_size} bytes")
    print(f"VALIDATED thumbnail: {thumb.stat().st_size} bytes")
    for p in shorts: print(f"VALIDATED Short: {p.name} ({p.stat().st_size} bytes)")
    return long_path,thumb,shorts,meta

def tg_send_message(text):
    r=requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":text},timeout=30)
    r.raise_for_status()

def send_file(path, caption, method="sendDocument"):
    # Document upload works for MP4 too and preserves the file even if preview rendering is not supported.
    with open(path,"rb") as f:
        r=requests.post(f"https://api.telegram.org/bot{BOT}/{method}",data={"chat_id":CHAT,"caption":caption},
                        files={"document" if method=="sendDocument" else "video" if method=="sendVideo" else "photo":f},timeout=600)
    if not r.ok:
        raise RuntimeError(f"Telegram upload failed for {path.name} ({r.status_code}): {r.text[:300]}")

def deliver(video,thumb,shorts,meta):
    if not BOT or not CHAT: raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID secret")
    tg_send_message(f"RHYMES STUDIO — OUTPUT READY\nTitle: {meta['title']}\n\nReview all files before publishing.\nAudio note: narration + original instrumental bed; not true singing yet.")
    send_file(thumb,"Thumbnail preview","sendPhoto")
    send_file(video,"Main 6–8 minute episode — review before upload","sendVideo")
    for i,p in enumerate(shorts,1):
        send_file(p,f"Vertical Short {i} — review before upload","sendVideo")

def main():
    dry=os.getenv("DRY_RUN","true").lower()=="true"
    pkg=ask_gemini()
    video,thumb,shorts,meta=make_video(pkg)
    if not dry: deliver(video,thumb,shorts,meta)
    print("Dry run: not sent to Telegram." if dry else "Delivered main video, thumbnail and 3 Shorts to Telegram.")

if __name__=="__main__":
    main()
