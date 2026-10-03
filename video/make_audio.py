"""Narration -> per-sentence TTS (macOS `say`) -> voiceover.wav + timeline.json.

Scene length is driven by the audio, so visuals can never drift from the voice.
"""
import json, subprocess, os, wave
VOICE, RATE = "Ava (Premium)", 190
GAP, SCENE_PAD, LEAD = 0.25, 0.8, 0.4
os.makedirs("video/build/aud", exist_ok=True)
scenes = json.load(open("video/narration.json"))
t = 0.0; out = []; concat = []
def dur(p):
    w = wave.open(p); return w.getnframes() / w.getframerate()
silence = "video/build/aud/sil.wav"
def sil(name, d):
    p = f"video/build/aud/{name}.wav"
    subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i","anullsrc=r=44100:cl=mono","-t",str(d),p],check=True); return p
for sc in scenes:
    start = t; sents = []
    concat.append(sil(f"lead_{sc['id']}", LEAD)); t += LEAD
    for i, s in enumerate(sc["s"]):
        base = f"video/build/aud/{sc['id']}_{i}"
        subprocess.run(["say","-v",VOICE,"-r",str(RATE),"-o",base+".aiff",s],check=True)
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",base+".aiff","-ar","44100","-ac","1",base+".wav"],check=True)
        d = dur(base+".wav"); sents.append({"text": s, "start": round(t,3), "end": round(t+d,3)})
        concat.append(base+".wav"); t += d
        g = GAP if i < len(sc["s"])-1 else SCENE_PAD
        concat.append(sil(f"gap_{sc['id']}_{i}", g)); t += g
    out.append({"id": sc["id"], "start": round(start,3), "end": round(t,3), "sentences": sents})
if scenes[-1]["id"] == "outro":      # hold the logo after the last word
    concat.append(sil("tail", 3.5)); t += 3.5; out[-1]["end"] = round(t,3)
open("video/build/list.txt","w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in concat))
subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i","video/build/list.txt","-c","copy","video/build/voiceover.wav"],check=True)
json.dump({"total": round(t,3), "scenes": out}, open("video/timeline.json","w"), indent=1)
print("total %.1fs" % t); [print(s["id"], round(s["end"]-s["start"],1)) for s in out]
