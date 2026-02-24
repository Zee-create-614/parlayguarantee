"""Download free stock sports videos from Pexels and music from Pixabay"""
import urllib.request
import os
import json

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Pexels video IDs - basketball and football action shots
# These are free to use commercially, no attribution required
PEXELS_VIDEOS = {
    "basketball1": "https://www.pexels.com/video/5586522/",  # man playing basketball
    "basketball2": "https://www.pexels.com/video/5192157/",  # basketball game
    "basketball3": "https://www.pexels.com/video/13037588/", # game of basketball
}

def download_pexels_video(video_id, filename):
    """Download video from Pexels using their free video API"""
    url = f"https://api.pexels.com/videos/videos/{video_id}"
    req = urllib.request.Request(url)
    # Pexels API key (free tier)
    req.add_header("Authorization", "vYKLnsnT7Gk0ygJKpE1ow6cGk6RVl9nM7R9rK0YNYHI6AvbJbLp2rx28")
    
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
        
        # Find the best video file (HD, portrait preferred)
        video_files = data.get("video_files", [])
        best = None
        for vf in video_files:
            # Prefer HD quality
            if vf.get("quality") == "hd" and vf.get("width", 0) >= 720:
                if best is None or vf.get("height", 0) > best.get("height", 0):
                    best = vf
        
        if not best:
            # Fallback to any file
            best = video_files[0] if video_files else None
        
        if best:
            dl_url = best["link"]
            outpath = os.path.join(ASSETS, filename)
            print(f"  Downloading {filename} ({best.get('width')}x{best.get('height')})...")
            urllib.request.urlretrieve(dl_url, outpath)
            size_mb = os.path.getsize(outpath) / 1024 / 1024
            print(f"  OK: {size_mb:.1f} MB")
            return outpath
        else:
            print(f"  No video files found for {video_id}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

if __name__ == "__main__":
    print("Downloading sports stock footage from Pexels...")
    for name, url in PEXELS_VIDEOS.items():
        vid_id = url.rstrip("/").split("/")[-1]
        download_pexels_video(vid_id, f"{name}.mp4")
    print("\nDone!")
