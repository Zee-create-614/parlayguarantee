"""Final clean launch video - All-Rounder voice + sports beat music + Edwards dunk BG"""
import subprocess, os

FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe","ffprobe.exe")
BG = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\nba_edwards_dunk.mp4"
AUDIO = r"C:\Users\joshs\Downloads\What_if_I_told_you_an_AI_could_All-Rounder_Eleven_v3_02eae27e-f098-4d21-9485-f5f99d13d9c3.mp3"
MUSIC = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\beat_sports.mp3"
OUT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\pg_launch_CLEAN_FINAL2.mp4"
FONT = "C\\\\:/Windows/Fonts/impact.ttf"

probe = subprocess.run([FFPROBE, "-v","quiet","-show_entries","format=duration","-of","csv=p=0", AUDIO], capture_output=True, text=True)
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

# Mix voiceover (loud) + music (background, lower volume)
fc = (
    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
    f"crop=1080:1920,setsar=1,fps=30,"
    f"eq=brightness=-0.08:contrast=1.5:saturation=2.0:gamma=1.15,"
    f"colorbalance=rs=0.0:gs=0.12:bs=-0.08:rm=0.0:gm=0.08:bm=0.0,"
    f"trim=duration={dur},setpts=PTS-STARTPTS,"
    f"vignette=PI/3,"
    f"{text_chain}[outv];"
    f"[1:a]aformat=fltp:44100:stereo,volume=1.0[voice];"
    f"[2:a]aformat=fltp:44100:stereo,volume=0.15,atrim=duration={dur}[music];"
    f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[outa]"
)

cmd = [FFMPEG, "-y", "-stream_loop", "-1", "-i", BG, "-i", AUDIO, "-stream_loop", "-1", "-i", MUSIC,
       "-filter_complex", fc, "-map", "[outv]", "-map", "[outa]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
       "-shortest", "-t", str(dur), OUT]

print("Building final video with music...", flush=True)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"DONE: {sz:.1f} MB — {OUT}")
else:
    print(f"FAILED: {r.stderr[-2000:]}")
