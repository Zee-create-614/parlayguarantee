"""
Build TikTok videos v4 - COLORFUL, eye-catching
- Vibrant saturated backgrounds with green/gold color grading
- Big bold title text + synced caption subtitles  
- Real beat track (loud enough to hear)
- Glow effect on text
"""
import subprocess
import os
import sys

OUTDIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(OUTDIR, "assets")
FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FONT = "C\\\\:/Windows/Fonts/arialbd.ttf"
FONT_IMPACT = "C\\\\:/Windows/Fonts/impact.ttf"
GREEN = "#00FF87"
GOLD = "#FFD700"
WHITE = "white"
RED = "#FF4444"
CYAN = "#00FFFF"
BEAT = os.path.join(ASSETS, "beat_sports.mp3")


def drawtext(text, color, start, end, y, size=56, font=None, glow=True):
    """Single drawtext entry, optionally with glow layer"""
    if font is None:
        font = FONT
    text = text.replace("'", "")
    parts = []
    if glow:
        parts.append(
            f"drawtext=fontfile={font}:expansion=none:text='{text}':"
            f"fontsize={size+4}:fontcolor={color}@0.35:borderw=8:bordercolor={color}@0.2:"
            f"x=(w-text_w)/2:y={y}:"
            f"enable='between(t\\,{start}\\,{end})'"
        )
    parts.append(
        f"drawtext=fontfile={font}:expansion=none:text='{text}':"
        f"fontsize={size}:fontcolor={color}:borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y={y}:"
        f"enable='between(t\\,{start}\\,{end})'"
    )
    return parts


def build_video(bg_video, vo_audio, duration, text_parts, outpath):
    """Build a single video with vibrant colors + text overlays + beat"""
    text_chain = ",".join(text_parts)
    
    filter_complex = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,setsar=1,fps=30,"
        f"eq=brightness=-0.08:contrast=1.5:saturation=2.0:gamma=1.15,"
        f"colorbalance=rs=0.0:gs=0.12:bs=-0.08:rm=0.0:gm=0.08:bm=0.0,"
        f"trim=duration={duration},setpts=PTS-STARTPTS,"
        f"vignette=PI/3,"
        f"{text_chain}[outv];"
        f"[1:a]aformat=fltp:44100:stereo,volume=1.3[vo];"
        f"[2:a]aformat=fltp:44100:stereo,volume=0.35,afade=t=in:st=0:d=0.5,atrim=duration={duration}[beat];"
        f"[vo][beat]amix=inputs=2:duration=first:normalize=0[outa]"
    )
    
    cmd = [
        FFMPEG, "-y",
        "-stream_loop", "-1", "-i", bg_video,
        "-i", vo_audio,
        "-i", BEAT,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-t", str(duration), outpath
    ]
    
    print(f"  Building {os.path.basename(outpath)}...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  FAILED! stderr:", flush=True)
        print(r.stderr[-2000:], flush=True)
        return None
    size_mb = os.path.getsize(outpath) / 1024 / 1024
    print(f"  OK: {size_mb:.1f} MB", flush=True)
    return outpath


