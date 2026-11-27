#!/usr/bin/env python3
"""
Transforma a transcrição do vídeo original em ROTEIRO dublado: resume, reescreve em português do Brasil
falado e divide em partes para vídeos curtos. De graça:
  - GitHub Models (padrão no Actions: usa o GITHUB_TOKEN, permissão `models: read`), ou
  - Gemini (se existir o segredo GEMINI_API_KEY; cota grátis maior).

  dub_roteiro.py --job J [--partes 0] [--alvo 60] [--resumo 0.35] [--llm auto|github|gemini] [--modelo-llm ...]

Lê   jobs/J/fonte_transcricao.json  e  jobs/J/meta.json
Grava jobs/J/roteiro.json   (pode ser editado à mão depois; ver DUBLAR.md)
"""
import argparse, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request

WPS = 2.6  # palavras por segundo da voz (estimativa; o áudio real manda na hora de renderizar)
MAX_PARTE = 85.0

SISTEMA = ("Você é roteirista de vídeos curtos verticais (Shorts, Reels, TikTok) e escreve em português do Brasil "
           "falado: natural, direto e com energia, como um bom narrador de canal de games. "
           "Responda SEMPRE e SOMENTE com JSON válido, sem texto antes ou depois.")


# ------------------------------------------------------------------ LLM
class _Redir(urllib.request.HTTPRedirectHandler):
    """Segue redirecionamentos mantendo POST + corpo (como `curl -L`); não manda o token para outro domínio."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        cab = dict(req.header_items())
        if urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            cab = {k: v for k, v in cab.items() if k.lower() not in ("authorization", "x-goog-api-key")}
        return urllib.request.Request(newurl, data=req.data, headers=cab, method=req.get_method())


_abrir = urllib.request.build_opener(_Redir).open


GEMINI_BASE = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")


def http_get_json(url, cab, tentativas=3):
    ultimo = ""
    for t in range(tentativas):
        try:
            with _abrir(urllib.request.Request(url, headers=cab), timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}"
            if e.code < 500 and e.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            ultimo = str(e)
        time.sleep(3 * (t + 1))
    raise RuntimeError(ultimo)


def http_json(url, corpo, cab, tentativas=6):
    dados = json.dumps(corpo).encode()
    ultimo, nao_json = "", 0
    for t in range(tentativas):
        req = urllib.request.Request(url, data=dados, headers=cab, method="POST")
        try:
            with _abrir(req, timeout=180) as r:
                bruto = r.read()
                try:
                    return json.loads(bruto)
                except ValueError:
                    ultimo = f"resposta que não é JSON (status {r.status}, de {r.geturl()}): {bruto[:300]!r}"
                    print("   " + ultimo, flush=True)
                    nao_json += 1
                    if nao_json >= 2:
                        break
                    time.sleep(6)
                    continue
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}"
            if e.code == 429 and re.search(r"per ?day|PerDay|daily", ultimo, re.I):
                raise RuntimeError(ultimo)  # cota do dia acabou: esperar não adianta
            if e.code in (429, 500, 502, 503, 504):
                espera = min(90.0, float(e.headers.get("Retry-After") or 0) or 10.0 * (t + 1))
                print(f"   LLM {e.code}, esperando {espera:.0f}s (tentativa {t + 1}/{tentativas})", flush=True)
                time.sleep(espera)
                continue
            raise RuntimeError(ultimo)
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = str(e)
            time.sleep(5 * (t + 1))
    raise RuntimeError("LLM indisponível: " + ultimo)


def modelos_gemini(chave, preferido=""):
    """Modelos 'flash' de texto que a SUA chave enxerga, do mais novo ao mais antigo (flash antes de flash-lite)."""
    achados = []
    try:
        r = http_get_json(f"{GEMINI_BASE}/models?pageSize=200", {"x-goog-api-key": chave})
        for m in r.get("models", []):
            nome = m.get("name", "").split("/")[-1]
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            mm = re.fullmatch(r"gemini-(\d+(?:\.\d+)*)-flash(-lite)?", nome)
            if mm:
                achados.append((bool(mm.group(2)), [-int(x) for x in mm.group(1).split(".")], nome))
    except RuntimeError as e:
        if "API key not valid" in str(e) or "API_KEY_INVALID" in str(e):
            sys.exit("ERRO_ROTEIRO a GEMINI_API_KEY não é válida: copie a chave de novo em aistudio.google.com e atualize o segredo")
        print(f"   não consegui listar os modelos do Gemini ({str(e)[:140]})", flush=True)
    achados.sort(key=lambda x: (x[0], x[1]))
    lista = [n for _, _, n in achados]
    reserva = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.0-flash"]
    out = []
    for m in ([preferido] if preferido else []) + lista + reserva:
        if m and m not in out:
            out.append(m)
    return out


class LLM:
    def __init__(self, provedor, modelo):
        gem = os.environ.get("GEMINI_API_KEY", "")
        if provedor == "auto":
            provedor = "gemini" if gem else "github"
        self.provedor = provedor
        if provedor == "gemini":
            if not gem:
                sys.exit("ERRO_ROTEIRO falta o segredo GEMINI_API_KEY")
            self.candidatos = modelos_gemini(gem, modelo)
            self.idx = 0
            self.modelo = self.candidatos[0]
            print("   modelos Gemini disponíveis (ordem de tentativa):", ", ".join(self.candidatos[:5]), flush=True)
        else:
            if not os.environ.get("GITHUB_TOKEN"):
                sys.exit("ERRO_ROTEIRO falta GITHUB_TOKEN (e a permissão `models: read` no workflow)")
            self.modelo = modelo or "openai/gpt-4.1-mini"
            self.reservas = [m for m in ("openai/gpt-4o-mini", "openai/gpt-4.1") if m != self.modelo]
        self.json_mode = True
        print(f"LLM: {self.provedor} / {self.modelo}", flush=True)

    def json(self, usuario, max_saida=3500):
        for tentativa in range(3):
            txt = self._chamar(usuario if tentativa == 0 else
                               usuario + "\n\nIMPORTANTE: devolva apenas o JSON, sem comentários nem ``` .", max_saida)
            try:
                return extrair_json(txt)
            except Exception:
                print("   resposta não era JSON válido, tentando de novo", flush=True)
        raise RuntimeError("o modelo não devolveu JSON válido")

    def _chamar(self, usuario, max_saida):
        if self.provedor == "gemini":
            cab = {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]}
            corpo = {"systemInstruction": {"parts": [{"text": SISTEMA}]},
                     "contents": [{"role": "user", "parts": [{"text": usuario}]}],
                     "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json",
                                          "maxOutputTokens": max_saida + 4000}}
            while True:
                try:
                    r = http_json(f"{GEMINI_BASE}/models/{self.modelo}:generateContent", corpo, cab)
                    if not r.get("candidates"):
                        raise RuntimeError("Gemini sem resposta: " + json.dumps(r, ensure_ascii=False)[:300])
                    txt = "".join(p.get("text", "") for p in r["candidates"][0].get("content", {}).get("parts", []))
                    if not txt.strip():
                        raise RuntimeError("Gemini devolveu texto vazio")
                    time.sleep(13)  # o plano grátis aceita poucos pedidos por minuto (~5 nos modelos flash)
                    return txt
                except RuntimeError as e:
                    if "API key not valid" in str(e) or "API_KEY_INVALID" in str(e):
                        sys.exit("ERRO_ROTEIRO a GEMINI_API_KEY não é válida: gere outra em aistudio.google.com e atualize o segredo")
                    if self.idx + 1 >= len(self.candidatos):
                        raise RuntimeError(f"{e}\n   Nenhum modelo Gemini funcionou. Veja os limites da sua chave em "
                                           "aistudio.google.com (Rate limits) ou tente de novo mais tarde.")
                    print(f"   modelo {self.modelo} falhou ({str(e)[:180]}); tentando {self.candidatos[self.idx + 1]}", flush=True)
                    self.idx += 1
                    self.modelo = self.candidatos[self.idx]
        corpo = {"model": self.modelo, "temperature": 0.4, "max_tokens": max_saida,
                 "messages": [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]}
        if self.json_mode:
            corpo["response_format"] = {"type": "json_object"}
        cab = {"Content-Type": "application/json", "Accept": "application/vnd.github+json",
               "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "X-GitHub-Api-Version": "2022-11-28"}
        try:
            r = http_json("https://models.github.ai/inference/chat/completions", corpo, cab)
            if "choices" not in r:
                raise RuntimeError("resposta sem 'choices': " + json.dumps(r, ensure_ascii=False)[:300])
        except RuntimeError as e:
            if self.reservas and "429" not in str(e) and "RateLimit" not in str(e):
                print(f"   modelo {self.modelo} falhou ({str(e)[:160]}); tentando {self.reservas[0]}", flush=True)
                self.modelo = self.reservas.pop(0)
                return self._chamar(usuario, max_saida)
            if self.json_mode and "response_format" in str(e):
                self.json_mode = False
                return self._chamar(usuario, max_saida)
            if "429" in str(e) or "RateLimit" in str(e):
                raise RuntimeError(str(e) + "\n   Acabou a cota grátis do GitHub Models por hoje. Opções: tentar amanhã, "
                                   "criar o segredo GEMINI_API_KEY (grátis) ou pedir ao Claude para escrever o roteiro.json.")
            raise
        time.sleep(4)  # respeita o limite de pedidos por minuto da cota grátis
        return r["choices"][0]["message"]["content"]


def extrair_json(txt):
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip(), flags=re.M).strip()
    i, j = txt.find("{"), txt.rfind("}")
    return json.loads(txt[i:j + 1])


# ------------------------------------------------------------------ etapas
def palavras(s):
    return len(s.split())


def janelas(trechos, max_s=240.0, max_pal=650):
    out, atual, pal = [], [], 0
    for t in trechos:
        if atual and (t["end"] - atual[0]["start"] > max_s or pal + palavras(t["text"]) > max_pal):
            out.append(atual); atual, pal = [], 0
        atual.append(t); pal += palavras(t["text"])
    if atual:
        out.append(atual)
    return out


def falas_da_janela(llm, meta, idioma, jan, razao, vocab):
    w0, w1 = jan[0]["start"], jan[-1]["end"]
    pal = sum(palavras(t["text"]) for t in jan)
    orc = max(25, round(pal * razao))
    corpo = "\n".join(f"[{t['start']:.1f}-{t['end']:.1f}] {t['text']}" for t in jan)
    prompt = f"""Vídeo: "{meta.get('titulo', '')}" (canal {meta.get('canal', '')}). Nomes e termos do assunto: {vocab}.
