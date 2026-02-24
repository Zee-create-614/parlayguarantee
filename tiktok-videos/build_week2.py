"""
Build ParlayGuarantee WEEK 2 TikTok videos - 7 trendy, action-packed videos
Uses the "all-rounder" voice style and unique backgrounds per video
"""
import subprocess
import os
import sys
import requests

OUTDIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(OUTDIR, "assets")
DOWNLOADS = r"C:\Users\joshs\Downloads"
FFMPEG = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
FONT = "C\\\\:/Windows/Fonts/arialbd.ttf"
FONT_IMPACT = "C\\\\:/Windows/Fonts/impact.ttf"
GREEN = "#00FF87"
WHITE = "white"
BEAT = os.path.join(ASSETS, "beat_sports.mp3")

# ElevenLabs TTS - Testing different voices to find "all-rounder"
ELEVEN_API_KEY = "sk_3bd03ab4e8df0cb2609ff7d1c58b7167a108d24566c432c9"
# Brian (deep confident) - likely candidate for "all-rounder"
VOICE_ID = "nPczCjzI2devNBz1zQrb"  # Brian
# Alternative: Chris (confident male): "iP95p4xoKVk53GoZ742B"

# === UNIQUE BACKGROUND ASSIGNMENTS - Week 2 ===
# Each video gets a different background - NO repeats from Week 1
BG_MAP = {
    "01_algorithm":    os.path.join(ASSETS, "nba_edwards_hang.mp4"),
    "02_vegashates":   os.path.join(ASSETS, "nba_allstar.mp4"),
    "03_factors":      os.path.join(ASSETS, "nba_top10.mp4"),
    "04_heart":        os.path.join(ASSETS, "nba_spurs_okc.mp4"),
    "05_march":        os.path.join(ASSETS, "nba_josh_clip4.mp4"),
    "06_receipts":     os.path.join(DOWNLOADS, "Anthony_Edwards_NBA_Dunking__Kling_25_Turbo_Pro_66818.mp4"),
    "07_freepack":     os.path.join(DOWNLOADS, "tiktok video backround for launch video.mp4"),
}

# === VOICEOVER SCRIPTS - Week 2 Trendy Content ===
VO_SCRIPTS = {
    "01_algorithm": "The algorithm never sleeps. While you're catching Z's, our AI is crunching numbers, analyzing matchups, finding edges. 24/7 non-stop. That's why we hit 74 percent. Parlay Guarantee dot com.",
    
    "02_vegashates": "Vegas hates this one trick. Our AI finds the edges they don't want you to know about. Hidden injuries, referee tendencies, travel fatigue. The stuff that moves lines. 74 percent accuracy. Parlay Guarantee dot com.",
    
    "03_factors": "38 factors. That's what our AI analyzes per game. Pace, defense, rest days, coaching records, referee history, weather, travel schedules. You check maybe three. We check everything. Parlay Guarantee dot com.",
    
    "04_heart": "Stop betting with your heart. Your gut says take the Lakers because you love LeBron. The AI sees they're on a back-to-back, missing two starters, and the refs favor the under. Data beats emotion. Parlay Guarantee dot com.",
    
    "05_march": "March Madness preview. Brackets get busted every year. But what if you had AI analyzing every upset possibility? Tournament experience, coaching, momentum, matchup advantages. Get ready. Parlay Guarantee dot com.",
    
    "06_receipts": "The receipts don't lie. 74 percent accuracy. 79 consecutive profitable nights. 100 percent deposit retention. Every single pick tracked and verified. The numbers speak for themselves. Parlay Guarantee dot com.",
    
    "07_freepack": "Free first pack. No credit card. No commitment. Just pure AI-powered picks to prove we're the real deal. See the 74 percent accuracy for yourself. What do you have to lose? Parlay Guarantee dot com.",
}


def generate_vo(key, script):
    """Generate voiceover via ElevenLabs API using 'all-rounder' voice"""
    outpath = os.path.join(ASSETS, f"vo_week2_{key}.mp3")
    if os.path.exists(outpath) and os.path.getsize(outpath) > 10000:
        print(f"  VO exists: {key}", flush=True)
        return outpath

    print(f"  Generating VO: {key}...", flush=True)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": script,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code == 200:
        with open(outpath, "wb") as f:
            f.write(resp.content)
        print(f"  VO saved: {outpath} ({len(resp.content)} bytes)", flush=True)
        return outpath
    else:
        print(f"  VO FAILED: {resp.status_code} {resp.text[:200]}", flush=True)
        return None


