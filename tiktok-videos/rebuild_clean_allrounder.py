"""Rebuild launch video with All-Rounder voice + clean language"""
import subprocess, os, requests

FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe","ffprobe.exe")
BG = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\nba_edwards_dunk.mp4"
OUT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\pg_launch_CLEAN_v2.mp4"
FONT = "C\\\\:/Windows/Fonts/impact.ttf"
ELEVEN_KEY = "sk_3bd03ab4e8df0cb2609ff7d1c58b7167a108d24566c432c9"

# Step 1: Find All-Rounder voice
print("Finding All-Rounder voice...", flush=True)
resp = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": ELEVEN_KEY})
voices = resp.json().get("voices", [])
allrounder_id = None
for v in voices:
    print(f"  Voice: {v['name']} ({v['voice_id']})")
    if "round" in v["name"].lower():
        allrounder_id = v["voice_id"]
        print(f"  >>> MATCH: {v['name']}")

if not allrounder_id:
    # Try premade voices
    print("Checking premade voices...", flush=True)
    resp2 = requests.get("https://api.elevenlabs.io/v1/voices?show_legacy=true", headers={"xi-api-key": ELEVEN_KEY})
    for v in resp2.json().get("voices", []):
        if "round" in v["name"].lower():
            allrounder_id = v["voice_id"]
            print(f"  >>> MATCH: {v['name']} ({v['voice_id']})")
            break

if not allrounder_id:
    print("All-Rounder not found in account. Using Josh voice reference file instead...")
    # Use voice design or clone from Josh voice file
    # For now let's check what voices we have
    exit(1)

# Step 2: Generate voiceover
SCRIPT = (
    "What if I told you... an AI could predict NBA games? "
    "74 percent prediction accuracy. 79 consecutive nights exposed. "
    "38 factors analyzed per game. "
    "This is AI sports intelligence. Parlay Guarantee dot com."
)

VO_PATH = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\vo_launch_clean_allrounder.mp3"

print(f"Generating voiceover with All-Rounder ({allrounder_id})...", flush=True)
resp = requests.post(
    f"https://api.elevenlabs.io/v1/text-to-speech/{allrounder_id}",
    headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"},
    json={
        "text": SCRIPT,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.85, "style": 0.6}
    }
)
if resp.status_code != 200:
    print(f"ElevenLabs error: {resp.status_code} {resp.text[:500]}")
    exit(1)

with open(VO_PATH, "wb") as f:
    f.write(resp.content)
print(f"Voiceover saved: {os.path.getsize(VO_PATH)/1024:.0f} KB")

# Get audio duration
probe = subprocess.run([FFPROBE, "-v","quiet","-show_entries","format=duration","-of","csv=p=0", VO_PATH], capture_output=True, text=True)
dur = float(probe.stdout.strip()) + 0.3
print(f"Audio duration: {dur:.1f}s")

GREEN = "#00FF87"
WHITE = "white"

def dt(text, color, s, e, y, sz=56, glow=True):
    text = text.replace("'", "").replace(":", "\\:")
    parts = []
    if glow:
        parts.append(
            f"drawtext=fontfile={FONT}:expansion=none:text='{text}':"
            f"fontsize={sz+4}:fontcolor={color}@0.35:borderw=8:bordercolor={color}@0.2:"
            f"x=(w-text_w)/2:y={y}:"
            f"enable='between(t\\,{s}\\,{e})'"
        )
    parts.append(
        f"drawtext=fontfile={FONT}:expansion=none:text='{text}':"
        f"fontsize={sz}:fontcolor={color}:borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y={y}:"
        f"enable='between(t\\,{s}\\,{e})'"
    )
    return parts

texts = []
texts += dt("WHAT IF I TOLD YOU...", WHITE, 0.2, 3.0, "h/2-200", 60)
texts += dt("AN AI COULD", GREEN, 3.0, 5.5, "h/2-280", 85)
texts += dt("PREDICT NBA GAMES?", GREEN, 3.0, 5.5, "h/2-170", 85)
texts += dt("74% PREDICTION", GREEN, 5.5, 7.5, "h/2-280", 80)
texts += dt("ACCURACY", GREEN, 5.5, 7.5, "h/2-170", 90)
texts += dt("79 CONSECUTIVE", GREEN, 7.5, 9.5, "h/2-280", 80)
texts += dt("NIGHTS EXPOSED", GREEN, 7.5, 9.5, "h/2-170", 80)
texts += dt("38 FACTORS", WHITE, 9.5, 11.0, "h/2-280", 90)
texts += dt("PER GAME", WHITE, 9.5, 11.0, "h/2-170", 90)
texts += dt("AI SPORTS", WHITE, 11.0, 12.8, "h/2-280", 80)
texts += dt("INTELLIGENCE", GREEN, 11.0, 12.8, "h/2-170", 80)
texts += dt("PARLAYGUARANTEE.COM", GREEN, 12.8, dur, "h/2-200", 70)

text_chain = ",".join(texts)

fc = (
    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
    f"crop=1080:1920,setsar=1,fps=30,"
    f"eq=brightness=-0.08:contrast=1.5:saturation=2.0:gamma=1.15,"
    f"colorbalance=rs=0.0:gs=0.12:bs=-0.08:rm=0.0:gm=0.08:bm=0.0,"
    f"trim=duration={dur},setpts=PTS-STARTPTS,"
    f"vignette=PI/3,"
    f"{text_chain}[outv];"
    f"[1:a]aformat=fltp:44100:stereo[outa]"
)

cmd = [FFMPEG, "-y", "-stream_loop", "-1", "-i", BG, "-i", VO_PATH,
       "-filter_complex", fc, "-map", "[outv]", "-map", "[outa]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
       "-shortest", "-t", str(dur), OUT]

print("Building clean launch video with All-Rounder...", flush=True)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"DONE: {sz:.1f} MB — {OUT}")
else:
    print(f"FAILED: {r.stderr[-2000:]}")
