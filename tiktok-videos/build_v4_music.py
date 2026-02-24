"""V4 - Two-step: pre-mix audio first, then combine with video"""
import subprocess, os

FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe","ffprobe.exe")
BG = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\nba_edwards_dunk.mp4"
VOICE = r"C:\Users\joshs\Downloads\What_if_I_told_you_an_AI_could_All-Rounder_Eleven_v3_02eae27e-f098-4d21-9485-f5f99d13d9c3.mp3"
MUSIC = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\beat_sports.mp3"
MIXED_AUDIO = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\mixed_audio_v4.wav"
OUT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\pg_launch_CLEAN_v4.mp4"
FONT = "C\\\\:/Windows/Fonts/impact.ttf"

# Get voice duration
probe = subprocess.run([FFPROBE, "-v","quiet","-show_entries","format=duration","-of","csv=p=0", VOICE], capture_output=True, text=True)
voice_dur = float(probe.stdout.strip())
dur = voice_dur + 0.5
print(f"Voice duration: {voice_dur:.1f}s, total: {dur:.1f}s")

# Step 1: Pre-mix audio as WAV (no compression artifacts)
print("Step 1: Mixing voice + music to WAV...", flush=True)
mix_cmd = [
    FFMPEG, "-y",
    "-i", VOICE,
    "-i", MUSIC,
    "-filter_complex",
    f"[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=1.3[v];"
    f"[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.5,aloop=loop=-1:size=2e+09,atrim=duration={dur},afade=in:d=0.3,afade=out:st={dur-1}:d=1[m];"
    f"[v][m]amerge=inputs=2,pan=stereo|c0<c0+c2|c1<c1+c3[out]",
    "-map", "[out]",
    "-c:a", "pcm_s16le",
    "-t", str(dur),
    MIXED_AUDIO
]
r = subprocess.run(mix_cmd, capture_output=True, text=True)
if r.returncode != 0:
    print(f"Mix FAILED: {r.stderr[-1000:]}")
    exit(1)
print(f"Mixed audio: {os.path.getsize(MIXED_AUDIO)/1024:.0f} KB")

# Verify mix has actual content
probe2 = subprocess.run([FFPROBE, "-v","quiet","-show_entries","stream=codec_name,channels,duration","-of","csv=p=0", MIXED_AUDIO], capture_output=True, text=True)
print(f"Mix info: {probe2.stdout.strip()}")

# Step 2: Build video with pre-mixed audio
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

print("Step 2: Building video with pre-mixed audio...", flush=True)
cmd = [FFMPEG, "-y",
       "-stream_loop", "-1", "-i", BG,
       "-i", MIXED_AUDIO,
       "-filter_complex", fc,
       "-map", "[outv]", "-map", "1:a",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
       "-t", str(dur), OUT]

r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"DONE: {sz:.1f} MB — {OUT}")
    
    # Verify output has audio
    p = subprocess.run([FFPROBE, "-v","quiet","-show_streams","-select_streams","a", OUT], capture_output=True, text=True)
    print(f"Output audio streams:\n{p.stdout[:500]}")
else:
    print(f"FAILED: {r.stderr[-2000:]}")
