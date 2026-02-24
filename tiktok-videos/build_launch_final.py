"""Rebuild launch video - Adam voice, NBA background, original script"""
import subprocess, os

FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
BG = r"C:\Users\joshs\Downloads\Anthony_Edwards_NBA_Dunking__Kling_25_Turbo_Pro_66818.mp4"
VO = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\vo_launch_real.mp3"
BEAT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\beat_sports.mp3"
OUT = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\pg_launch_FINAL.mp4"
FONT = "C\\\\:/Windows/Fonts/impact.ttf"
FONTB = "C\\\\:/Windows/Fonts/arialbd.ttf"

dur = 15

def dt(text, color, s, e, y, sz=56, font=None, glow=True):
    if font is None:
        font = FONTB
    text = text.replace("'", "").replace(":", "\\:")
    parts = []
    if glow:
        parts.append(
            f"drawtext=fontfile={font}:expansion=none:text='{text}':"
            f"fontsize={sz+4}:fontcolor={color}@0.35:borderw=8:bordercolor={color}@0.2:"
            f"x=(w-text_w)/2:y={y}:"
            f"enable='between(t\\,{s}\\,{e})'"
        )
    parts.append(
        f"drawtext=fontfile={font}:expansion=none:text='{text}':"
        f"fontsize={sz}:fontcolor={color}:borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y={y}:"
        f"enable='between(t\\,{s}\\,{e})'"
    )
    return parts

texts = []
texts += dt("WHAT IF I TOLD YOU...", "white", 0.2, 3.0, "h/2-200", 60, FONT)
texts += dt("AN AI WAS", "#00FF87", 3.0, 5.5, "h/2-280", 85, FONT)
texts += dt("BEATING VEGAS?", "#00FF87", 3.0, 5.5, "h/2-170", 85, FONT)
texts += dt("74% ACCURACY", "#00FF87", 5.5, 7.5, "h/2-250", 90, FONT)
texts += dt("79 NIGHTS", "#FFD700", 7.5, 9.5, "h/2-280", 85, FONT)
texts += dt("OF PROFIT", "#FFD700", 7.5, 9.5, "h/2-170", 85, FONT)
texts += dt("ZERO LOSSES", "#FF4444", 9.5, 11.0, "h/2-250", 90, FONT)
texts += dt("YOUR MONEY BACK", "white", 11.0, 12.8, "h/2-280", 70, FONT)
texts += dt("IF WERE WRONG", "white", 11.0, 12.8, "h/2-170", 70, FONT)
texts += dt("PARLAY GUARANTEE", "#FFD700", 12.8, 15.0, "h/2-250", 80, FONT)
texts += dt("ParlayGuarantee.com", "#FFD700", 12.8, 15.0, "h-280", 52)

text_chain = ",".join(texts)

fc = (
    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
    f"crop=1080:1920,setsar=1,fps=30,"
    f"eq=brightness=-0.08:contrast=1.5:saturation=2.0:gamma=1.15,"
    f"colorbalance=rs=0.0:gs=0.12:bs=-0.08:rm=0.0:gm=0.08:bm=0.0,"
    f"trim=duration={dur},setpts=PTS-STARTPTS,"
    f"vignette=PI/3,"
    f"{text_chain}[outv];"
    f"[1:a]aformat=fltp:44100:stereo,volume=1.3[vo];"
    f"[2:a]aformat=fltp:44100:stereo,volume=0.35,afade=t=in:st=0:d=0.5,atrim=duration={dur}[beat];"
    f"[vo][beat]amix=inputs=2:duration=first:normalize=0[outa]"
)

cmd = [FFMPEG, "-y", "-stream_loop", "-1", "-i", BG, "-i", VO, "-i", BEAT,
       "-filter_complex", fc, "-map", "[outv]", "-map", "[outa]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
       "-shortest", "-t", str(dur), OUT]

print("Building launch video...", flush=True)
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    sz = os.path.getsize(OUT) / 1024 / 1024
    print(f"DONE: {sz:.1f} MB — {OUT}")
else:
    print(f"FAILED: {r.stderr[-2000:]}")
