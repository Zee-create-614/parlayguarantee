"""
ParlayGuarantee TikTok Video Generator
Creates professional text/motion graphic videos using ffmpeg
9:16 aspect ratio (1080x1920) for TikTok
"""
import subprocess
import os
import json

OUTDIR = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(OUTDIR, "..", "public", "logo-transparent.png")
PCT74 = os.path.join(OUTDIR, "74pct.txt").replace("\\", "/").replace(":", "\\\\:")
W, H = 1080, 1920
BG = "0x0A0A0F"  # near-black (for color source)
GOLD = "#FFD700"   # brand accent-gold
GREEN = "#00FF87"  # brand accent-green
WHITE = "white"
GRAY = "0x888888"
# For drawtext, use string color names or #hex
FONT = "C\\\\:/Windows/Fonts/arialbd.ttf"
FONT_REG = "C\\\\:/Windows/Fonts/arial.ttf"

def make_video1_launch():
    """Video 1: Launch Announcement - 15 seconds"""
    out = os.path.join(OUTDIR, "01_launch_announcement.mp4")
    
    # Build filter complex for animated text overlays
    # Scene 1 (0-3s): Logo fade in
    # Scene 2 (3-6s): "AI-Powered Sports Picks"
    # Scene 3 (6-9s): "74% Accuracy"  
    # Scene 4 (9-12s): "Your Money Back If We're Wrong"
    # Scene 5 (12-15s): "parlayguarantee.com" + CTA
    
    filter_complex = (
        f"color=c={BG}:s={W}x{H}:d=15:r=30,"
        
        # Scene 1: Brand name
        f"drawtext=fontfile={FONT}:text='PARLAY':fontsize=90:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+100:"
        f"enable='between(t,0.5,3)':alpha='if(lt(t,1),(t-0.5)*2,if(gt(t,2.5),(3-t)*2,1))',"
        
        # Brand tagline
        f"drawtext=fontfile={FONT}:text='GUARANTEE':fontsize=90:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+200:"
        f"enable='between(t,0.5,3)':alpha='if(lt(t,1),(t-0.5)*2,if(gt(t,2.5),(3-t)*2,1))',"
        
        # Scene 2: AI Powered
        f"drawtext=fontfile={FONT}:text='AI-POWERED':fontsize=80:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:"
        f"enable='between(t,3,6)':alpha='if(lt(t,3.5),(t-3)*2,if(gt(t,5.5),(6-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='SPORTS PICKS':fontsize=80:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='between(t,3,6)':alpha='if(lt(t,3.5),(t-3)*2,if(gt(t,5.5),(6-t)*2,1))',"
        
        # Scene 3: Stats
        f"drawtext=fontfile={FONT}:expansion=none:text='74%':fontsize=200:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-150:"
        f"enable='between(t,6,9)':alpha='if(lt(t,6.5),(t-6)*2,if(gt(t,8.5),(9-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='ACCURACY RATE':fontsize=70:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+80:"
        f"enable='between(t,6,9)':alpha='if(lt(t,6.5),(t-6)*2,if(gt(t,8.5),(9-t)*2,1))',"
        f"drawtext=fontfile={FONT_REG}:text='79 Consecutive Profitable Nights':fontsize=40:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+180:"
        f"enable='between(t,6.5,9)':alpha='if(lt(t,7),(t-6.5)*2,if(gt(t,8.5),(9-t)*2,1))',"
        
        # Scene 4: Guarantee
        f"drawtext=fontfile={FONT}:text='YOUR MONEY BACK':fontsize=70:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-80:"
        f"enable='between(t,9,12)':alpha='if(lt(t,9.5),(t-9)*2,if(gt(t,11.5),(12-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='IF WE ARE WRONG':fontsize=70:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+40:"
        f"enable='between(t,9,12)':alpha='if(lt(t,9.5),(t-9)*2,if(gt(t,11.5),(12-t)*2,1))',"
        
        # Scene 5: CTA
        f"drawtext=fontfile={FONT}:text='PARLAYGUARANTEE.COM':fontsize=60:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-50:"
        f"enable='between(t,12,15)':alpha='if(lt(t,12.5),(t-12)*2,1)',"
        f"drawtext=fontfile={FONT_REG}:text='Link in bio':fontsize=45:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+50:"
        f"enable='between(t,12.5,15)':alpha='if(lt(t,13),(t-12.5)*2,1)'"
        f"[outv]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:d=15:r=30",
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-t", "15",
        out
    ]
    print("Creating Video 1: Launch Announcement...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr[-2000:]}")
        raise Exception(f"ffmpeg failed with code {r.returncode}")
    print(f"✅ Video 1 saved: {out}")
    return out


