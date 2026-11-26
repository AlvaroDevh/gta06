#!/usr/bin/env python3
"""
Renderiza o vídeo resumido e dublado em português, parte por parte (9:16, 1080x1920).

  dub_render.py --job J --video fonte.mp4 [--so 01,02] [--tts edge|fake]

Lê  jobs/J/roteiro.json  (feito por dub_roteiro.py, ou escrito/editado à mão pelo Claude) e gera
saida/J/parte_01.mp4 ... + saida/J/publicacao.md.

Como cada parte é montada (a locução manda no tempo):
  1. cada fala vira áudio em português (edge-tts; reserva gTTS; "fake" só para teste);
  2. para cada fala, pega o trecho do vídeo original que ela resume, na velocidade certa para durar
     o mesmo que a voz (sem áudio original: ele está em inglês);
  3. fundo = o próprio vídeo ampliado e borrado; vídeo nítido 16:9 no meio;
  4. legenda palavra por palavra, em caixa alta, com a palavra falada em caixa roxa;
  5. voz normalizada (+ música de fundo baixinha, se houver arquivo em musicas/).
"""
import argparse, asyncio, hashlib, json, math, os, re, shutil, subprocess, sys, wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(AQUI, "..")
W, H, FPS, SR = 1080, 1920, 30, 44100

PADRAO = {
    "voz": "pt-BR-AntonioNeural",
    "ritmo": "+8%",            # velocidade da voz (edge-tts)
    "gancho": True,            # abre cada parte com a frase de gancho do roteiro
    "rotulo_parte": False,     # "PARTE 1/8" no topo
    "cor_destaque": "#6D3EF2", # caixa roxa da palavra falada
    "painel_centro": 0.541,    # centro do vídeo nítido (fração da altura)
    "legenda_centro": 0.807,   # centro da legenda (fração da altura)
    "pausa": 0.22,             # silêncio entre falas (s)
    "musica": "",              # arquivo opcional (ex.: musicas/fundo.mp3)
    "vol_musica": 0.07,
}


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def probe(arq, campo):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", f"stream={campo}",
                        "-of", "csv=p=0", arq], capture_output=True, text=True, check=True)
    return r.stdout.strip().split(",")[0]


