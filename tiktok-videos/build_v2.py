"""
Build TikTok videos v2 - with synced subtitle captions
Background sports footage + darkened + text overlays + VO + beat + subtitles
"""
import subprocess
import os

OUTDIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(OUTDIR, "assets")
FONT = "C\\\\:/Windows/Fonts/arialbd.ttf"
FONT_REG = "C\\\\:/Windows/Fonts/arial.ttf"
GREEN = "#00FF87"
GOLD = "#FFD700"
WHITE = "white"
GRAY = "#888888"
W, H = 1080, 1920


def write_srt(lines, outpath):
    """Write SRT subtitle file. lines = [(start_s, end_s, text), ...]"""
    with open(outpath, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(lines, 1):
            def fmt(t):
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int((t % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            f.write(f"{i}\n{fmt(start)} --> {fmt(end)}\n{text}\n\n")
    return outpath


def build_video(bg_video, vo_audio, duration, srt_path, outpath, beat_path):
    """Compose final video with subtitles"""
    
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", bg_video,
        "-i", vo_audio,
        "-i", beat_path,
        "-filter_complex",
        # Video pipeline
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,setsar=1,fps=30,"
        f"eq=brightness=-0.35:contrast=1.2:saturation=0.4,"
        f"trim=duration={duration},setpts=PTS-STARTPTS,"
        # Subtitles - large, bold, centered, with outline
        f"subtitles='{srt_escaped}':force_style='"
        f"FontName=Arial Bold,"
        f"FontSize=28,"
        f"PrimaryColour=&H0087FF00,"  # Green in ASS BGR format
        f"OutlineColour=&H00000000,"
        f"BorderStyle=3,"
        f"Outline=2,"
        f"Shadow=0,"
        f"Alignment=2,"
        f"MarginV=350"
        f"'[outv];"
        # Audio
        f"[1:a]aformat=fltp:44100:stereo,volume=1.2[vo];"
        f"[2:a]aformat=fltp:44100:stereo,volume=0.2,atrim=duration={duration}[beat];"
        f"[vo][beat]amix=inputs=2:duration=first[outa]",
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-t", str(duration),
        outpath
    ]
    print(f"  Building {os.path.basename(outpath)}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  STDERR: {r.stderr[-2000:]}")
        return None
    size_mb = os.path.getsize(outpath) / 1024 / 1024
    print(f"  OK: {size_mb:.1f} MB")
    return outpath


def generate_beat(duration, outpath):
    """Simple background beat"""
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


def video1():
    dur = 15
    bg = os.path.join(ASSETS, "basketball_portrait.mp4")
    vo = os.path.join(ASSETS, "vo_launch.mp3")
    beat = os.path.join(ASSETS, "beat_15.m4a")
    srt = os.path.join(OUTDIR, "sub_launch.srt")
    out = os.path.join(OUTDIR, "01_launch_announcement.mp4")
    
    generate_beat(dur, beat)
    
    # Subtitles synced to VO script
    write_srt([
        (0.3, 2.0, "PARLAY GUARANTEE"),
        (2.0, 4.5, "AI-POWERED SPORTS PICKS"),
        (4.5, 7.0, "74% ACCURACY"),
        (7.0, 9.5, "79 STRAIGHT PROFITABLE NIGHTS"),
        (9.5, 12.0, "YOUR MONEY BACK\\NIF WE'RE WRONG"),
        (12.5, 15.0, "PARLAYGUARANTEE.COM"),
    ], srt)
    
    return build_video(bg, vo, dur, srt, out, beat)


def video2():
    dur = 20
    bg = os.path.join(ASSETS, "basketball_action2.mp4")
    vo = os.path.join(ASSETS, "vo_howitworks.mp3")
    beat = os.path.join(ASSETS, "beat_20.m4a")
    srt = os.path.join(OUTDIR, "sub_howitworks.srt")
    out = os.path.join(OUTDIR, "02_how_it_works.mp4")
    
    generate_beat(dur, beat)
    
    write_srt([
        (0.3, 2.5, "HERE'S HOW IT WORKS"),
        (2.5, 4.5, "STEP ONE"),
        (4.5, 7.0, "PICK YOUR SPORT\\NNBA  NFL  MLB  UFC"),
        (7.0, 9.0, "STEP TWO"),
        (9.0, 12.0, "OUR AI ANALYZES\\N38+ FACTORS"),
        (12.0, 14.0, "INJURIES  MATCHUPS\\NTRENDS  ODDS"),
        (14.0, 16.5, "STEP THREE"),
        (16.5, 18.5, "WIN OR GET\\NYOUR MONEY BACK"),
        (18.5, 20.0, "PARLAYGUARANTEE.COM\\NLINK IN BIO"),
    ], srt)
    
    return build_video(bg, vo, dur, srt, out, beat)


def video3():
    dur = 16
    bg = os.path.join(ASSETS, "basketball_action1.mp4")
    vo = os.path.join(ASSETS, "vo_guarantee.mp3")
    beat = os.path.join(ASSETS, "beat_16.m4a")
    srt = os.path.join(OUTDIR, "sub_guarantee.srt")
    out = os.path.join(OUTDIR, "03_the_guarantee.mp4")
    
    generate_beat(dur, beat)
    
    write_srt([
        (0.3, 2.5, "TIRED OF LOSING YOUR BETS?"),
        (2.5, 5.0, "WE PUT OUR MONEY\\NWHERE OUR MOUTH IS"),
        (5.0, 7.5, "74% ACCURACY"),
        (7.5, 10.0, "IF WE'RE WRONG\\NYOU GET A FULL REFUND"),
        (10.0, 12.5, "NO QUESTIONS ASKED"),
        (12.5, 16.0, "PARLAYGUARANTEE.COM\\NLINK IN BIO"),
    ], srt)
    
    return build_video(bg, vo, dur, srt, out, beat)


if __name__ == "__main__":
    print("Building v2 TikTok videos with synced subtitles...")
    video1()
    video2()
    video3()
    print("\nAll done!")
