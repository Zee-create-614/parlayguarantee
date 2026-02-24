"""
Build ALL ParlayGuarantee TikTok videos - UNIQUE backgrounds per video
Uses v4 style: vibrant colors, glow text, beat track
Each video gets a different NBA clip so nothing repeats
"""
import subprocess
import os
import sys
import requests

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

# ElevenLabs TTS
ELEVEN_API_KEY = "sk_3bd03ab4e8df0cb2609ff7d1c58b7167a108d24566c432c9"

# === UNIQUE BACKGROUND ASSIGNMENTS ===
# Each video gets a different clip - NO repeats
BG_MAP = {
    "01_launch":        os.path.join(ASSETS, "nba_edwards_dunk.mp4"),
    "02_howitworks":    os.path.join(ASSETS, "nba_fast_break.mp4"),
    "03_guarantee":     os.path.join(ASSETS, "nba_slam_dunk.mp4"),
    "day3_challenge":   os.path.join(ASSETS, "nba_buzzer_beater.mp4"),
    "day4_receipts":    os.path.join(ASSETS, "nba_josh_clip1.mp4"),
    "day5_aivsgut":     os.path.join(ASSETS, "nba_josh_clip2.mp4"),
    "day6_marchmadness": os.path.join(ASSETS, "nba_josh_clip3.mp4"),
}

# === VOICEOVER SCRIPTS ===
VO_SCRIPTS = {
    "01_launch": "Parlay Guarantee is now live. AI-powered sports picks with 74 percent accuracy over 79 consecutive profitable nights. Your money back if we're wrong. Parlay Guarantee dot com.",
    "02_howitworks": "Here's how it works. Step one, pick your sport. NBA, NFL, MLB, NHL, UFC, or soccer. Step two, our AI analyzes 38 factors including injuries, matchups, and trends. Step three, win or get a full refund. It's that simple. Parlay Guarantee dot com.",
    "03_guarantee": "Tired of losing your bets? We put our money where our mouth is. 74 percent accuracy rate. If we're wrong, you get a full refund. No questions asked. Parlay Guarantee dot com.",
    "day3_challenge": "Think you can beat the AI? Our engine analyzes 38 factors per game. Injuries, matchups, pace, rest days, travel, referee tendencies, and more. Drop your best pick in the comments. Let's see who wins. Parlay Guarantee dot com.",
    "day4_receipts": "Don't just take our word for it. Here are the receipts. 74 percent accuracy. 79 consecutive profitable nights. 100 percent deposit keep rate. Every single pick is tracked and verified. See for yourself at Parlay Guarantee dot com.",
    "day5_aivsgut": "AI versus gut feeling. Your gut says take the favorite. The AI sees a rest advantage, a weak defensive matchup, and an injury the public hasn't priced in. 38 factors. No emotion. No bias. Just data. Parlay Guarantee dot com.",
    "day6_marchmadness": "March Madness is coming. Upsets, busted brackets, and chaos. But what if you had AI analyzing every matchup? 38 factors per game. Tempo, defensive efficiency, tournament experience, coaching records, and more. Get ready at Parlay Guarantee dot com.",
}


def generate_vo(key, script):
    """Generate voiceover via ElevenLabs API"""
    outpath = os.path.join(ASSETS, f"vo_{key}.mp3")
    if os.path.exists(outpath) and os.path.getsize(outpath) > 10000:
        print(f"  VO exists: {key}", flush=True)
        return outpath

    print(f"  Generating VO: {key}...", flush=True)
    url = "https://api.elevenlabs.io/v1/text-to-speech/pNInz6obpgDQGcFmaJgB"  # Adam voice
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
    """Single drawtext with optional glow layer"""
    if font is None:
        font = FONT
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

    outpath = os.path.join(OUTDIR, f"pg_WEEK1_{key}.mp4")
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


# === VIDEO DEFINITIONS ===