def make_video2_how_it_works():
    """Video 2: How It Works - 20 seconds"""
    out = os.path.join(OUTDIR, "02_how_it_works.mp4")
    
    filter_complex = (
        f"color=c={BG}:s={W}x{H}:d=20:r=30,"
        
        # Title
        f"drawtext=fontfile={FONT}:text='HOW IT WORKS':fontsize=80:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=300:"
        f"enable='between(t,0,3)':alpha='if(lt(t,0.5),t*2,if(gt(t,2.5),(3-t)*2,1))',"
        
        # Step 1
        f"drawtext=fontfile={FONT}:text='1':fontsize=150:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=500:"
        f"enable='between(t,3,7)':alpha='if(lt(t,3.5),(t-3)*2,if(gt(t,6.5),(7-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='PICK YOUR SPORT':fontsize=60:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=700:"
        f"enable='between(t,3.3,7)':alpha='if(lt(t,3.8),(t-3.3)*2,if(gt(t,6.5),(7-t)*2,1))',"
        f"drawtext=fontfile={FONT_REG}:text='NBA · NFL · MLB · NHL · UFC · Soccer':fontsize=35:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=790:"
        f"enable='between(t,3.6,7)':alpha='if(lt(t,4.1),(t-3.6)*2,if(gt(t,6.5),(7-t)*2,1))',"
        
        # Step 2
        f"drawtext=fontfile={FONT}:text='2':fontsize=150:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=500:"
        f"enable='between(t,7,11)':alpha='if(lt(t,7.5),(t-7)*2,if(gt(t,10.5),(11-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='AI ANALYZES 38+ FACTORS':fontsize=55:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=700:"
        f"enable='between(t,7.3,11)':alpha='if(lt(t,7.8),(t-7.3)*2,if(gt(t,10.5),(11-t)*2,1))',"
        f"drawtext=fontfile={FONT_REG}:text='Injuries · Matchups · Trends · Odds':fontsize=35:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=790:"
        f"enable='between(t,7.6,11)':alpha='if(lt(t,8.1),(t-7.6)*2,if(gt(t,10.5),(11-t)*2,1))',"
        
        # Step 3
        f"drawtext=fontfile={FONT}:text='3':fontsize=150:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=500:"
        f"enable='between(t,11,15)':alpha='if(lt(t,11.5),(t-11)*2,if(gt(t,14.5),(15-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='WIN OR GET A REFUND':fontsize=60:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=700:"
        f"enable='between(t,11.3,15)':alpha='if(lt(t,11.8),(t-11.3)*2,if(gt(t,14.5),(15-t)*2,1))',"
        f"drawtext=fontfile={FONT_REG}:expansion=none:text='100% deposit keep rate · 79 nights':fontsize=35:fontcolor={GRAY}:"
        f"x=(w-text_w)/2:y=790:"
        f"enable='between(t,11.6,15)':alpha='if(lt(t,12.1),(t-11.6)*2,if(gt(t,14.5),(15-t)*2,1))',"
        
        # CTA
        f"drawtext=fontfile={FONT}:text='PARLAYGUARANTEE.COM':fontsize=60:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,15.5,20)':alpha='if(lt(t,16),(t-15.5)*2,1)',"
        f"drawtext=fontfile={FONT_REG}:text='First pick pack FREE with signup':fontsize=40:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+100:"
        f"enable='between(t,16,20)':alpha='if(lt(t,16.5),(t-16)*2,1)'"
        f"[outv]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:d=20:r=30",
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-t", "20",
        out
    ]
    print("Creating Video 2: How It Works...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr[-2000:]}")
        raise Exception(f"ffmpeg failed with code {r.returncode}")
    print(f"✅ Video 2 saved: {out}")
    return out


