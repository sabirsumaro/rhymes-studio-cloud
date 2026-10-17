import os, json, time, math, random, subprocess, asyncio, textwrap, re
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont
import edge_tts

ROOT=Path(__file__).parent
OUT=ROOT/"output"; WORK=ROOT/"work"
OUT.mkdir(exist_ok=True); WORK.mkdir(exist_ok=True)
CFG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
GEMINI=os.getenv("GEMINI_API_KEY","")
BOT=os.getenv("TELEGRAM_BOT_TOKEN","")
CHAT=os.getenv("TELEGRAM_CHAT_ID","")

def ask_gemini():
    if not GEMINI: raise RuntimeError("Missing GEMINI_API_KEY secret")
    prompt=f"""Create an ORIGINAL preschool English nursery-rhyme video package.
Return ONLY valid JSON with keys: title, description, lyrics, scenes.
scenes must be an array of 10 objects, each with keys: visual, action, lyric.
Each scene lyric must be original, short, sing-song English and together the lyrics should have a coherent beginning-middle-ending story.
Do not quote or closely imitate existing nursery rhymes, known lyrics, melodies, characters, brands, or channels.
Avoid generic repeated filler. Give a distinctive story, concrete actions, a memorable original chorus repeated at most twice, and a satisfying ending.
Target duration is about {CFG['target_duration_minutes']} minutes; make lyrics long enough for slow preschool narration, but do not pad with repeated lines.
Characters: {CFG['character_bible']}
Topic pool: {CFG['topic_seed']}
Safety: gentle, age-appropriate, no dangerous imitation, no scary content.
""".strip()
    models=["gemini-3.8-flash","gemini-3.5-flash","gemini-3.1-flash-lite"]
    last=None
    for model in models:
        try:
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI}"
            r=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0.95}},timeout=90)
            if r.status_code==429: last=RuntimeError("Gemini free quota/rate limit reached"); continue
            r.raise_for_status()
            txt=r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(txt)
        except Exception as e: last=e
    raise RuntimeError(f"Text generation failed: {last}")

