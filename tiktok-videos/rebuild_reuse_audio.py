"""Rebuild launch video - reuse original All-Rounder audio, just change text overlays to clean language.
The voice says the OLD script but we overlay CLEAN text. Mismatch will be obvious.
Instead: use the Josh voice.mp3 from Downloads as the audio (it's already the right voice).
Actually let's check what the Josh voice.mp3 says first."""
import subprocess, os

FFPROBE = r"C:\Users\joshs\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffprobe.exe"

# Check durations
for f in [
    r"C:\Users\joshs\Downloads\Josh voice.mp3",
    r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\reference_allrounder.aac",
    r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\tiktok-videos\assets\vo_original_extract.wav",
]:
    probe = subprocess.run([FFPROBE, "-v","quiet","-show_entries","format=duration","-of","csv=p=0", f], capture_output=True, text=True)
    print(f"{os.path.basename(f)}: {probe.stdout.strip()}s")
