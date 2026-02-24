"""Rebuild launch video - original audio, Edwards dunk BG, Impact bold green+white text"""
import subprocess, os

FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
BG = r"C:\Users\joshs\Downloads\Anthony_Edwards_NBA_Dunking__Kling_25_Turbo_Pro_66818.mp4"
AUDIO = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\vo_original_extract.wav"
OUT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\pg_launch_FINAL2.mp4"
FONT = "C\\\\:/Windows/Fonts/impact.ttf"

dur = 14.2  # match original audio length
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

# Text matching the script: "What if I told you... an AI was beating Vegas?
# 74 percent accuracy. 79 nights of profit. Zero losses.
# Your money back if we're wrong. This is Parlay Guarantee."
texts = []
texts += dt("WHAT IF I TOLD YOU...", WHITE, 0.2, 3.0, "h/2-200", 60)
texts += dt("AN AI WAS", GREEN, 3.0, 5.5, "h/2-280", 85)
texts += dt("BEATING VEGAS?", GREEN, 3.0, 5.5, "h/2-170", 85)
texts += dt("74% ACCURACY", GREEN, 5.5, 7.5, "h/2-250", 90)
texts += dt("79 NIGHTS", GREEN, 7.5, 9.5, "h/2-280", 85)
texts += dt("OF PROFIT", GREEN, 7.5, 9.5, "h/2-170", 85)
texts += dt("ZERO LOSSES", WHITE, 9.5, 11.0, "h/2-250", 90)
texts += dt("YOUR MONEY BACK", WHITE, 11.0, 12.8, "h/2-280", 70)
texts += dt("IF WERE WRONG", WHITE, 11.0, 12.8, "h/2-170", 70)
texts += dt("PARLAY GUARANTEE", GREEN, 12.8, 14.2, "h/2-280", 80)
texts += dt("ParlayGuarantee.com", WHITE, 12.8, 14.2, "h-280", 52)

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

cmd = [FFMPEG, "-y", "-stream_loop", "-1", "-i", BG, "-i", AUDIO,
       "-filter_complex", fc, "-map", "[outv]", "-map", "[outa]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
       "-shortest", "-t", str(dur), OUT]

print("Building launch video v3 (original audio, green+white Impact)...", flush=True)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"DONE: {sz:.1f} MB — {OUT}")
else:
    print(f"FAILED: {r.stderr[-2000:]}")
