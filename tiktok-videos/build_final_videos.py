"""
Build final TikTok videos with:
- Background sports footage (darkened)
- Text overlays (green/gold brand colors)
- Voiceover
- Generated beat
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

def generate_beat(duration, outpath):
    """Generate a simple dark trap-style beat using ffmpeg"""
    # Low bass + hi-hat pattern
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"sine=frequency=55:duration={duration}:sample_rate=44100",
        "-f", "lavfi", "-i",
        f"anoisesrc=d={duration}:c=pink:r=44100:a=0.02",
        "-filter_complex",
        f"[0:a]aformat=fltp:44100:stereo,volume=0.15,lowpass=f=120[bass];"
        f"[1:a]aformat=fltp:44100:stereo,highpass=f=8000,volume=0.08,"
        f"agate=threshold=0.01:attack=5:release=50[hh];"
        f"[bass][hh]amix=inputs=2:duration=longest,volume=0.5[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(duration),
        outpath
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return outpath


def build_video(bg_video, vo_audio, duration, text_filter, outpath, beat_path):
    """Compose final video: bg footage + dark overlay + text + VO + beat"""
    
    # Scale background to 1080x1920, crop center, darken
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", bg_video,     # 0: background (loop)
        "-i", vo_audio,                              # 1: voiceover
        "-i", beat_path,                             # 2: beat
        "-filter_complex",
        # Video: scale to fill 9:16, crop center, darken with overlay
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,setsar=1,fps=30,"
        f"colorbalance=bs=-0.3:bm=-0.3:bh=-0.2,"
        f"eq=brightness=-0.3:contrast=1.2:saturation=0.5,"
        f"trim=duration={duration},setpts=PTS-STARTPTS,"
        # Text overlays
        f"{text_filter}[outv];"
        # Audio: mix VO + beat
        f"[1:a]aformat=fltp:44100:stereo,volume=1.0[vo];"
        f"[2:a]aformat=fltp:44100:stereo,volume=0.3,atrim=duration={duration}[beat];"
        f"[vo][beat]amix=inputs=2:duration=first[outa]",
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-t", str(duration),
        outpath
    ]
    print(f"  Building {os.path.basename(outpath)}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  STDERR: {r.stderr[-1500:]}")
        return None
    size_mb = os.path.getsize(outpath) / 1024 / 1024
    print(f"  OK: {size_mb:.1f} MB")
    return outpath


def video1_launch():
    """Launch announcement - ~15s"""
    dur = 15
    bg = os.path.join(ASSETS, "basketball_portrait.mp4")
    vo = os.path.join(ASSETS, "vo_launch.mp3")
    beat = os.path.join(ASSETS, "beat_15.m4a")
    out = os.path.join(OUTDIR, "01_launch_announcement.mp4")
    
    generate_beat(dur, beat)
    
    text = (
        # PARLAY GUARANTEE
        f"drawtext=fontfile={FONT}:text='PARLAY':fontsize=90:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+50:"
        f"enable='between(t,0.5,3.5)':alpha='if(lt(t,1),(t-0.5)*2,if(gt(t,3),(3.5-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='GUARANTEE':fontsize=90:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+160:"
        f"enable='between(t,0.5,3.5)':alpha='if(lt(t,1),(t-0.5)*2,if(gt(t,3),(3.5-t)*2,1))',"
        
        # AI-POWERED SPORTS PICKS
        f"drawtext=fontfile={FONT}:text='AI-POWERED':fontsize=80:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-50:"
        f"enable='between(t,3.5,6.5)':alpha='if(lt(t,4),(t-3.5)*2,if(gt(t,6),(6.5-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='SPORTS PICKS':fontsize=80:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+60:"
        f"enable='between(t,3.5,6.5)':alpha='if(lt(t,4),(t-3.5)*2,if(gt(t,6),(6.5-t)*2,1))',"
        
        # 74% ACCURACY
        f"drawtext=fontfile={FONT}:expansion=none:text='74%':fontsize=200:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-150:"
        f"enable='between(t,6.5,10)':alpha='if(lt(t,7),(t-6.5)*2,if(gt(t,9.5),(10-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='ACCURACY':fontsize=70:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+60:"
        f"enable='between(t,6.5,10)':alpha='if(lt(t,7),(t-6.5)*2,if(gt(t,9.5),(10-t)*2,1))',"
        
        # YOUR MONEY BACK
        f"drawtext=fontfile={FONT}:text='YOUR MONEY BACK':fontsize=65:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-60:"
        f"enable='between(t,10,12.5)':alpha='if(lt(t,10.5),(t-10)*2,if(gt(t,12),(12.5-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='IF WERE WRONG':fontsize=65:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+60:"
        f"enable='between(t,10,12.5)':alpha='if(lt(t,10.5),(t-10)*2,if(gt(t,12),(12.5-t)*2,1))',"
        
        # CTA
        f"drawtext=fontfile={FONT}:text='PARLAYGUARANTEE.COM':fontsize=55:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-30:"
        f"enable='between(t,12.5,15)':alpha='if(lt(t,13),(t-12.5)*2,1)',"
        f"drawtext=fontfile={FONT_REG}:text='Link in bio':fontsize=40:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+40:"
        f"enable='between(t,13,15)':alpha='if(lt(t,13.5),(t-13)*2,1)'"
    )
    
    return build_video(bg, vo, dur, text, out, beat)


def video2_howitworks():
    """How It Works - ~20s (trimmed from 30s VO)"""
    dur = 20
    bg = os.path.join(ASSETS, "basketball_action2.mp4")
    vo = os.path.join(ASSETS, "vo_howitworks.mp3")
    beat = os.path.join(ASSETS, "beat_20.m4a")
    out = os.path.join(OUTDIR, "02_how_it_works.mp4")
    
    generate_beat(dur, beat)
    
    text = (
        # HOW IT WORKS
        f"drawtext=fontfile={FONT}:text='HOW IT WORKS':fontsize=80:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,0,3)':alpha='if(lt(t,0.5),t*2,if(gt(t,2.5),(3-t)*2,1))',"
        
        # Step 1
        f"drawtext=fontfile={FONT}:text='1':fontsize=150:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-150:"
        f"enable='between(t,3,7)':alpha='if(lt(t,3.5),(t-3)*2,if(gt(t,6.5),(7-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='PICK YOUR SPORT':fontsize=60:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='between(t,3.3,7)':alpha='if(lt(t,3.8),(t-3.3)*2,if(gt(t,6.5),(7-t)*2,1))',"
        
        # Step 2
        f"drawtext=fontfile={FONT}:text='2':fontsize=150:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-150:"
        f"enable='between(t,7,11)':alpha='if(lt(t,7.5),(t-7)*2,if(gt(t,10.5),(11-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='AI ANALYZES 38+ FACTORS':fontsize=50:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='between(t,7.3,11)':alpha='if(lt(t,7.8),(t-7.3)*2,if(gt(t,10.5),(11-t)*2,1))',"
        
        # Step 3
        f"drawtext=fontfile={FONT}:text='3':fontsize=150:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-150:"
        f"enable='between(t,11,15)':alpha='if(lt(t,11.5),(t-11)*2,if(gt(t,14.5),(15-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='WIN OR GET A REFUND':fontsize=55:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='between(t,11.3,15)':alpha='if(lt(t,11.8),(t-11.3)*2,if(gt(t,14.5),(15-t)*2,1))',"
        
        # CTA
        f"drawtext=fontfile={FONT}:text='PARLAYGUARANTEE.COM':fontsize=55:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-30:"
        f"enable='between(t,16,20)':alpha='if(lt(t,16.5),(t-16)*2,1)',"
        f"drawtext=fontfile={FONT_REG}:text='Link in bio':fontsize=40:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+40:"
        f"enable='between(t,16.5,20)':alpha='if(lt(t,17),(t-16.5)*2,1)'"
    )
    
    return build_video(bg, vo, dur, text, out, beat)


def video3_guarantee():
    """The Guarantee - ~16s"""
    dur = 16
    bg = os.path.join(ASSETS, "basketball_action1.mp4")
    vo = os.path.join(ASSETS, "vo_guarantee.mp3")
    beat = os.path.join(ASSETS, "beat_16.m4a")
    out = os.path.join(OUTDIR, "03_the_guarantee.mp4")
    
    generate_beat(dur, beat)
    
    text = (
        # HOOK
        f"drawtext=fontfile={FONT}:text='TIRED OF LOSING':fontsize=70:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-60:"
        f"enable='between(t,0,3.5)':alpha='if(lt(t,0.3),t*3,if(gt(t,3),(3.5-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='YOUR BETS?':fontsize=70:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+50:"
        f"enable='between(t,0.3,3.5)':alpha='if(lt(t,0.6),(t-0.3)*3,if(gt(t,3),(3.5-t)*2,1))',"
        
        # PITCH
        f"drawtext=fontfile={FONT}:text='WE PUT OUR MONEY':fontsize=60:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-80:"
        f"enable='between(t,3.5,7)':alpha='if(lt(t,4),(t-3.5)*2,if(gt(t,6.5),(7-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='WHERE OUR MOUTH IS':fontsize=55:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+40:"
        f"enable='between(t,3.8,7)':alpha='if(lt(t,4.3),(t-3.8)*2,if(gt(t,6.5),(7-t)*2,1))',"
        
        # STATS
        f"drawtext=fontfile={FONT}:expansion=none:text='74% ACCURACY':fontsize=80:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-60:"
        f"enable='between(t,7.5,10.5)':alpha='if(lt(t,8),(t-7.5)*2,if(gt(t,10),(10.5-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='REFUND IF WRONG':fontsize=65:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+50:"
        f"enable='between(t,7.8,10.5)':alpha='if(lt(t,8.3),(t-7.8)*2,if(gt(t,10),(10.5-t)*2,1))',"
        
        # CTA
        f"drawtext=fontfile={FONT}:text='PARLAYGUARANTEE.COM':fontsize=55:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-30:"
        f"enable='between(t,11,16)':alpha='if(lt(t,11.5),(t-11)*2,1)',"
        f"drawtext=fontfile={FONT_REG}:text='Link in bio':fontsize=40:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+40:"
        f"enable='between(t,11.5,16)':alpha='if(lt(t,12),(t-11.5)*2,1)'"
    )
    
    return build_video(bg, vo, dur, text, out, beat)


if __name__ == "__main__":
    print("Building final TikTok videos with footage + VO + beat...")
    v1 = video1_launch()
    v2 = video2_howitworks()
    v3 = video3_guarantee()
    print(f"\nAll done!")