def vid_01_launch():
    dur = 15
    vo = generate_vo("01_launch", VO_SCRIPTS["01_launch"])
    texts = []
    texts += drawtext("PARLAY", GREEN, 0.2, 2.2, "h/2-300", 95, FONT_IMPACT)
    texts += drawtext("GUARANTEE", GOLD, 0.2, 2.2, "h/2-190", 90, FONT_IMPACT)
    texts += drawtext("IS NOW LIVE", WHITE, 0.2, 2.2, "h-280", 52)
    texts += drawtext("AI-Powered Sports Picks", WHITE, 2.2, 4.8, "h-280", 52)
    texts += drawtext("74% ACCURACY", GREEN, 4.8, 7.2, "h/2-250", 88, FONT_IMPACT)
    texts += drawtext("Exposed by AI", CYAN, 4.8, 7.2, "h-280", 52)
    texts += drawtext("79 NIGHTS", GOLD, 7.2, 10.0, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("PROFITABLE", GOLD, 7.2, 10.0, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("Exposed Straight", CYAN, 7.2, 10.0, "h-280", 52)
    texts += drawtext("Your Money Back If Were Wrong", WHITE, 10.0, 12.5, "h-280", 48)
    texts += drawtext("ParlayGuarantee.com", GOLD, 12.5, 15.0, "h-280", 52)
    return build_video("01_launch", dur, texts, vo)


def vid_02_howitworks():
    dur = 22
    vo = generate_vo("02_howitworks", VO_SCRIPTS["02_howitworks"])
    texts = []
    texts += drawtext("HOW IT WORKS", GREEN, 0.2, 3.0, "h/2-250", 85, FONT_IMPACT)
    texts += drawtext("Three Simple Steps", WHITE, 0.2, 3.0, "h-280", 52)
    texts += drawtext("38 FACTORS", GOLD, 6.5, 10.5, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("Pick Your Sport", WHITE, 3.0, 6.5, "h-280", 52)
    texts += drawtext("AI Analyzes Everything", CYAN, 6.5, 10.5, "h-280", 52)
    texts += drawtext("WIN OR", GREEN, 10.5, 15.0, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("MONEY BACK", GREEN, 10.5, 15.0, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("Guaranteed Results", WHITE, 10.5, 15.0, "h-280", 52)
    texts += drawtext("ParlayGuarantee.com", GOLD, 15.5, 22.0, "h-280", 52)
    return build_video("02_howitworks", dur, texts, vo)


def vid_03_guarantee():
    dur = 16
    vo = generate_vo("03_guarantee", VO_SCRIPTS["03_guarantee"])
    texts = []
    texts += drawtext("TIRED OF LOSING?", RED, 0.2, 2.5, "h/2-250", 80, FONT_IMPACT)
    texts += drawtext("Stop Throwing Money Away", WHITE, 0.2, 2.5, "h-280", 52, glow=False)
    texts += drawtext("We Back Every Pick", WHITE, 2.5, 5.2, "h-280", 52, glow=False)
    texts += drawtext("74% ACCURACY", GREEN, 5.2, 7.8, "h/2-250", 95, FONT_IMPACT)
    texts += drawtext("Exposed by AI", CYAN, 5.2, 7.8, "h-280", 52, glow=False)
    texts += drawtext("FULL REFUND", GOLD, 7.8, 10.5, "h/2-250", 85, FONT_IMPACT)
    texts += drawtext("If Were Wrong You Get Paid", WHITE, 7.8, 10.5, "h-280", 48, glow=False)
    texts += drawtext("NO QUESTIONS ASKED", GOLD, 10.5, 12.5, "h/2-250", 70, FONT_IMPACT)
    texts += drawtext("Period.", WHITE, 10.5, 12.5, "h-280", 52, glow=False)
    texts += drawtext("ParlayGuarantee.com", GOLD, 12.5, 16.0, "h-280", 52, glow=False)
    return build_video("03_guarantee", dur, texts, vo)


def vid_day3_challenge():
    dur = 18
    vo = generate_vo("day3_challenge", VO_SCRIPTS["day3_challenge"])
    texts = []
    texts += drawtext("CAN YOU BEAT", RED, 0.2, 2.5, "h/2-300", 80, FONT_IMPACT)
    texts += drawtext("THE AI?", GREEN, 0.2, 2.5, "h/2-190", 95, FONT_IMPACT)
    texts += drawtext("Think you know ball?", WHITE, 0.2, 2.5, "h-280", 52)
    texts += drawtext("38 FACTORS", GOLD, 2.5, 5.5, "h/2-280", 90, FONT_IMPACT)
    texts += drawtext("PER GAME", GOLD, 2.5, 5.5, "h/2-170", 80, FONT_IMPACT)
    texts += drawtext("Injuries  Matchups  Pace", CYAN, 2.5, 5.5, "h-280", 44)
    texts += drawtext("REST DAYS", GREEN, 5.5, 8.0, "h/2-280", 80, FONT_IMPACT)
    texts += drawtext("TRAVEL  REFS", GREEN, 5.5, 8.0, "h/2-170", 75, FONT_IMPACT)
    texts += drawtext("Things you never check", WHITE, 5.5, 8.0, "h-280", 48)
    texts += drawtext("DROP YOUR PICK", GOLD, 8.0, 11.0, "h/2-280", 80, FONT_IMPACT)
    texts += drawtext("IN THE COMMENTS", GOLD, 8.0, 11.0, "h/2-170", 75, FONT_IMPACT)
    texts += drawtext("Lets see who wins", WHITE, 8.0, 11.0, "h-280", 48)
    texts += drawtext("74% ACCURACY", GREEN, 11.0, 14.0, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("Can you beat that?", CYAN, 11.0, 14.0, "h-280", 52)
    texts += drawtext("ParlayGuarantee.com", GOLD, 14.0, 18.0, "h-280", 52)
    return build_video("day3_challenge", dur, texts, vo)


def vid_day4_receipts():
    dur = 18
    vo = generate_vo("day4_receipts", VO_SCRIPTS["day4_receipts"])
    texts = []
    texts += drawtext("THE RECEIPTS", GREEN, 0.2, 2.5, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("Dont just take our word", WHITE, 0.2, 2.5, "h-280", 48)
    texts += drawtext("74%", GREEN, 2.5, 5.5, "h/2-350", 160, FONT_IMPACT)
    texts += drawtext("ACCURACY", WHITE, 2.5, 5.5, "h/2-160", 70, FONT_IMPACT)
    texts += drawtext("Exposed by 38-factor AI", CYAN, 2.5, 5.5, "h-280", 48)
    texts += drawtext("79 NIGHTS", GOLD, 5.5, 8.5, "h/2-300", 95, FONT_IMPACT)
    texts += drawtext("STRAIGHT PROFIT", GOLD, 5.5, 8.5, "h/2-180", 75, FONT_IMPACT)
    texts += drawtext("100% deposit keep rate", WHITE, 5.5, 8.5, "h-280", 48)
    texts += drawtext("EVERY PICK", GREEN, 8.5, 11.5, "h/2-280", 85, FONT_IMPACT)
    texts += drawtext("TRACKED", GREEN, 8.5, 11.5, "h/2-170", 85, FONT_IMPACT)
    texts += drawtext("Full transparency", CYAN, 8.5, 11.5, "h-280", 52)
    texts += drawtext("SEE FOR YOURSELF", WHITE, 11.5, 14.0, "h/2-250", 75, FONT_IMPACT)
    texts += drawtext("ParlayGuarantee.com", GOLD, 14.0, 18.0, "h-280", 52)
    return build_video("day4_receipts", dur, texts, vo)


def vid_day5_aivsgut():
    dur = 20
    vo = generate_vo("day5_aivsgut", VO_SCRIPTS["day5_aivsgut"])
    texts = []
    texts += drawtext("AI", GREEN, 0.2, 2.5, "h/2-320", 120, FONT_IMPACT)
    texts += drawtext("vs", WHITE, 0.2, 2.5, "h/2-190", 70, FONT_IMPACT)
    texts += drawtext("GUT FEELING", RED, 0.2, 2.5, "h/2-100", 90, FONT_IMPACT)
    texts += drawtext("Which side are you on?", WHITE, 0.2, 2.5, "h-280", 48)
    texts += drawtext("YOUR GUT SAYS", RED, 2.5, 5.5, "h/2-280", 75, FONT_IMPACT)
    texts += drawtext("TAKE THE FAVORITE", RED, 2.5, 5.5, "h/2-170", 70, FONT_IMPACT)
    texts += drawtext("Everyone else is too", WHITE, 2.5, 5.5, "h-280", 48)
    texts += drawtext("THE AI SEES", GREEN, 5.5, 9.0, "h/2-320", 80, FONT_IMPACT)
    texts += drawtext("REST ADVANTAGE", CYAN, 5.5, 9.0, "h/2-210", 65, FONT_IMPACT)
    texts += drawtext("WEAK MATCHUP", CYAN, 5.5, 9.0, "h/2-120", 65, FONT_IMPACT)
    texts += drawtext("HIDDEN INJURY", CYAN, 5.5, 9.0, "h/2-30", 65, FONT_IMPACT)
    texts += drawtext("What the public misses", WHITE, 5.5, 9.0, "h-280", 48)
    texts += drawtext("38 FACTORS", GOLD, 9.0, 12.0, "h/2-280", 90, FONT_IMPACT)
    texts += drawtext("NO EMOTION", GOLD, 9.0, 12.0, "h/2-170", 80, FONT_IMPACT)
    texts += drawtext("NO BIAS", GOLD, 9.0, 12.0, "h/2-70", 80, FONT_IMPACT)
    texts += drawtext("Just data", WHITE, 9.0, 12.0, "h-280", 52)
    texts += drawtext("74% ACCURACY", GREEN, 12.0, 15.0, "h/2-250", 90, FONT_IMPACT)
    texts += drawtext("The numbers dont lie", CYAN, 12.0, 15.0, "h-280", 52)
    texts += drawtext("ParlayGuarantee.com", GOLD, 15.0, 20.0, "h-280", 52)
    return build_video("day5_aivsgut", dur, texts, vo)


def vid_day6_marchmadness():
    dur = 18
    vo = generate_vo("day6_marchmadness", VO_SCRIPTS["day6_marchmadness"])
    texts = []
    texts += drawtext("MARCH MADNESS", GOLD, 0.2, 3.0, "h/2-300", 85, FONT_IMPACT)
    texts += drawtext("IS COMING", RED, 0.2, 3.0, "h/2-190", 85, FONT_IMPACT)
    texts += drawtext("Upsets and busted brackets", WHITE, 0.2, 3.0, "h-280", 48)
    texts += drawtext("WHAT IF YOU HAD", WHITE, 3.0, 6.0, "h/2-280", 70, FONT_IMPACT)
    texts += drawtext("AI ON YOUR SIDE?", GREEN, 3.0, 6.0, "h/2-170", 80, FONT_IMPACT)
    texts += drawtext("Every matchup analyzed", CYAN, 3.0, 6.0, "h-280", 48)
    texts += drawtext("TEMPO", GREEN, 6.0, 9.0, "h/2-320", 70, FONT_IMPACT)
    texts += drawtext("DEFENSE", GREEN, 6.0, 9.0, "h/2-230", 70, FONT_IMPACT)
    texts += drawtext("EXPERIENCE", GREEN, 6.0, 9.0, "h/2-140", 70, FONT_IMPACT)
    texts += drawtext("COACHING", GREEN, 6.0, 9.0, "h/2-50", 70, FONT_IMPACT)
    texts += drawtext("38 factors per game", CYAN, 6.0, 9.0, "h-280", 48)
    texts += drawtext("GET READY", GOLD, 9.0, 12.0, "h/2-250", 95, FONT_IMPACT)
    texts += drawtext("Before tip-off", WHITE, 9.0, 12.0, "h-280", 52)
    texts += drawtext("ParlayGuarantee.com", GOLD, 12.0, 18.0, "h-280", 52)
    return build_video("day6_marchmadness", dur, texts, vo)


if __name__ == "__main__":
    import shutil
    
    print("=" * 60, flush=True)
    print("BUILDING ALL TIKTOK VIDEOS - UNIQUE BACKGROUNDS", flush=True)
    print("=" * 60, flush=True)
    
    # Verify all backgrounds exist
    print("\nChecking backgrounds...", flush=True)
    for key, path in BG_MAP.items():
        exists = os.path.exists(path)
        size = os.path.getsize(path) / 1024 / 1024 if exists else 0
        print(f"  {key}: {os.path.basename(path)} {'OK' if exists else 'MISSING'} ({size:.1f} MB)", flush=True)
    
    # Generate VOs
    print("\nGenerating voiceovers...", flush=True)
    for key, script in VO_SCRIPTS.items():
        generate_vo(key, script)
    
    # Build videos
    print("\nBuilding videos...", flush=True)
    results = []
    for fn in [vid_01_launch, vid_02_howitworks, vid_03_guarantee, 
               vid_day3_challenge, vid_day4_receipts, vid_day5_aivsgut, vid_day6_marchmadness]:
        r = fn()
        results.append(r)
    
    # Copy to Desktop
    print("\nCopying to Desktop...", flush=True)
    desktop = r"C:\Users\joshs\OneDrive\Desktop"
    for r in results:
        if r and os.path.exists(r):
            dest = os.path.join(desktop, os.path.basename(r))
            shutil.copy2(r, dest)
            print(f"  → {os.path.basename(r)}", flush=True)
    
    print("\n" + "=" * 60, flush=True)
    print("DONE! All videos on Desktop.", flush=True)
    print("=" * 60, flush=True)
