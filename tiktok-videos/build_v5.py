"""V5 - Music LOUD. Normalize both tracks then mix."""
import subprocess, os

FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe","ffprobe.exe")
BG = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\nba_edwards_dunk.mp4"
VOICE = r"C:\Users\joshs\Downloads\What_if_I_told_you_an_AI_could_All-Rounder_Eleven_v3_02eae27e-f098-4d21-9485-f5f99d13d9c3.mp3"
MUSIC = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\beat_sports.mp3"
OUT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\pg_launch_CLEAN_v5.mp4"
FONT = "C\\\\:/Windows/Fonts/impact.ttf"

probe = subprocess.run([FFPROBE, "-v","quiet","-show_entries","format=duration","-of","csv=p=0", VOICE], capture_output=True, text=True)
dur = float(probe.stdout.strip()) + 0.5
print(f"Total duration: {dur:.1f}s")

# Step 1: Normalize music to -14dB LUFS (loud), then mix
# Voice: normalize to -16 LUFS
# Music: normalize to -20 LUFS (clearly audible behind voice)
NORM_VOICE = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\norm_voice.wav"
NORM_MUSIC = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\norm_music.wav"
MIXED = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\mixed_v5.wav"

# Normalize voice
print("Normalizing voice...", flush=True)
r = subprocess.run([FFMPEG, "-y", "-i", VOICE, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "2", NORM_VOICE], capture_output=True, text=True)
if r.returncode != 0: print(f"FAIL voice norm: {r.stderr[-300:]}"); exit(1)

# Normalize music (boost it hard - original is very quiet at -30dB)
print("Normalizing music (boosting from -30dB)...", flush=True)
r = subprocess.run([FFMPEG, "-y", "-i", MUSIC, "-af", f"loudnorm=I=-14:TP=-1:LRA=7,aloop=loop=-1:size=2e+09,atrim=duration={dur}", "-ar", "44100", "-ac", "2", NORM_MUSIC], capture_output=True, text=True)
if r.returncode != 0: print(f"FAIL music norm: {r.stderr[-300:]}"); exit(1)

# Check volumes
for f in [NORM_VOICE, NORM_MUSIC]:
    r = subprocess.run([FFMPEG, "-i", f, "-af", "volumedetect", "-f", "null", "NUL"], capture_output=True, text=True)
    for line in r.stderr.split('\n'):
        if 'mean_volume' in line or 'max_volume' in line:
            print(f"  {os.path.basename(f)}: {line.strip()}")

# Mix: voice full + music at 0.6 (after normalization it'll be clearly audible)
print("Mixing...", flush=True)
r = subprocess.run([FFMPEG, "-y", "-i", NORM_VOICE, "-i", NORM_MUSIC,
    "-filter_complex",
    "[0:a]volume=1.0[v];[1:a]volume=0.6[m];[v][m]amerge=inputs=2,pan=stereo|c0<c0+c2|c1<c1+c3,alimiter=limit=0.95[out]",
    "-map", "[out]", "-c:a", "pcm_s16le", "-t", str(dur), MIXED], capture_output=True, text=True)
if r.returncode != 0: print(f"FAIL mix: {r.stderr[-300:]}"); exit(1)

# Verify
r = subprocess.run([FFMPEG, "-i", MIXED, "-af", "volumedetect", "-f", "null", "NUL"], capture_output=True, text=True)
for line in r.stderr.split('\n'):
    if 'mean_volume' in line or 'max_volume' in line:
        print(f"  MIX: {line.strip()}")

# Step 2: Build video
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

seg = dur / 6
texts = []
texts += dt("WHAT IF I TOLD YOU...", WHITE, 0.2, seg, "h/2-200", 60)
texts += dt("AN AI COULD", GREEN, seg, seg*2, "h/2-280", 85)
texts += dt("PREDICT NBA GAMES?", GREEN, seg, seg*2, "h/2-170", 85)
texts += dt("74% PREDICTION", GREEN, seg*2, seg*3, "h/2-280", 80)
texts += dt("ACCURACY", GREEN, seg*2, seg*3, "h/2-170", 90)
texts += dt("79 CONSECUTIVE", GREEN, seg*3, seg*4, "h/2-280", 80)
texts += dt("NIGHTS EXPOSED", GREEN, seg*3, seg*4, "h/2-170", 80)
texts += dt("38 FACTORS", WHITE, seg*4, seg*4.7, "h/2-280", 90)
texts += dt("PER GAME", WHITE, seg*4, seg*4.7, "h/2-170", 90)
texts += dt("AI SPORTS", WHITE, seg*4.7, seg*5.4, "h/2-280", 80)
texts += dt("INTELLIGENCE", GREEN, seg*4.7, seg*5.4, "h/2-170", 80)
texts += dt("PARLAYGUARANTEE.COM", GREEN, seg*5.4, dur, "h/2-200", 70)
text_chain = ",".join(texts)

fc = (
    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
    f"crop=1080:1920,setsar=1,fps=30,"
    f"eq=brightness=-0.08:contrast=1.5:saturation=2.0:gamma=1.15,"
    f"colorbalance=rs=0.0:gs=0.12:bs=-0.08:rm=0.0:gm=0.08:bm=0.0,"
    f"trim=duration={dur},setpts=PTS-STARTPTS,"
    f"vignette=PI/3,"
    f"{text_chain}[outv]"
)

print("Building video...", flush=True)
cmd = [FFMPEG, "-y", "-stream_loop", "-1", "-i", BG, "-i", MIXED,
       "-filter_complex", fc, "-map", "[outv]", "-map", "1:a",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
       "-t", str(dur), OUT]

r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"DONE: {sz:.1f} MB — {OUT}")
else:
    print(f"FAILED: {r.stderr[-2000:]}")
