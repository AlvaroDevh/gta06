#!/usr/bin/env python3
"""
Efeitos sonoros estilo TikTok/Shorts, GERADOS POR CÓDIGO (sem direitos autorais, sem baixar nada):
whoosh (transição), pop, ding, coin (grana), boom (impacto), riser (tensão).

Para usar um som seu no lugar de qualquer um, coloque na pasta  efeitos/  um arquivo com o mesmo nome
(ex.: efeitos/whoosh.mp3, efeitos/boom.wav). Só use sons livres de direitos.

  python scripts/dub_sfx.py            -> grava amostras de todos os efeitos em tmp/sfx_amostras/
"""
import os, re, subprocess, sys, wave

import numpy as np

SR = 44100
RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def _norm(y, pico=0.9):
    m = float(np.max(np.abs(y))) or 1.0
    return (y / m * pico).astype(np.float32)


def _passa_baixa(x, coef):
    """filtro de um polo com coeficiente variável no tempo (coef pequeno = som abafado)."""
    y = np.empty(len(x), dtype=np.float64)
    acc = 0.0
    for i in range(len(x)):
        acc += coef[i] * (x[i] - acc)
        y[i] = acc
    return y


def whoosh(dur=0.5):
    n = int(dur * SR)
    tt = np.linspace(0, 1, n)
    ruido = np.random.default_rng(7).standard_normal(n)
    y = _passa_baixa(ruido, 0.02 + 0.5 * tt ** 2)          # abafado -> brilhante
    y = y - np.convolve(y, np.ones(160) / 160, mode="same")  # tira o grave
    return _norm(y * np.sin(np.pi * tt ** 0.8) ** 2)


def pop(dur=0.14):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = np.linspace(950, 320, n)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38)
    return _norm(y)


def ding(dur=0.9):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = sum(a * np.sin(2 * np.pi * 1568 * k * t) * np.exp(-t * d)
            for k, a, d in ((1, 1.0, 4.5), (2, 0.45, 7.0), (3, 0.2, 10.0)))
    y *= np.minimum(1, t / 0.003)
    return _norm(y)


def coin(dur=0.55):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for ini, f, d in ((0.0, 1319, 14.0), (0.075, 1976, 6.0)):
        k = t >= ini
        tt = (t - ini) * k
        y += k * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 3 * f * tt)) * np.exp(-tt * d)
    return _norm(y)


def boom(dur=1.1):
    """impacto: começa em ~230 Hz e cai até ~70 Hz (celular não reproduz grave abaixo de ~150 Hz,
    então o 'soco' precisa ter médio para ser ouvido); camada de ruído abafado dá o corpo."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 70 + 170 * np.exp(-t * 15)
    base = np.sin(2 * np.pi * np.cumsum(f) / SR)
    y = (base + 0.5 * np.sin(2 * np.pi * np.cumsum(f * 2) / SR)) * np.exp(-t * 3.6)
    ruido = _passa_baixa(np.random.default_rng(3).standard_normal(n), np.full(n, 0.12)) * np.exp(-t * 11) * 3
    return _norm(np.tanh((y + ruido * 0.6) * 1.6))


def riser(dur=1.3):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tt = t / dur
    ruido = _passa_baixa(np.random.default_rng(11).standard_normal(n), 0.01 + 0.6 * tt ** 2)
    f = 220 * (8 ** tt)
    y = 0.6 * ruido + 0.4 * np.sin(2 * np.pi * np.cumsum(f) / SR)
    return _norm(y * (tt ** 1.6) * np.minimum(1, (dur - t) / 0.02))


GERADORES = {"whoosh": whoosh, "pop": pop, "ding": ding, "coin": coin, "boom": boom, "riser": riser}


def _carregar_arquivo(caminho):
    """decodifica qualquer áudio (mp3/wav/ogg/m4a) para mono 44,1 kHz."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", caminho, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    return _norm(np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32))


def carregar_efeitos(pasta=None):
    pasta = pasta or os.path.join(RAIZ, "efeitos")
    out = {}
    for nome, gera in GERADORES.items():
        y = None
        for ext in ("wav", "mp3", "ogg", "m4a"):
            arq = os.path.join(pasta, f"{nome}.{ext}")
            if os.path.isfile(arq):
                y = _carregar_arquivo(arq)
                if y is not None:
                    print(f"   efeito '{nome}': usando seu arquivo {os.path.basename(arq)}", flush=True)
                    break
        out[nome] = y if y is not None else gera()
    return out


DINHEIRO = ("dinheiro", "grana", "milh", "bilh", "dolar", "dólar", "real", "reais", "lucr", "rico", "ouro", "pagament")
REGANCHO = re.compile(r"^(mas calma|agora vem|e aqui|tem mais|olha s[oó]|presta aten|e o melhor|aqui t[aá])", re.I)


def planejar(inicios, falas, palavras_abs, total, nivel):
    """-> lista de (tempo_s, nome, ganho). inicios[i] = instante em que a fala i começa."""
    if nivel == "off":
        return []
    ev = []
    ev.append((0.0, "boom" if nivel != "leve" else "pop", 0.55 if nivel != "leve" else 0.35))
    ultimo_whoosh, ultimo_riser, ultimo_ding = -99.0, -99.0, -99.0
    folga = {"leve": 99.0, "medio": 5.5, "forte": 3.2}.get(nivel, 5.5)
    for i, t in enumerate(inicios):
        if i == 0:
            continue
        if REGANCHO.match(falas[i]["texto"].strip()) and t - ultimo_riser > 20 and t > 6:
            ev.append((max(0.0, t - 1.1), "riser", 0.30)); ultimo_riser = t
            ev.append((t, "boom", 0.35))
            ultimo_whoosh = t
        elif t - ultimo_whoosh >= folga and total - t > 2.0:
            ev.append((max(0.0, t - 0.10), "whoosh", 0.30)); ultimo_whoosh = t
    for w, t0, _ in palavras_abs:
        nw = re.sub(r"\W+", "", w.lower())
        if t0 - ultimo_ding < 7.0 or t0 < 2.5 or total - t0 < 3.0:
            continue
        if any(nw.startswith(k) for k in DINHEIRO) or (any(c.isdigit() for c in nw) and nivel != "leve"):
            ev.append((t0, "coin" if any(nw.startswith(k) for k in DINHEIRO) else "ding", 0.30)); ultimo_ding = t0
    ev.append((max(0.0, total - 0.45), "pop", 0.40))
    return sorted(ev)


def mixar(eventos, efeitos, total, saida_wav):
    n = int((total + 1.0) * SR)
    mix = np.zeros(n, dtype=np.float32)
    for t, nome, ganho in eventos:
        y = efeitos[nome] * ganho
        i = int(t * SR)
        if i >= n:
            continue
        j = min(n, i + len(y))
        mix[i:j] += y[: j - i]
    mix = np.clip(mix, -1.0, 1.0)
    with wave.open(saida_wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return saida_wav


if __name__ == "__main__":
    pasta = os.path.join(RAIZ, "tmp", "sfx_amostras")
    os.makedirs(pasta, exist_ok=True)
    for nome, y in carregar_efeitos().items():
        with wave.open(os.path.join(pasta, nome + ".wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((y * 32767).astype(np.int16).tobytes())
        print(f"{nome}: {len(y) / SR:.2f}s -> {pasta}/{nome}.wav")