def duracao_arquivo(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", arq],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


# ------------------------------------------------------------------ fonte
_FONTE_CACHE = {}


_ARQ_FONTE = []


def arquivo_fonte():
    if not _ARQ_FONTE:
        _ARQ_FONTE.append(_achar_fonte())
    return _ARQ_FONTE[0]


def _achar_fonte():
    """Montserrat Black: converte o woff2 do repositório (precisa de brotli); reservas: sistema, Poppins."""
    tmp = os.path.join(RAIZ, "tmp")
    os.makedirs(tmp, exist_ok=True)
    ttf = os.path.join(tmp, "montserrat-black.ttf")
    if os.path.isfile(ttf):
        return ttf, None
    woff = os.path.join(RAIZ, "fontes_legenda", "montserrat-latin-900-normal.woff2")
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(woff)
        f.flavor = None
        f.save(ttf)
        return ttf, None
    except Exception as e:
        print("   aviso: woff2 não convertido (", str(e)[:80], ") - tentando fonte do sistema", flush=True)
    for p in shutil.which("fc-list") and subprocess.run(["fc-list", ":family=Montserrat", "file"], capture_output=True,
                                                        text=True).stdout.splitlines() or []:
        p = p.split(":")[0].strip()
        if p.endswith(".ttf") and "Italic" not in p:
            return p, "Black"
    return os.path.join(RAIZ, "fonts", "Poppins-Bold.ttf"), None


def fonte(tam):
    if tam not in _FONTE_CACHE:
        arq, var = arquivo_fonte()
        f = ImageFont.truetype(arq, tam)
        if var:
            try:
                f.set_variation_by_name(var)
            except Exception:
                pass
        _FONTE_CACHE[tam] = f
    return _FONTE_CACHE[tam]


# ------------------------------------------------------------------ voz
def normaliza(s):
    return re.sub(r"\W+", "", s.lower())


def tempos_proporcionais(palavras, dur):
    pesos = []
    for w in palavras:
        p = len(w) + (4 if w[-1:] in ",;:" else 7 if w[-1:] in ".!?…" else 0)
        pesos.append(max(p, 2))
    tot = sum(pesos)
    t, out = 0.0, []
    for w, p in zip(palavras, pesos):
        d = dur * p / tot
        out.append((t, t + d * (0.86 if p > len(w) else 1.0)))
        t += d
    return out


def alinhar(palavras, bounds, dur):
    """Casa as palavras do texto com os marcadores da voz. Devolve [(t0,t1)] ou None."""
    n = len(palavras)
    if not bounds:
        return None
    if len(bounds) == n:
        return [(b[0], b[1]) for b in bounds]
    res, j = [None] * n, 0
    for i, w in enumerate(palavras):
        nw = normaliza(w)
        for k in range(j, len(bounds)):
            if nw and normaliza(bounds[k][2]) == nw:
                res[i] = (bounds[k][0], bounds[k][1])
                j = k + 1
                break
    if sum(r is not None for r in res) < 0.7 * n:
        return None
    i = 0
    while i < n:  # interpola as que faltaram entre vizinhas conhecidas
        if res[i] is None:
            a = i
            while i < n and res[i] is None:
                i += 1
            ini = res[a - 1][1] if a > 0 else 0.0
            fim = res[i][0] if i < n else dur
            seg = tempos_proporcionais(palavras[a:i], max(fim - ini, 0.05 * (i - a)))
            for k, (x, y) in enumerate(seg):
                res[a + k] = (ini + x, ini + y)
        else:
            i += 1
    return res


def ler_wav(arq):
    with wave.open(arq) as w:
        dados = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return dados


def aparar(x):
    """Tira silêncio do começo/fim. Devolve (amostras, segundos tirados do começo)."""
    forte = np.where(np.abs(x.astype(np.int32)) > 300)[0]
    if len(forte) == 0:
        return x, 0.0
    a = max(0, forte[0] - int(0.04 * SR))
    b = min(len(x), forte[-1] + int(0.10 * SR))
    return x[a:b], a / SR


async def _edge(texto, voz, ritmo, saida_mp3):
    import edge_tts
    try:
        com = edge_tts.Communicate(texto, voz, rate=ritmo, boundary="WordBoundary")
    except TypeError:  # versão antiga: já manda palavra por palavra
        com = edge_tts.Communicate(texto, voz, rate=ritmo)
    audio, marcas = bytearray(), []
    async for ch in com.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            marcas.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    if not audio:
        raise RuntimeError("edge-tts não devolveu áudio")
    with open(saida_mp3, "wb") as f:
        f.write(audio)
    return marcas


def _gtts(texto, saida_mp3):
    from gtts import gTTS
    gTTS(texto, lang="pt", tld="com.br").save(saida_mp3)


def _fake(texto):
    """Voz de mentira (tom que oscila) só para testar a montagem sem internet."""
    n = len(texto.split())
    dur = max(0.6, n / 2.7)
    t = np.arange(int(dur * SR)) / SR
    env = 0.5 * (1 + np.sin(2 * math.pi * 2.7 * t)) ** 0.5
    x = (0.25 * env * np.sin(2 * math.pi * 170 * t) * 32767).astype(np.int16)
    return x


def sintetizar(texto, cfg, cache, modo):
    """-> (amostras int16 mono 44,1 kHz, [(t0,t1)] por palavra)"""
    palavras = texto.split()
    chave = hashlib.sha1(f"{modo}|{cfg['voz']}|{cfg['ritmo']}|{texto}".encode()).hexdigest()[:16]
    wav, js = os.path.join(cache, chave + ".wav"), os.path.join(cache, chave + ".json")
    if os.path.isfile(wav) and os.path.isfile(js):
        return ler_wav(wav), [tuple(p) for p in json.load(open(js))]
    marcas = []
    if modo == "fake":
        x = _fake(texto)
    else:
        mp3 = os.path.join(cache, chave + ".mp3")
        ultimo = None
        for tent in range(3):
            try:
                marcas = asyncio.run(_edge(texto, cfg["voz"], cfg["ritmo"], mp3))
                break
            except Exception as e:
                ultimo = e
                print(f"   edge-tts falhou ({str(e)[:90]}), tentativa {tent + 1}/3", flush=True)
                import time as _t; _t.sleep(2 * (tent + 1))
        else:
            print("   usando gTTS (voz mais simples) como reserva", flush=True)
            _gtts(texto, mp3)
            marcas = []
        tmpw = os.path.join(cache, chave + "_raw.wav")
        sh(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", tmpw])
        x = ler_wav(tmpw)
        os.remove(tmpw)
    x, lead = aparar(x)
    dur = len(x) / SR
    marcas = [(a - lead, b - lead, t) for a, b, t in marcas]
    tempos = alinhar(palavras, marcas, dur) or tempos_proporcionais(palavras, dur)
    tempos = [(max(0.0, min(a, dur)), max(0.0, min(b, dur))) for a, b in tempos]
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(x.tobytes())
    json.dump(tempos, open(js, "w"))
    return x, tempos


# ------------------------------------------------------------------ legenda
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def frases(palavras):
    """palavras: [(txt,t0,t1)] -> grupos de até 3 palavras, quebrando em pontuação."""
    grupos, atual = [], []
    for w in palavras:
        atual.append(w)
        chars = sum(len(x[0]) for x in atual) + len(atual) - 1
        fim = w[0][-1:] in ".!?…"
        meio = w[0][-1:] in ",;:"
        if len(atual) >= 3 or chars >= 18 or fim or (meio and len(atual) >= 2):
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    out = []
    for g in grupos:  # palavra solta (sem fim de frase) gruda na próxima
        if out and len(out[-1]) == 1 and out[-1][0][0][-1:] not in ".!?…" and len(out[-1]) + len(g) <= 4:
            out[-1] = out[-1] + g
        else:
            out.append(g)
    return out


def desenhar_estado(txt_palavras, ativa, cor, caminho):
    """Imagem RGBA 1080x300: palavras brancas com contorno; a ativa em caixa colorida."""
    tam = 84
    while True:
        f = fonte(tam)
        esp = tam * 0.30 + 28
        larg = [f.getlength(p) for p in txt_palavras]
        total = sum(larg) + esp * (len(larg) - 1)
        if total <= 980 or tam <= 56:
            break
        tam -= 2
    linhas = [list(range(len(txt_palavras)))]
    if total > 980 and len(txt_palavras) > 1:  # ainda não coube: duas linhas
        m = (len(txt_palavras) + 1) // 2
        linhas = [list(range(m)), list(range(m, len(txt_palavras)))]
    alt_linha = int(tam * 1.32)
    img = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    sombra = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    caixa = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    ds, dc, dt = ImageDraw.Draw(sombra), ImageDraw.Draw(caixa), ImageDraw.Draw(img)
    cap = -f.getbbox("H", anchor="ls")[1]
    y0 = 150 - (len(linhas) - 1) * alt_linha / 2 + cap / 2
    for li, idxs in enumerate(linhas):
        tot = sum(larg[i] for i in idxs) + esp * (len(idxs) - 1)
        x = (W - tot) / 2
        base = y0 + li * alt_linha
        for i in idxs:
            p = txt_palavras[i]
            if i == ativa:
                dc.rounded_rectangle((x - 16, base - cap - 16, x + larg[i] + 16, base + 18), radius=16,
                                     fill=hex_rgb(cor) + (255,))
                dt.text((x, base), p, font=f, fill=(255, 255, 255, 255), anchor="ls")
                ds.text((x, base + 6), p, font=f, fill=(0, 0, 0, 120), anchor="ls")
            else:
                ds.text((x, base + 6), p, font=f, fill=(0, 0, 0, 170), anchor="ls", stroke_width=7)
                dt.text((x, base), p, font=f, fill=(255, 255, 255, 255), anchor="ls",
                        stroke_width=7, stroke_fill=(0, 0, 0, 255))
            x += larg[i] + esp
    sombra = sombra.filter(ImageFilter.GaussianBlur(5))
    out = Image.alpha_composite(Image.alpha_composite(sombra, caixa), img)
    out.save(caminho)


def montar_legenda(palavras_abs, total, pasta, cor):
    """-> caminho do arquivo de lista (concat) com os quadros de legenda ao longo da parte."""
    os.makedirs(pasta, exist_ok=True)
    branco = os.path.join(pasta, "vazio.png")
    Image.new("RGBA", (W, 300), (0, 0, 0, 0)).save(branco)
    linhas, t = [], 0.0
    grupos = frases(palavras_abs)
    for gi, g in enumerate(grupos):
        ini = g[0][1]
        prox = grupos[gi + 1][0][1] if gi + 1 < len(grupos) else total
        fim_grupo = min(prox, g[-1][2] + 0.35, total)
        if ini > t + 0.02:
            linhas.append((branco, ini - t)); t = ini
        textos = [x[0].upper() for x in g]
        for wi, w in enumerate(g):
            a = max(w[1], t)
            b = g[wi + 1][1] if wi + 1 < len(g) else fim_grupo
            if b - a < 0.04:
                continue
            chave = hashlib.sha1(("|".join(textos) + f"#{wi}").encode()).hexdigest()[:12]
            png = os.path.join(pasta, f"{chave}.png")
            if not os.path.isfile(png):
                desenhar_estado(textos, wi, cor, png)
            if a > t + 0.02:
                linhas.append((branco, a - t))
            linhas.append((png, b - a)); t = b
    if total > t:
        linhas.append((branco, total - t))
    lista = os.path.join(pasta, "legenda.txt")
    with open(lista, "w") as f:
        for p, d in linhas:
            f.write(f"file '{os.path.abspath(p)}'\nduration {max(d, 0.001):.3f}\n")
        f.write(f"file '{os.path.abspath(linhas[-1][0])}'\n")
    return lista


def rotulo_png(texto, caminho):
    img = Image.new("RGBA", (W, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = fonte(44)
    tw = f.getlength(texto)
    d.rounded_rectangle(((W - tw) / 2 - 30, 30, (W + tw) / 2 + 30, 110), radius=40, fill=(0, 0, 0, 120))
    d.text((W / 2, 70), texto, font=f, fill=(255, 255, 255, 255), anchor="mm")
    img.save(caminho)


# ------------------------------------------------------------------ montagem
def clamp(v, a, b):
    return max(a, min(b, v))


def renderizar_parte(parte, idx, total_partes, video, vdur, pw, ph, cfg, trab, saida, modo):
    pid = parte["id"]
    pasta = os.path.join(trab, f"p{pid}")
    shutil.rmtree(pasta, ignore_errors=True)
    os.makedirs(pasta)
    cache = os.path.join(trab, "tts")
    os.makedirs(cache, exist_ok=True)

    falas = list(parte["falas"])
    if cfg["gancho"] and parte.get("gancho") and falas:
        falas.insert(0, {"texto": parte["gancho"], "src_inicio": falas[0]["src_inicio"],
                         "src_fim": falas[0]["src_fim"], "gancho": True})

    # 1) voz + linha do tempo (tudo em quadros inteiros para áudio e vídeo nunca se afastarem)
    audio, palavras_abs, clipes, t = [], [], [], 0.0
    cursor_ini = cursor_fim = -1.0
    for n, fa in enumerate(falas):
        x, tempos = sintetizar(fa["texto"], cfg, cache, modo)
        d = len(x) / SR
        quadros = math.ceil((d + cfg["pausa"]) * FPS)
        L = quadros / FPS
        palavras = fa["texto"].split()
        for w, (a, b) in zip(palavras, tempos):
            palavras_abs.append((w, t + a, t + b))
        pad = np.zeros(int(round(L * SR)) - len(x), dtype=np.int16)
        audio.append(np.concatenate([x, pad]))
        # trecho do vídeo original
        a, b = float(fa["src_inicio"]), float(fa["src_fim"])
        span = max(b - a, 0.5)
        vel = clamp(span / L, 0.9, 1.6)
        ini = a
        if cursor_ini <= ini < cursor_fim:  # não repete o que acabou de passar
            ini = cursor_fim
        gasto = L * vel
        ini = clamp(ini, 0.0, max(0.0, vdur - gasto - 0.1))
        cursor_ini, cursor_fim = ini, ini + gasto
        clipes.append((ini, gasto, vel, L))
        t += L
    total = t
    wav_total = os.path.join(pasta, "locucao.wav")
    with wave.open(wav_total, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(np.concatenate(audio).tobytes())

    # 2) clipes do vídeo original, já no tamanho do painel
    lista = os.path.join(pasta, "clipes.txt")
    with open(lista, "w") as f:
        for k, (ini, gasto, vel, L) in enumerate(clipes):
            c = os.path.join(pasta, f"c{k:02d}.mp4")
            sh(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.3f}", "-t", f"{gasto + 0.2:.3f}", "-i", video,
                "-an", "-vf", f"setpts=PTS/{vel:.4f},scale={pw}:{ph}:flags=lanczos,fps={FPS},setsar=1",
                "-frames:v", str(round(L * FPS)), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                "-pix_fmt", "yuv420p", c])
            f.write(f"file '{os.path.abspath(c)}'\n")
    painel = os.path.join(pasta, "painel.mp4")
    sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", painel])

    # 3) legenda + rótulo
    leg = montar_legenda(palavras_abs, total, os.path.join(pasta, "leg"), cfg["cor_destaque"])
    py = int(cfg["painel_centro"] * H - ph / 2)
    cy = int(cfg["legenda_centro"] * H - 150)
    ent = ["-i", painel, "-i", wav_total, "-f", "concat", "-safe", "0", "-i", leg]
    filtro = [
        "[0:v]split=2[p][b]",
        "[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,gblur=sigma=6,"
        "scale=1080:1920:flags=bicubic,eq=brightness=-0.16:saturation=1.15[bg]",
        f"[bg][p]overlay=(W-w)/2:{py}:shortest=1[v1]",
        f"[2:v]fps={FPS},format=rgba[c]",
        f"[v1][c]overlay=0:{cy}:format=auto:eof_action=pass[v2]",
    ]
    ultimo, prox_in = "v2", 3
    if cfg["rotulo_parte"]:
        rp = os.path.join(pasta, "rotulo.png")
        rotulo_png(f"PARTE {idx}/{total_partes}", rp)
        ent += ["-i", rp]
        filtro.append(f"[{ultimo}][{prox_in}:v]overlay=0:{max(py - 230, 60)}:format=auto[v3]")
        ultimo, prox_in = "v3", prox_in + 1
    filtro.append(f"[{ultimo}]format=yuv420p[vf]")
    musica = cfg.get("musica") and os.path.isfile(cfg["musica"])
    if musica:
        ent += ["-stream_loop", "-1", "-i", cfg["musica"]]
        filtro.append("[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[n]")
        filtro.append(f"[{prox_in}:a]volume={cfg['vol_musica']}[m]")
        filtro.append("[n][m]amix=inputs=2:duration=first:normalize=0[af]")
    else:
        filtro.append("[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100[af]")
    saida_arq = os.path.join(saida, f"parte_{pid}.mp4")
    sh(["ffmpeg", "-y", "-v", "error", *ent, "-filter_complex", ";".join(filtro), "-map", "[vf]", "-map", "[af]",
        "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", saida_arq])
    print(f"RENDERIZADO parte {pid}: {total:.1f}s, {len(falas)} falas, {len(palavras_abs)} palavras", flush=True)
    if total > 90:
        print(f"   AVISO parte {pid} passou de 90 s ({total:.0f}s): divida no roteiro.json ou aumente o ritmo", flush=True)
    return total


def publicacao(rot, partes_ok, saida):
    cred = f"Vídeo original: {rot.get('titulo_original', '')} - {rot.get('canal', '')} - {rot.get('url', '')}".strip(" -")
    linhas = [f"# {rot.get('titulo_serie') or rot.get('titulo_original') or 'Resumo dublado'}\n"]
    if rot.get("descricao"):
        linhas.append(rot["descricao"] + "\n")
    tags = " ".join(rot.get("hashtags") or [])
    for p in partes_ok:
        linhas.append(f"## Parte {p['id']} - {p.get('titulo', '')}\n")
        linhas.append(f"Título: {p.get('titulo', '')}")
        linhas.append(f"Descrição: {p.get('descricao') or p.get('gancho') or ''}\n{cred}\n{tags}\n")
    open(os.path.join(saida, "publicacao.md"), "w", encoding="utf-8").write("\n".join(linhas))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--so", default="")
    ap.add_argument("--tts", default="edge", choices=["edge", "fake"])
    ap.add_argument("--voz", default="")
    ap.add_argument("--ritmo", default="")
    ap.add_argument("--saida", default="")
    a = ap.parse_args()

    rot = json.load(open(os.path.join("jobs", a.job, "roteiro.json"), encoding="utf-8"))
    cfg = {**PADRAO, **(rot.get("config") or {})}
    if a.voz:
        cfg["voz"] = a.voz
    if a.ritmo:
        cfg["ritmo"] = a.ritmo
    saida = a.saida or os.path.join("saida", a.job)
    os.makedirs(saida, exist_ok=True)
    trab = os.path.join("tmp", "dub", a.job)
    os.makedirs(trab, exist_ok=True)

    vw, vh = int(probe(a.video, "width")), int(probe(a.video, "height"))
    vdur = duracao_arquivo(a.video)
    if vw / vh >= 1.2:
        pw, ph = 1080, int(round(1080 * vh / vw / 2) * 2)
    else:
        ph, pw = 1100, int(round(1100 * vw / vh / 2) * 2)
    print(f"fonte {vw}x{vh} {vdur / 60:.1f} min -> painel {pw}x{ph}", flush=True)

    so = {x.strip() for x in a.so.split(",") if x.strip()}
    partes = rot["partes"]
    ok = []
    for i, p in enumerate(partes, 1):
        if so and p["id"] not in so:
            continue
        try:
            renderizar_parte(p, i, len(partes), a.video, vdur, pw, ph, cfg, trab, saida, a.tts)
            ok.append(p)
        except Exception as e:
            print(f"ERRO_DUB parte {p['id']}: {e}", flush=True)
    publicacao(rot, [p for p in partes if so == set() or p["id"] in so], saida)
    if not ok:
        sys.exit("ERRO_DUB nenhuma parte foi renderizada")


if __name__ == "__main__":
    main()
