"""
Build TikTok videos v3 - drawtext-based captions synced to VO
"""
import subprocess
import os

OUTDIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(OUTDIR, "assets")
FONT = "C\\\\:/Windows/Fonts/arialbd.ttf"
GREEN = "#00FF87"
GOLD = "#FFD700"
WHITE = "white"
GRAY = "#aaaaaa"


def caption_filter(lines, y_pos="h-250"):
    """Generate drawtext chain for timed captions.
    lines = [(start, end, text, color), ...]
    """
    parts = []
    for start, end, text, color in lines:
        text = text.replace("'", "")
        parts.append(
            f"drawtext=fontfile={FONT}:expansion=none:text='{text}':"
            f"fontsize=52:fontcolor={color}:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y={y_pos}:"
            f"enable='between(t\\,{start}\\,{end})'"
        )
    return ",".join(parts)


def generate_beat(duration, outpath):
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=55:duration={duration}:sample_rate=44100",
        "-f", "lavfi", "-i", f"anoisesrc=d={duration}:c=pink:r=44100:a=0.02",
        "-filter_complex",
        f"[0:a]aformat=fltp:44100:stereo,volume=0.12,lowpass=f=100[bass];"
        f"[1:a]aformat=fltp:44100:stereo,highpass=f=8000,volume=0.06[hh];"
        f"[bass][hh]amix=inputs=2:duration=longest,volume=0.4[out]",
        "-map", "[out]", "-c:a", "aac", "-b:a", "128k", "-t", str(duration), outpath
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def build_video(bg_video, vo_audio, duration, caption_text, outpath, beat_path):
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", bg_video,
        "-i", vo_audio,
        "-i", beat_path,
        "-filter_complex",
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,setsar=1,fps=30,"
        f"eq=brightness=-0.35:contrast=1.2:saturation=0.4,"
        f"trim=duration={duration},setpts=PTS-STARTPTS,"
        f"{caption_text}[outv];"
        f"[1:a]aformat=fltp:44100:stereo,volume=1.2[vo];"
        f"[2:a]aformat=fltp:44100:stereo,volume=0.2,atrim=duration={duration}[beat];"
        f"[vo][beat]amix=inputs=2:duration=first[outa]",
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-t", str(duration), outpath
    ]
    print(f"  Building {os.path.basename(outpath)}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  STDERR: {r.stderr[-2000:]}")
        return None
    size_mb = os.path.getsize(outpath) / 1024 / 1024
    print(f"  OK: {size_mb:.1f} MB")
    return outpath


def video1():
    dur = 15
    bg = os.path.join(ASSETS, "basketball_portrait.mp4")
    vo = os.path.join(ASSETS, "vo_launch.mp3")
    beat = os.path.join(ASSETS, "beat_15.m4a")
    out = os.path.join(OUTDIR, "01_launch_announcement.mp4")
    generate_beat(dur, beat)
    
    captions = caption_filter([
        (0.2, 2.2,  "PARLAY GUARANTEE",               GREEN),
        (2.2, 4.8,  "AI-Powered Sports Picks",         WHITE),
        (4.8, 7.2,  "74% Accuracy",                    GREEN),
        (7.2, 10.0, "79 Straight Profitable Nights",   GOLD),
        (10.0, 12.5,"Your Money Back If We're Wrong",   WHITE),
        (12.5, 15.0,"ParlayGuarantee.com",              GOLD),
    ])
    return build_video(bg, vo, dur, captions, out, beat)


def video2():
    dur = 22
    bg = os.path.join(ASSETS, "basketball_action2.mp4")
    vo = os.path.join(ASSETS, "vo_howitworks.mp3")
    beat = os.path.join(ASSETS, "beat_22.m4a")
    out = os.path.join(OUTDIR, "02_how_it_works.mp4")
    generate_beat(dur, beat)
    
    captions = caption_filter([
        (0.2, 3.0,  "Heres How It Works",               GREEN),
        (3.0, 6.5,  "Pick Your Sport",                   WHITE),
        (6.5, 10.5, "AI Analyzes 38 Factors",            WHITE),
        (10.5, 15.0,"Win or Get Your Money Back",        GREEN),
        (15.5, 22.0,"ParlayGuarantee.com",               GOLD),
    ])
    return build_video(bg, vo, dur, captions, out, beat)


def video3():
    dur = 16
    bg = os.path.join(ASSETS, "basketball_action1.mp4")
    vo = os.path.join(ASSETS, "vo_guarantee.mp3")
    beat = os.path.join(ASSETS, "beat_16.m4a")
    out = os.path.join(OUTDIR, "03_the_guarantee.mp4")
    generate_beat(dur, beat)
    
    captions = caption_filter([
        (0.2, 2.5,  "Tired of Losing Your Bets?",       WHITE),
        (2.5, 5.2,  "We Put Our Money Where Our Mouth Is", GREEN),
        (5.2, 7.8,  "74% Accuracy",                      GREEN),
        (7.8, 10.5, "If We're Wrong You Get a Full Refund", WHITE),
        (10.5, 12.5,"No Questions Asked",                 GOLD),
        (12.5, 16.0,"ParlayGuarantee.com - Link in Bio",  GOLD),
    ])
    return build_video(bg, vo, dur, captions, out, beat)


if __name__ == "__main__":
    print("Building v3 TikTok videos with synced captions...")
    video1()
    video2()
    video3()
    print("\nAll done!")