def drawtext(text, color, start, end, y, size=56, font=None, glow=True):
    """Single drawtext with optional glow layer for impact"""
    if font is None:
        font = FONT_IMPACT  # Use Impact font by default for bold look
    text = text.replace("'", "").replace(":", "\\:")
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


def build_video(key, duration, text_parts, vo_path):
    """Build video with unique background + text + VO + beat"""
    bg = BG_MAP[key]
    if not os.path.exists(bg):
        print(f"  MISSING BG: {bg}", flush=True)
        return None

    outpath = os.path.join(OUTDIR, f"pg_WEEK2_{key}.mp4")
    text_chain = ",".join(text_parts)

    # Check if VO exists
    has_vo = vo_path and os.path.exists(vo_path)

    if has_vo:
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
            "-stream_loop", "-1", "-i", bg,
            "-i", vo_path,
            "-i", BEAT,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-t", str(duration), outpath
        ]
    else:
        # No VO - just beat
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30,"
            f"eq=brightness=-0.08:contrast=1.5:saturation=2.0:gamma=1.15,"
            f"colorbalance=rs=0.0:gs=0.12:bs=-0.08:rm=0.0:gm=0.08:bm=0.0,"
            f"trim=duration={duration},setpts=PTS-STARTPTS,"
            f"vignette=PI/3,"
            f"{text_chain}[outv];"
            f"[1:a]aformat=fltp:44100:stereo,volume=0.5,afade=t=in:st=0:d=0.5,atrim=duration={duration}[outa]"
        )
        cmd = [
            FFMPEG, "-y",
            "-stream_loop", "-1", "-i", bg,
            "-i", BEAT,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-t", str(duration), outpath
        ]

    print(f"  Building {os.path.basename(outpath)} with {os.path.basename(bg)}...", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  FAILED! stderr:", flush=True)
        print(r.stderr[-2000:], flush=True)
        return None
    size_mb = os.path.getsize(outpath) / 1024 / 1024
    print(f"  {os.path.basename(outpath)}: {size_mb:.1f} MB", flush=True)
    return outpath


# === WEEK 2 VIDEO DEFINITIONS ===

def vid_01_algorithm():
    """The Algorithm Never Sleeps - AI working 24/7"""
    dur = 14
    vo = generate_vo("01_algorithm", VO_SCRIPTS["01_algorithm"])
    texts = []
    texts += drawtext("THE ALGORITHM", GREEN, 0.2, 2.5, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("NEVER SLEEPS", GREEN, 0.2, 2.5, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("24/7 Non-Stop", WHITE, 0.2, 2.5, "h-280", 48)
    texts += drawtext("WHILE YOU SLEEP", WHITE, 2.5, 5.0, "h/2-250", 75, FONT_IMPACT)
    texts += drawtext("AI IS WORKING", GREEN, 2.5, 5.0, "h/2-140", 80, FONT_IMPACT)
    texts += drawtext("Crunching numbers, finding edges", WHITE, 2.5, 5.0, "h-280", 44)
    texts += drawtext("74% ACCURACY", GREEN, 5.0, 8.0, "h/2-250", 95, FONT_IMPACT)
    texts += drawtext("Never stops grinding", WHITE, 5.0, 8.0, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GREEN, 8.0, 14.0, "h-280", 52)
    return build_video("01_algorithm", dur, texts, vo)


def vid_02_vegashates():
    """Vegas Hates This - AI finds edges Vegas doesn't want you to know"""
    dur = 15
    vo = generate_vo("02_vegashates", VO_SCRIPTS["02_vegashates"])
    texts = []
    texts += drawtext("VEGAS HATES", WHITE, 0.2, 2.0, "h/2-300", 85, FONT_IMPACT)
    texts += drawtext("THIS TRICK", GREEN, 0.2, 2.0, "h/2-190", 90, FONT_IMPACT)
    texts += drawtext("The edges they hide", WHITE, 0.2, 2.0, "h-280", 48)
    texts += drawtext("HIDDEN INJURIES", GREEN, 2.0, 4.5, "h/2-320", 70, FONT_IMPACT)
    texts += drawtext("REF TENDENCIES", GREEN, 2.0, 4.5, "h/2-220", 70, FONT_IMPACT)
    texts += drawtext("TRAVEL FATIGUE", GREEN, 2.0, 4.5, "h/2-120", 70, FONT_IMPACT)
    texts += drawtext("What moves the lines", WHITE, 2.0, 4.5, "h-280", 48)
    texts += drawtext("74% ACCURACY", GREEN, 4.5, 7.0, "h/2-250", 95, FONT_IMPACT)
    texts += drawtext("The secret is out", WHITE, 4.5, 7.0, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GREEN, 7.0, 15.0, "h-280", 52)
    return build_video("02_vegashates", dur, texts, vo)


def vid_03_factors():
    """38 Factors - breakdown of what AI analyzes"""
    dur = 16
    vo = generate_vo("03_factors", VO_SCRIPTS["03_factors"])
    texts = []
    texts += drawtext("38 FACTORS", GREEN, 0.2, 2.5, "h/2-250", 100, FONT_IMPACT)
    texts += drawtext("Per Game Analysis", WHITE, 0.2, 2.5, "h-280", 48)
    texts += drawtext("PACE  DEFENSE  REST", WHITE, 2.5, 5.0, "h/2-320", 60, FONT_IMPACT)
    texts += drawtext("COACHING  REFS  WEATHER", WHITE, 2.5, 5.0, "h/2-220", 60, FONT_IMPACT)
    texts += drawtext("TRAVEL  SCHEDULES", WHITE, 2.5, 5.0, "h/2-120", 60, FONT_IMPACT)
    texts += drawtext("You check maybe 3", WHITE, 2.5, 5.0, "h-280", 48)
    texts += drawtext("WE CHECK", GREEN, 5.0, 8.0, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("EVERYTHING", GREEN, 5.0, 8.0, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("Every angle covered", WHITE, 5.0, 8.0, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GREEN, 8.0, 16.0, "h-280", 52)
    return build_video("03_factors", dur, texts, vo)


def vid_04_heart():
    """Stop Betting With Your Heart - emotion vs data"""
    dur = 17
    vo = generate_vo("04_heart", VO_SCRIPTS["04_heart"])
    texts = []
    texts += drawtext("STOP BETTING", WHITE, 0.2, 2.5, "h/2-280", 80, FONT_IMPACT)
    texts += drawtext("WITH YOUR HEART", WHITE, 0.2, 2.5, "h/2-170", 75, FONT_IMPACT)
    texts += drawtext("❤️", WHITE, 0.2, 2.5, "h/2-50", 80)
    texts += drawtext("Your gut says Lakers", WHITE, 2.5, 5.0, "h-280", 48)
    texts += drawtext("THE AI SEES", GREEN, 5.0, 8.0, "h/2-320", 75, FONT_IMPACT)
    texts += drawtext("BACK-TO-BACK", GREEN, 5.0, 8.0, "h/2-220", 65, FONT_IMPACT)
    texts += drawtext("MISSING STARTERS", GREEN, 5.0, 8.0, "h/2-130", 60, FONT_IMPACT)
    texts += drawtext("REF FAVORS UNDER", GREEN, 5.0, 8.0, "h/2-50", 60, FONT_IMPACT)
    texts += drawtext("DATA BEATS EMOTION", GREEN, 8.0, 11.0, "h/2-250", 80, FONT_IMPACT)
    texts += drawtext("Every single time", WHITE, 8.0, 11.0, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GREEN, 11.0, 17.0, "h-280", 52)
    return build_video("04_heart", dur, texts, vo)


def vid_05_march():
    """March Madness Preview - AI ready for tournament chaos"""
    dur = 15
    vo = generate_vo("05_march", VO_SCRIPTS["05_march"])
    texts = []
    texts += drawtext("MARCH MADNESS", GREEN, 0.2, 2.5, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("PREVIEW", GREEN, 0.2, 2.5, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("Brackets get busted every year", WHITE, 0.2, 2.5, "h-280", 44)
    texts += drawtext("WHAT IF YOU HAD AI", WHITE, 2.5, 5.0, "h/2-280", 70, FONT_IMPACT)
    texts += drawtext("ANALYZING UPSETS?", GREEN, 2.5, 5.0, "h/2-170", 75, FONT_IMPACT)
    texts += drawtext("Tournament experience matters", WHITE, 2.5, 5.0, "h-280", 44)
    texts += drawtext("COACHING", GREEN, 5.0, 8.0, "h/2-320", 65, FONT_IMPACT)
    texts += drawtext("MOMENTUM", GREEN, 5.0, 8.0, "h/2-230", 65, FONT_IMPACT)
    texts += drawtext("MATCHUPS", GREEN, 5.0, 8.0, "h/2-140", 65, FONT_IMPACT)
    texts += drawtext("Every advantage calculated", WHITE, 5.0, 8.0, "h-280", 44)
    texts += drawtext("GET READY", GREEN, 8.0, 11.0, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("ParlayGuarantee.com", GREEN, 11.0, 15.0, "h-280", 52)
    return build_video("05_march", dur, texts, vo)


def vid_06_receipts():
    """The Receipts - showing 74% accuracy, track record"""
    dur = 16
    vo = generate_vo("06_receipts", VO_SCRIPTS["06_receipts"])
    texts = []
    texts += drawtext("THE RECEIPTS", GREEN, 0.2, 2.0, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("DONT LIE", WHITE, 0.2, 2.0, "h/2-140", 90, FONT_IMPACT)
    texts += drawtext("Numbers speak for themselves", WHITE, 0.2, 2.0, "h-280", 44)
    texts += drawtext("74%", GREEN, 2.0, 4.5, "h/2-350", 160, FONT_IMPACT)
    texts += drawtext("ACCURACY", WHITE, 2.0, 4.5, "h/2-160", 70, FONT_IMPACT)
    texts += drawtext("Verified and tracked", WHITE, 2.0, 4.5, "h-280", 48)
    texts += drawtext("79 NIGHTS", GREEN, 4.5, 7.0, "h/2-300", 85, FONT_IMPACT)
    texts += drawtext("STRAIGHT PROFIT", GREEN, 4.5, 7.0, "h/2-180", 75, FONT_IMPACT)
    texts += drawtext("100% deposit retention", WHITE, 4.5, 7.0, "h-280", 48)
    texts += drawtext("EVERY PICK", WHITE, 7.0, 10.0, "h/2-280", 80, FONT_IMPACT)
    texts += drawtext("TRACKED", GREEN, 7.0, 10.0, "h/2-170", 80, FONT_IMPACT)
    texts += drawtext("Full transparency", WHITE, 7.0, 10.0, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GREEN, 10.0, 16.0, "h-280", 52)
    return build_video("06_receipts", dur, texts, vo)


def vid_07_freepack():
    """Free First Pack - promotional video"""
    dur = 14
    vo = generate_vo("07_freepack", VO_SCRIPTS["07_freepack"])
    texts = []
    texts += drawtext("FREE", GREEN, 0.2, 2.0, "h/2-320", 120, FONT_IMPACT)
    texts += drawtext("FIRST PACK", WHITE, 0.2, 2.0, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("No credit card required", WHITE, 0.2, 2.0, "h-280", 48)
    texts += drawtext("NO COMMITMENT", WHITE, 2.0, 4.5, "h/2-280", 75, FONT_IMPACT)
    texts += drawtext("JUST PURE AI PICKS", GREEN, 2.0, 4.5, "h/2-170", 70, FONT_IMPACT)
    texts += drawtext("Prove we're the real deal", WHITE, 2.0, 4.5, "h-280", 44)
    texts += drawtext("74% ACCURACY", GREEN, 4.5, 7.0, "h/2-250", 95, FONT_IMPACT)
    texts += drawtext("See it for yourself", WHITE, 4.5, 7.0, "h-280", 48)
    texts += drawtext("WHAT DO YOU", WHITE, 7.0, 10.0, "h/2-280", 75, FONT_IMPACT)
    texts += drawtext("HAVE TO LOSE?", GREEN, 7.0, 10.0, "h/2-170", 75, FONT_IMPACT)
    texts += drawtext("ParlayGuarantee.com", GREEN, 10.0, 14.0, "h-280", 52)
    return build_video("07_freepack", dur, texts, vo)


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("BUILDING WEEK 2 TIKTOK VIDEOS - 7 TRENDY VIDEOS", flush=True)
    print("=" * 60, flush=True)
    
    # Verify all backgrounds exist
    print("\nChecking backgrounds...", flush=True)
    for key, path in BG_MAP.items():
        exists = os.path.exists(path)
        size = os.path.getsize(path) / 1024 / 1024 if exists else 0
        print(f"  {key}: {os.path.basename(path)} {'OK' if exists else 'MISSING'} ({size:.1f} MB)", flush=True)
    
    # Generate VOs
    print(f"\nGenerating voiceovers with voice ID: {VOICE_ID}...", flush=True)
    for key, script in VO_SCRIPTS.items():
        generate_vo(key, script)
    
    # Build videos
    print("\nBuilding Week 2 videos...", flush=True)
    results = []
    for fn in [vid_01_algorithm, vid_02_vegashates, vid_03_factors, 
               vid_04_heart, vid_05_march, vid_06_receipts, vid_07_freepack]:
        r = fn()
        results.append(r)
    
    print("\n" + "=" * 60, flush=True)
    print("WEEK 2 VIDEOS COMPLETE!", flush=True)
    for r in results:
        if r:
            print(f"  ✓ {os.path.basename(r)}", flush=True)
    print("=" * 60, flush=True)