def font(size, bold=False):
    candidates=[
      "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for f in candidates:
        if os.path.exists(f): return ImageFont.truetype(f,size)
    return ImageFont.load_default()

def wrap(draw, text, f, maxw):
    words=text.split(); lines=[]; cur=""
    for w in words:
        test=(cur+" "+w).strip()
        if draw.textbbox((0,0),test,font=f)[2] <= maxw: cur=test
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return lines

def draw_scene(scene, idx, frame, total, lyric, path, thumbnail=False):
    W,H=1280,720
    im=Image.new("RGB",(W,H),(111,205,235)); d=ImageDraw.Draw(im)
    # Gentle animated sky and sun; motion changes by frame.
    d.ellipse((1000+int(10*math.sin(frame/9)),55,1110+int(10*math.sin(frame/9)),165),fill=(255,221,91))
    d.rectangle((0,475,W,H),fill=(105,194,111))
    # rolling hills
    d.ellipse((-180,390,600,700),fill=(84,177,102)); d.ellipse((470,400,1450,760),fill=(65,160,94))
    # simple original character: Pip, bobbing and stepping
    bob=int(9*math.sin(frame/4))
    x=370+int(22*math.sin(frame/8)); y=365+bob
    # wings
    d.ellipse((x-95,y-25,x-25,y+55),fill=(255,220,87),outline=(40,111,127),width=5)
    d.ellipse((x+30,y-25,x+100,y+55),fill=(255,220,87),outline=(40,111,127),width=5)
    # body/head
    d.ellipse((x-75,y-100,x+75,y+75),fill=(47,177,183),outline=(26,98,117),width=6)
    # belly
    d.ellipse((x-40,y-15,x+40,y+60),fill=(157,229,207))
    # eyes and smile
    d.ellipse((x-38,y-55,x-15,y-27),fill="white"); d.ellipse((x+15,y-55,x+38,y-27),fill="white")
    d.ellipse((x-30,y-48,x-20,y-34),fill=(20,40,55)); d.ellipse((x+22,y-48,x+32,y-34),fill=(20,40,55))
    d.arc((x-27,y-23,x+28,y+18),0,180,fill=(20,70,75),width=5)
    # little orange bird moves in opposite direction
    bx=850-int(25*math.sin(frame/7)); by=390+int(7*math.sin(frame/3))
    d.ellipse((bx-65,by-50,bx+65,by+65),fill=(255,155,64),outline=(125,82,48),width=5)
    d.ellipse((bx-28,by-25,bx-10,by-4),fill="white"); d.ellipse((bx+12,by-25,bx+30,by-4),fill="white")
    d.ellipse((bx-21,by-20,bx-13,by-10),fill=(30,40,50)); d.ellipse((bx+19,by-20,bx+27,by-10),fill=(30,40,50))
    d.polygon([(bx+55,by),(bx+88,by+10),(bx+55,by+20)],fill=(255,210,61))
    # moving stars / flowers
    for j in range(6):
        fx=(100+j*205+frame*3)%(W+40)-20; fy=225+(j%3)*45
        d.ellipse((fx,fy,fx+14,fy+14),fill=(255,255,255))
    # lyric caption panel
    d.rounded_rectangle((65,565,1215,690),radius=28,fill=(255,255,255),outline=(255,208,63),width=5)
    lines=wrap(d,lyric,font(30,True),1080)[:2]
    yy=585
    for line in lines:
        bb=d.textbbox((0,0),line,font=font(30,True)); d.text(((W-(bb[2]-bb[0]))/2,yy),line,font=font(30,True),fill=(33,65,93)); yy+=40
    if thumbnail:
        d.rounded_rectangle((60,40,800,150),radius=24,fill=(255,255,255),outline=(255,190,46),width=6)
        title=scene.get("title","A New Little Adventure")
        title_lines=wrap(d,title.upper(),font(42,True),690)[:2]
        ty=55
        for line in title_lines:
            d.text((85,ty),line,font=font(42,True),fill=(29,79,125),stroke_width=1); ty+=48
    im.save(path,quality=94)

async def make_voice(text, path):
    # This is neural narration, not singing. Voice availability can change.
    communicate=edge_tts.Communicate(text, voice="en-US-AvaNeural", rate="-8%", pitch="+2Hz")
    await communicate.save(str(path))

def run_ffmpeg(args):
    subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error",*map(str,args)],check=True)

def make_video(pkg, dry):
    scenes=pkg.get("scenes",[])
    if not scenes: raise RuntimeError("No scenes in generated package")
    vid=OUT/"rhymes-studio.mp4"; thumb=OUT/"thumbnail.jpg"; audio=WORK/"voice.mp3"
    lyrics=pkg.get("lyrics","")
    asyncio.run(make_voice(lyrics,audio))
    # Render moving 2D scene frames. This is deliberately a prototype animation engine,
    # not a claim of 3D/cartoon-studio quality.
    fps=24; seconds_per_scene=6
    frame_dir=WORK/"frames"; frame_dir.mkdir(exist_ok=True)
    for p in frame_dir.glob("*.jpg"): p.unlink()
    frame_idx=0
    for si,sc in enumerate(scenes):
        line=(sc.get("lyric") or lyrics[:120] or "Come along and play with me!")
        for f in range(seconds_per_scene*fps):
            p=frame_dir/f"f{frame_idx:06d}.jpg"
            draw_scene(sc,si,f,seconds_per_scene*fps,line,p)
            frame_idx+=1
    concat=WORK/"frames.txt"
    concat.write_text("\n".join(f"file '{(frame_dir/f).as_posix()}'" for f in sorted(p.name for p in frame_dir.glob("*.jpg")))+"\n",encoding="utf-8")
    # Join video and neural narration. Loop audio/video to target duration with a hard cap.
    target=max(60,int(float(CFG["target_duration_minutes"])*60))
    run_ffmpeg(["-framerate",str(fps),"-i",str(frame_dir/"f%06d.jpg"),"-i",str(audio),"-vf",f"scale={CFG['resolution'][0]}:{CFG['resolution'][1]}:flags=lanczos,format=yuv420p","-t",str(target),"-c:v","libx264","-preset","ultrafast","-crf","22","-c:a","aac","-b:a","160k","-shortest",str(vid)])
    first=scenes[0].copy(); first["title"]=pkg.get("title","A New Little Adventure")
    draw_scene(first,0,1,1,"",thumb,thumbnail=True)
    meta={"title":pkg.get("title","Original Nursery Rhyme"),"description":pkg.get("description","Original English nursery rhyme created by Rhymes Studio."),"lyrics":lyrics,"tags":["nursery rhymes","kids songs","original animation","preschool"]}
    (OUT/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    return vid,thumb,meta

def send_telegram(video,thumb,meta):
    if not BOT or not CHAT: raise RuntimeError("Missing Telegram secrets")
    text=f"RHYMES STUDIO — VIDEO READY\n\nTitle: {meta['title']}\n\n{meta['description'][:700]}\n\nReview before publishing. This prototype uses neural narration, not sung vocals."
    requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",data={"chat_id":CHAT,"text":text},timeout=30).raise_for_status()
    with open(thumb,"rb") as f:
        requests.post(f"https://api.telegram.org/bot{BOT}/sendPhoto",data={"chat_id":CHAT,"caption":"Thumbnail preview"},files={"photo":f},timeout=60).raise_for_status()
    # Telegram Bot API has a file-size limit; fail clearly rather than silently losing delivery.
    with open(video,"rb") as f:
        r=requests.post(f"https://api.telegram.org/bot{BOT}/sendVideo",data={"chat_id":CHAT,"supports_streaming":"true","caption":"Generated video — review before upload"},files={"video":f},timeout=600)
    if not r.ok:
        raise RuntimeError(f"Telegram video upload failed ({r.status_code}): {r.text[:500]}")

def main():
    dry=os.getenv("DRY_RUN","true").lower()=="true"
    pkg=ask_gemini()
    video,thumb,meta=make_video(pkg,dry)
    if not dry: send_telegram(video,thumb,meta)
    print(f"Generated: {video} ({video.stat().st_size} bytes)")
    print(f"Thumbnail: {thumb}")
    print("Dry run: not sent to Telegram." if dry else "Delivered to Telegram.")

if __name__=="__main__":
    main()
