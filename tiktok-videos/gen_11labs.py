"""Generate voiceover audio using ElevenLabs API"""
import urllib.request
import json
import os
import sys

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
API_KEY = os.environ.get("ELEVEN_API_KEY", "")

# Best voices for sports/hype content:
# TX3LPaxmHKxFdv7VOQHJ = Liam - Energetic, Social Media Creator (american male)
# IKne3meq5aSn9XLyUdCD = Charlie - Deep, Confident, Energetic (australian male)
# CwhRBWXzGAHq8TQ4Fs17 = Roger - Laid-Back, Casual, Resonant (american male)
VOICE_ID = "TX3LPaxmHKxFdv7VOQHJ"  # Liam - perfect for TikTok

SCRIPTS = {
    "vo_launch.mp3": "Parlay Guarantee. AI powered sports picks. Seventy four percent accuracy. Seventy nine straight profitable nights. Your money back if we're wrong. Parlay Guarantee dot com.",
    "vo_howitworks.mp3": "Here's how it works. Step one. Pick your sport. NBA, NFL, MLB, UFC, and more. Step two. Our AI analyzes over thirty eight factors. Injuries, matchups, trends, odds movement. Step three. Win, or get your money back. It's that simple. Parlay Guarantee dot com. Link in bio.",
    "vo_guarantee.mp3": "Tired of losing your bets? We put our money where our mouth is. Seventy four percent accuracy. If we're wrong, you get a full refund. No questions asked. Parlay Guarantee dot com. Link in bio.",
}

def generate_voice(text, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    payload = json.dumps({
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True
        }
    }).encode()
    
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("xi-api-key", API_KEY)
    req.add_header("Accept", "audio/mpeg")
    
    try:
        resp = urllib.request.urlopen(req)
        with open(output_path, "wb") as f:
            f.write(resp.read())
        size_kb = os.path.getsize(output_path) / 1024
        print(f"  OK: {os.path.basename(output_path)} ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

if __name__ == "__main__":
    if not API_KEY:
        print("ERROR: Set ELEVEN_API_KEY environment variable")
        print("Get your key at: https://elevenlabs.io/app/settings/api-keys")
        sys.exit(1)
    
    print(f"Generating voiceovers with ElevenLabs (voice: Liam)...")
    for filename, script in SCRIPTS.items():
        outpath = os.path.join(ASSETS, filename)
        print(f"  Generating {filename}...")
        generate_voice(script, outpath)
    print("Done!")
