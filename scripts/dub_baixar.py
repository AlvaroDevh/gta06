#!/usr/bin/env python3
"""
Baixa o VÍDEO inteiro (até 1080p) para dublar.

  dub_baixar.py <link | release:<tag>/<arquivo>> --job J [--saida tmp/dub/J/fonte.mp4]

-> grava o vídeo em --saida e jobs/J/meta.json (título, canal, link, duração).
Usa o mesmo cookies do YouTube (segredo YT_COOKIES) do resto do robô.
"""
import argparse, json, os, subprocess, sys

COOKIES = os.environ.get("YTDLP_COOKIES") if os.path.isfile(os.environ.get("YTDLP_COOKIES", "")) else None


def duracao(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fonte")
    ap.add_argument("--job", required=True)
    ap.add_argument("--saida", default="")
    a = ap.parse_args()
    saida = a.saida or os.path.join("tmp", "dub", a.job, "fonte.mp4")
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    os.makedirs(os.path.join("jobs", a.job), exist_ok=True)
    meta_arq = os.path.join("jobs", a.job, "meta.json")
    meta = json.load(open(meta_arq, encoding="utf-8")) if os.path.isfile(meta_arq) else {}

    if os.path.isfile(saida) and os.path.getsize(saida) > 1_000_000:
        print("fonte já existe (cache):", saida, flush=True)
        meta.setdefault("duracao", duracao(saida))
        json.dump(meta, open(meta_arq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return

    if a.fonte.startswith("release:"):  # release:<tag>/<arquivo>
        tag, arq = a.fonte[8:].split("/", 1)
        pasta = os.path.dirname(saida)
        subprocess.run(["gh", "release", "download", tag, "-p", arq, "-D", pasta, "--clobber"], check=True)
        os.replace(os.path.join(pasta, arq), saida)
        meta.update({"url": a.fonte, "titulo": meta.get("titulo") or arq, "duracao": duracao(saida)})
    else:
        import yt_dlp
        o = {"quiet": True, "no_warnings": True, "noplaylist": True, "merge_output_format": "mp4",
             "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
             "remote_components": ["ejs:github"],
             "outtmpl": saida.replace(".mp4", ".%(ext)s"), "concurrent_fragment_downloads": 8}
        if COOKIES:
            o["cookiefile"] = COOKIES
        try:
            with yt_dlp.YoutubeDL(o) as y:
                i = y.extract_info(a.fonte, download=True)
        except yt_dlp.utils.DownloadError as e:
            msg = str(e)
            if "not a bot" in msg or "Sign in to confirm" in msg:
                sys.exit("ERRO_YOUTUBE_BLOQUEOU: o YouTube bloqueou o servidor do GitHub. Crie o segredo YT_COOKIES "
                         "(cookies do seu navegador, formato Netscape) ou baixe o vídeo no seu PC, suba numa Release "
                         "e use  release:<tag>/<arquivo.mp4>  no lugar do link.")
            if "format is not available" in msg:
                print("\nFormatos que o YouTube ofereceu (diagnóstico):", flush=True)
                subprocess.run(["yt-dlp", "--list-formats"] + (["--cookies", COOKIES] if COOKIES else []) + [a.fonte])
                sys.exit("ERRO_FORMATO: confira se o passo 'denoland/setup-deno' está no workflow e se o yt-dlp está "
                         "atualizado. Se o diagnóstico acima só mostrar 'storyboard/images', falta o interpretador de JS.")
            raise
        if not os.path.isfile(saida):  # yt-dlp pode ter gravado .mkv/.webm
            for ext in ("mkv", "webm", "mov"):
                alt = saida.replace(".mp4", "." + ext)
                if os.path.isfile(alt):
                    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", alt, "-c", "copy", saida], check=True)
                    os.remove(alt)
        meta.update({"url": a.fonte, "titulo": i.get("title"), "canal": i.get("uploader") or i.get("channel"),
                     "duracao": i.get("duration") or duracao(saida), "idioma_video": i.get("language")})
    json.dump(meta, open(meta_arq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("baixado:", saida, f"{os.path.getsize(saida) / 1e6:.0f} MB", json.dumps(meta, ensure_ascii=False)[:300],
          flush=True)


if __name__ == "__main__":
    main()