Abaixo, um trecho da transcrição original (idioma: {idioma}) com o tempo, em segundos, de cada trecho no vídeo original.

TAREFA: resuma este trecho em falas de narração em português do Brasil.
- No total, cerca de {orc} palavras (entre {int(orc * 0.8)} e {int(orc * 1.2)}). Corte enrolação, repetição, pedido de like/inscrição, patrocínio e tudo que não ajuda quem assiste.
- Cada fala: UMA frase de no máximo 22 palavras, feita para ser FALADA (sem parênteses, sem emoji, sem listas). Números e valores como se fala ("cinco mil dólares").
- Não traduza palavra por palavra: reconte as ideias, na ordem do vídeo, mantendo nomes, valores, lugares e passos corretos. Não invente nada que não esteja no trecho.
- Para cada fala, informe src_inicio e src_fim: o intervalo (segundos, usando os tempos abaixo) do vídeo original que ela resume. As imagens desse intervalo vão aparecer enquanto a fala é dita.

Responda: {{"falas":[{{"texto":"...","src_inicio":0.0,"src_fim":0.0}}]}}

TRANSCRIÇÃO:
{corpo}"""
    r = llm.json(prompt)
    out = []
    for f in r.get("falas", []):
        try:
            txt = " ".join(str(f["texto"]).split())
            a, b = float(f["src_inicio"]), float(f["src_fim"])
        except (KeyError, TypeError, ValueError):
            continue
        if not txt:
            continue
        a = min(max(a, w0), w1)
        b = min(max(b, a + 1.0), w1 + 4.0)
        out.append({"texto": txt, "src_inicio": round(a, 2), "src_fim": round(b, 2)})
    if not out:
        raise RuntimeError(f"nenhuma fala válida na janela {w0:.0f}-{w1:.0f}s")
    return out


def estimar(falas):
    return sum(palavras(f["texto"]) / WPS + 0.25 for f in falas)


def dividir_por_tempo(falas, alvo, n=0):
    """Reserva sem IA / ajuste: fatias sequenciais de ~alvo segundos (ou exatamente n fatias)."""
    n = n or max(1, round(estimar(falas) / alvo))
    por = estimar(falas) / n
    grupos, atual, t = [], [], 0.0
    for f in falas:
        atual.append(f); t += palavras(f["texto"]) / WPS + 0.25
        if t >= por and len(grupos) < n - 1:
            grupos.append(atual); atual, t = [], 0.0
    if atual:
        grupos.append(atual)
    return grupos


def estruturar(llm, falas, meta, n_partes, alvo):
    lista = "\n".join(f"{i} | {palavras(f['texto'])} palavras | {f['texto']}" for i, f in enumerate(falas))
    quer = (f"Faça EXATAMENTE {n_partes} partes." if n_partes else
            f"Cada parte deve durar uns {int(alvo)} s (entre {int(alvo * 0.5)} e {int(MAX_PARTE)} s).")
    prompt = f"""Estas são, em ordem, as falas da narração de um vídeo ("{meta.get('titulo', '')}").
