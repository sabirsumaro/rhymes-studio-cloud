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
Create one original preschool English nursery SONG package as valid JSON only.
Required JSON keys: title, description, lyrics, scenes.
Top-level lyrics MUST contain 800-900 English words. This is a hard requirement.
Use 18 scenes. Every scene object must contain exactly these keys: visual, action, lyric, mood.
Every scene's lyric must have 6-8 short singable lines, with roughly 6-8 words per line.
The 18 scene lyric fields together must match the top-level lyrics in the same order.
The song must have verses and a catchy ORIGINAL chorus repeated at most 3 times.
Write a real rhythmic song with rhyme and repeated musical phrasing, not narration, not a story summary.
No copied nursery-rhyme lyrics, known melodies, famous characters, brands, or imitation of a channel.
Characters: {CFG['character_bible']}
Theme: {CFG['topic_seed']}
Age range: preschool. Gentle, safe, positive.
Return valid JSON with no markdown fences. Count the lyric words before responding.
""".strip()
    models = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
    errors = []
    for model in models:
        current_prompt = prompt
        for attempt in range(3):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": GEMINI},
                    json={"contents":[{"parts":[{"text":current_prompt}]}],
                          "generationConfig":{"responseMimeType":"application/json","temperature":0.75,"maxOutputTokens":12000}},
                    timeout=180)
                if r.status_code in (401,403):
                    raise RuntimeError(f"Gemini API key/access error ({r.status_code}); check key and API access.")
                if r.status_code == 429:
                    errors.append(f"{model}: free quota/rate limit (429)")
                    break
                if r.status_code in (500,502,503,504):
                    errors.append(f"{model}: temporary service error ({r.status_code}), attempt {attempt+1}/3")
                    if attempt < 2:
                        import time
                        time.sleep(2 ** attempt)
                        continue
                    break
                if r.status_code == 404:
                    errors.append(f"{model}: model not available (404)")
                    break
                r.raise_for_status()
                body = r.json()
                candidates = body.get("candidates", [])
                if not candidates:
                    errors.append(f"{model}: response contained no candidates")
                    break
                candidate = candidates[0]
                raw = "".join(part.get("text","") for part in candidate.get("content",{}).get("parts",[])).strip()
                # Recover common formatting mistakes, but never invent missing lyrics.
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE).strip()
                if not raw.startswith("{"):
                    a, b = raw.find("{"), raw.rfind("}")
                    if a >= 0 and b > a:
                        raw = raw[a:b+1]
                try:
                    pkg = json.loads(raw)
                except json.JSONDecodeError as e:
                    errors.append(f"{model}: malformed/truncated JSON (attempt {attempt+1}/3)")
                    if attempt < 2:
                        current_prompt = prompt + "\n\nYour previous response was invalid or truncated JSON. Return a complete valid JSON object only. Ensure all quotation marks are escaped and close every array/object. Do not shorten the lyrics."
                        import time
                        time.sleep(1)
                        continue
                    break
                if not isinstance(pkg, dict) or not isinstance(pkg.get("scenes"), list) or len(pkg["scenes"]) < 12:
                    errors.append(f"{model}: response has fewer than 12 valid scenes")
                    if attempt < 2:
                        current_prompt = prompt + "\n\nYour previous response missed required scene objects. Return exactly 18 complete scenes and the full 800-900 word lyrics."
                        continue
                    break
                lyric_text = str(pkg.get("lyrics", "")).strip()
                lyric_words = len(lyric_text.split())