def video1():
    """Launch Announcement - 15s"""
    dur = 15
    bg = os.path.join(ASSETS, "basketball_portrait.mp4")
    vo = os.path.join(ASSETS, "vo_launch.mp3")
    out = os.path.join(OUTDIR, "01_launch_announcement.mp4")

    texts = []
    # Big titles (center)
    texts += drawtext("PARLAY", GREEN, 0.2, 2.2, "h/2-300", 95, FONT_IMPACT)
    texts += drawtext("GUARANTEE", GOLD, 0.2, 2.2, "h/2-190", 90, FONT_IMPACT)
    texts += drawtext("74% ACCURACY", GREEN, 4.8, 7.2, "h/2-250", 88, FONT_IMPACT)
    texts += drawtext("79 NIGHTS", GOLD, 7.2, 10.0, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("PROFITABLE", GOLD, 7.2, 10.0, "h/2-170", 85, FONT_IMPACT)
    # Caption subtitles (bottom)
    texts += drawtext("IS NOW LIVE", WHITE, 0.2, 2.2, "h-280", 52)
    texts += drawtext("AI-Powered Sports Picks", WHITE, 2.2, 4.8, "h-280", 52)
    texts += drawtext("Exposed by AI", CYAN, 4.8, 7.2, "h-280", 52)
    texts += drawtext("Exposed Straight", CYAN, 7.2, 10.0, "h-280", 52)
    texts += drawtext("Your Money Back If Were Wrong", WHITE, 10.0, 12.5, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GOLD, 12.5, 15.0, "h-280", 52)

    return build_video(bg, vo, dur, texts, out)


def video2():
    """How It Works - 22s"""
    dur = 22
    bg = os.path.join(ASSETS, "basketball_action2.mp4")
    vo = os.path.join(ASSETS, "vo_howitworks.mp3")
    out = os.path.join(OUTDIR, "02_how_it_works.mp4")

    texts = []
    texts += drawtext("HOW IT WORKS", GREEN, 0.2, 3.0, "h/2-250", 85, FONT_IMPACT)
    texts += drawtext("38 FACTORS", GOLD, 6.5, 10.5, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("WIN OR", GREEN, 10.5, 15.0, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("MONEY BACK", GREEN, 10.5, 15.0, "h/2-170", 85, FONT_IMPACT)
    # Captions
    texts += drawtext("Three Simple Steps", WHITE, 0.2, 3.0, "h-280", 52)
    texts += drawtext("Pick Your Sport", WHITE, 3.0, 6.5, "h-280", 52)
    texts += drawtext("AI Analyzes Everything", CYAN, 6.5, 10.5, "h-280", 52)
    texts += drawtext("Guaranteed Results", WHITE, 10.5, 15.0, "h-280", 52)
    texts += drawtext("ParlayGuarantee.com", GOLD, 15.5, 22.0, "h-280", 52)

    return build_video(bg, vo, dur, texts, out)


def video3():
    """The Guarantee - 16s"""
    dur = 16
    bg = os.path.join(ASSETS, "basketball_action1.mp4")
    vo = os.path.join(ASSETS, "vo_guarantee.mp3")
    out = os.path.join(OUTDIR, "03_the_guarantee.mp4")

    texts = []
    texts += drawtext("TIRED OF LOSING?", RED, 0.2, 2.5, "h/2-250", 80, FONT_IMPACT)
    texts += drawtext("74% ACCURACY", GREEN, 5.2, 7.8, "h/2-250", 95, FONT_IMPACT)
    texts += drawtext("FULL REFUND", GOLD, 7.8, 10.5, "h/2-250", 85, FONT_IMPACT)
    texts += drawtext("NO QUESTIONS ASKED", GOLD, 10.5, 12.5, "h/2-250", 70, FONT_IMPACT)
    # Captions (no glow to reduce filter count)
    texts += drawtext("Stop Throwing Money Away", WHITE, 0.2, 2.5, "h-280", 52, glow=False)
    texts += drawtext("We Back Every Pick", WHITE, 2.5, 5.2, "h-280", 52, glow=False)
    texts += drawtext("Exposed by AI", CYAN, 5.2, 7.8, "h-280", 52, glow=False)
    texts += drawtext("If Were Wrong You Get Paid", WHITE, 7.8, 10.5, "h-280", 48, glow=False)
    texts += drawtext("Period.", WHITE, 10.5, 12.5, "h-280", 52, glow=False)
    texts += drawtext("ParlayGuarantee.com", GOLD, 12.5, 16.0, "h-280", 52, glow=False)

    return build_video(bg, vo, dur, texts, out)


if __name__ == "__main__":
    print("Building v4 TikTok videos - COLORFUL edition...", flush=True)
    video1()
    video2()
    video3()
    print("\nCopying to Desktop...", flush=True)
    
    import shutil
    desktop = r"C:\Users\joshs\OneDrive\Desktop"
    for f in ["01_launch_announcement.mp4", "02_how_it_works.mp4", "03_the_guarantee.mp4"]:
        src = os.path.join(OUTDIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(desktop, f))
            print(f"  Copied {f}", flush=True)
    print("All done!", flush=True)