Divida em PARTES, cada uma um vídeo curto independente. {quer}
Estimativa da duração de uma parte = (soma das palavras / {WPS}) + 0,25 s por fala.
Corte sempre onde muda o assunto, método ou etapa (se o vídeo é uma lista "N formas de...", prefira uma parte por item).
Para cada parte: titulo (até 60 caracteres, chamativo e honesto), gancho (frase de abertura de até 12 palavras, que prende sem mentir), descricao (1 frase).
Também: titulo_serie, descricao (2 linhas) e hashtags (6 a 8, com #).
"de" e "ate" são os índices (inclusivos) das falas; as partes devem cobrir todas as falas, em ordem, sem sobrepor.

Responda: {{"titulo_serie":"","descricao":"","hashtags":[],"partes":[{{"de":0,"ate":0,"titulo":"","gancho":"","descricao":""}}]}}

FALAS:
{lista}"""
    return llm.json(prompt, 2500)


def montar_partes(falas, est, alvo):
    """Valida o que a IA devolveu; se algo estiver torto, cai para a divisão por tempo."""
    cortes = []
    try:
        prox = 0
        for p in sorted(est.get("partes", []), key=lambda p: int(p["de"])):
            de, ate = int(p["de"]), int(p["ate"])
            if de != prox or ate < de or ate >= len(falas):
                raise ValueError("faixas não contínuas")
            cortes.append((falas[de:ate + 1], p))
            prox = ate + 1
        if prox != len(falas):
            raise ValueError("faltaram falas")
    except (KeyError, TypeError, ValueError) as e:
        print(f"   divisão da IA descartada ({e}); dividindo por tempo", flush=True)
        cortes = [(g, {}) for g in dividir_por_tempo(falas, alvo)]
    # parte longa demais -> divide; parte curta demais -> junta com a anterior
    saida = []
    for g, p in cortes:
        if estimar(g) > MAX_PARTE:
            subs = dividir_por_tempo(g, alvo, n=math.ceil(estimar(g) / (MAX_PARTE * 0.9)))
            for k, s in enumerate(subs):
                q = dict(p) if k == 0 else {"titulo": f"{p.get('titulo', '')} (continuação)".strip(), "descricao": p.get("descricao", "")}
                saida.append((s, q))
        else:
            saida.append((g, p))
    final = []
    for g, p in saida:
        if final and estimar(g) < 18 and estimar(final[-1][0]) + estimar(g) <= MAX_PARTE:
            final[-1] = (final[-1][0] + g, final[-1][1])
        else:
            final.append((g, p))
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--partes", type=int, default=0, help="número de partes (0 = automático)")
    ap.add_argument("--alvo", type=float, default=60.0, help="duração alvo de cada parte, em segundos")
    ap.add_argument("--resumo", type=float, default=0.35, help="fração das palavras do original que sobra (0.15-0.7)")
    ap.add_argument("--llm", default="auto", choices=["auto", "github", "gemini"])
    ap.add_argument("--modelo-llm", default="")
    a = ap.parse_args()

    pasta = os.path.join("jobs", a.job)
    tr = json.load(open(os.path.join(pasta, "fonte_transcricao.json"), encoding="utf-8"))
    meta = json.load(open(os.path.join(pasta, "meta.json"), encoding="utf-8")) if os.path.isfile(os.path.join(pasta, "meta.json")) else {}
    trechos = tr["trechos"]
    pal_total = sum(palavras(t["text"]) for t in trechos)
    razao = a.resumo
    if a.partes:
        razao = min(0.7, max(0.12, a.partes * a.alvo * WPS / max(pal_total, 1)))
    print(f"fonte: {pal_total} palavras, resumo para ~{razao:.0%}", flush=True)

    llm = LLM(a.llm, a.modelo_llm)
    vocab = f"{meta.get('titulo', '')}, {meta.get('canal', '')}"
    falas = []
    for k, jan in enumerate(janelas(trechos), 1):
        print(f"   janela {k}: {jan[0]['start'] / 60:.1f}-{jan[-1]['end'] / 60:.1f} min", flush=True)
        falas += falas_da_janela(llm, meta, tr.get("idioma", "en"), jan, razao, vocab)
    print(f"{len(falas)} falas, ~{estimar(falas):.0f}s de locução", flush=True)

    try:
        est = estruturar(llm, falas, meta, a.partes, a.alvo)
    except Exception as e:
        print(f"   estruturação falhou ({str(e)[:120]}); dividindo por tempo", flush=True)
        est = {}
    partes = montar_partes(falas, est, a.alvo)

    roteiro = {"titulo_original": meta.get("titulo", ""), "canal": meta.get("canal", ""), "url": meta.get("url", ""),
               "titulo_serie": est.get("titulo_serie") or meta.get("titulo", ""),
               "descricao": est.get("descricao", ""), "hashtags": est.get("hashtags") or [],
               "config": {}, "partes": []}
    for i, (g, p) in enumerate(partes, 1):
        roteiro["partes"].append({"id": f"{i:02d}", "titulo": p.get("titulo") or f"Parte {i}",
                                  "gancho": p.get("gancho", ""), "descricao": p.get("descricao", ""), "falas": g})
    with open(os.path.join(pasta, "roteiro.json"), "w", encoding="utf-8") as f:
        json.dump(roteiro, f, ensure_ascii=False, indent=1)
    for p in roteiro["partes"]:
        print(f"ROTEIRO parte {p['id']}: ~{estimar(p['falas']):.0f}s, {len(p['falas'])} falas - {p['titulo']}", flush=True)


if __name__ == "__main__":
    main()