def make_video3_guarantee():
    """Video 3: The Guarantee - 12 seconds, punchy"""
    out = os.path.join(OUTDIR, "03_the_guarantee.mp4")
    
    filter_complex = (
        f"color=c={BG}:s={W}x{H}:d=12:r=30,"
        
        # Hook
        f"drawtext=fontfile={FONT}:text='TIRED OF LOSING':fontsize=75:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-100:"
        f"enable='between(t,0,3)':alpha='if(lt(t,0.3),t*3.3,if(gt(t,2.5),(3-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='YOUR BETS?':fontsize=75:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20:"
        f"enable='between(t,0.3,3)':alpha='if(lt(t,0.6),(t-0.3)*3.3,if(gt(t,2.5),(3-t)*2,1))',"
        
        # The pitch
        f"drawtext=fontfile={FONT}:text='WE PUT OUR':fontsize=65:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-120:"
        f"enable='between(t,3.5,7)':alpha='if(lt(t,4),(t-3.5)*2,if(gt(t,6.5),(7-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='MONEY':fontsize=120:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,3.8,7)':alpha='if(lt(t,4.3),(t-3.8)*2,if(gt(t,6.5),(7-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='WHERE OUR MOUTH IS':fontsize=55:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+150:"
        f"enable='between(t,4.1,7)':alpha='if(lt(t,4.6),(t-4.1)*2,if(gt(t,6.5),(7-t)*2,1))',"
        
        # Stats flash
        f"drawtext=fontfile={FONT}:expansion=none:text='74% ACCURACY':fontsize=80:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-80:"
        f"enable='between(t,7.5,9.5)':alpha='if(lt(t,8),(t-7.5)*2,if(gt(t,9),(9.5-t)*2,1))',"
        f"drawtext=fontfile={FONT}:text='REFUND IF WRONG':fontsize=70:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+50:"
        f"enable='between(t,7.8,9.5)':alpha='if(lt(t,8.3),(t-7.8)*2,if(gt(t,9),(9.5-t)*2,1))',"
        
        # CTA
        f"drawtext=fontfile={FONT}:text='PARLAYGUARANTEE.COM':fontsize=65:fontcolor={GREEN}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-30:"
        f"enable='between(t,10,12)':alpha='if(lt(t,10.5),(t-10)*2,1)',"
        f"drawtext=fontfile={FONT_REG}:text='Link in bio ↓':fontsize=50:fontcolor={WHITE}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+70:"
        f"enable='between(t,10.3,12)':alpha='if(lt(t,10.8),(t-10.3)*2,1)'"
        f"[outv]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:d=12:r=30",
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-t", "12",
        out
    ]
    print("Creating Video 3: The Guarantee...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"STDERR: {r.stderr[-2000:]}")
        raise Exception(f"ffmpeg failed with code {r.returncode}")
    print(f"✅ Video 3 saved: {out}")
    return out


if __name__ == "__main__":
    v1 = make_video1_launch()
    v2 = make_video2_how_it_works()
    v3 = make_video3_guarantee()
    print(f"\n🎬 All 3 videos created in: {OUTDIR}")
    for v in [v1, v2, v3]:
        size_mb = os.path.getsize(v) / 1024 / 1024
        print(f"  {os.path.basename(v)} ({size_mb:.1f} MB)")

