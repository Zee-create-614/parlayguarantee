import urllib.request, json

# ElevenLabs public voices endpoint (no API key needed to list)
req = urllib.request.Request('https://api.elevenlabs.io/v1/voices')
req.add_header('accept', 'application/json')
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
for v in data.get('voices', [])[:10]:
    labels = v.get('labels', {})
    print(f"{v['voice_id']} | {v['name']} | {labels.get('accent','')} {labels.get('gender','')} {labels.get('use_case','')}")
