#!/usr/bin/env python3
"""
Transcreve o vídeo original (qualquer língua) com faster-whisper, rodando no próprio GitHub Actions.

  dub_transcrever.py <video> --job J [--idioma en|auto|...] [--modelo small]

-> jobs/J/fonte_transcricao.json   [{"start","end","text"}, ...]
   jobs/J/fonte_transcricao.txt    uma linha por trecho, legível
"""
import argparse, json, os, subprocess, time, wave

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--job", required=True)
    ap.add_argument("--idioma", default="en")
    ap.add_argument("--modelo", default="small", help="base (rápido) | small (bom) | medium (melhor, bem mais lento)")
    a = ap.parse_args()
    pasta = os.path.join("jobs", a.job)
    os.makedirs(pasta, exist_ok=True)
    wav = os.path.join("tmp", "dub", a.job, "audio16k.wav")
    os.makedirs(os.path.dirname(wav), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.video, "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", wav], check=True)

    # lê o WAV aqui mesmo (16 kHz, mono) e entrega ao Whisper como lista de números:
    # assim o faster-whisper não usa o PyAV para abrir arquivo (que quebra em algumas versões)
    with wave.open(wav) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    from faster_whisper import WhisperModel
    m = WhisperModel(a.modelo, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 2)
    t0 = time.time()
    segs, info = m.transcribe(audio, language=None if a.idioma == "auto" else a.idioma, vad_filter=True,
                              beam_size=1, condition_on_previous_text=False)
    out, ultimo = [], 0
    for s in segs:
        txt = s.text.strip()
        if txt:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": txt})
        if s.end - ultimo > 120:
            ultimo = s.end
            print(f"   transcrito até {s.end / 60:.1f} min ({time.time() - t0:.0f}s de trabalho)", flush=True)
    json.dump({"idioma": info.language, "duracao": round(info.duration, 1), "trechos": out},
              open(os.path.join(pasta, "fonte_transcricao.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(pasta, "fonte_transcricao.txt"), "w", encoding="utf-8") as f:
        for s in out:
            f.write(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}\n")
    print(f"TRANSCRITO {len(out)} trechos, idioma {info.language}, {info.duration / 60:.1f} min em "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
