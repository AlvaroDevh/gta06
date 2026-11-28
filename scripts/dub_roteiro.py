#!/usr/bin/env python3
"""
Transforma a transcrição do vídeo original em ROTEIRO dublado e otimizado para Shorts/TikTok/Reels:
  1) resume cada trecho em português do Brasil falado, com linguagem de gamer;
  2) divide em partes INDEPENDENTES (cada uma com começo, meio e fim), com tamanho mínimo/máximo;
  3) lapida cada parte com gancho, re-ganchos, fechamento e CTA (SEO + retenção) e escreve título,
     descrição, hashtags e comentário fixado.
De graça: GitHub Models (usa o GITHUB_TOKEN) ou Gemini (segredo GEMINI_API_KEY).

  dub_roteiro.py --job J [--partes 0] [--alvo 75] [--min-parte 65] [--max-parte 110] [--giria media]
                 [--resumo 0.35] [--llm auto|github|gemini] [--modelo-llm ...]

Lê   jobs/J/fonte_transcricao.json  e  jobs/J/meta.json
Grava jobs/J/roteiro.json   (pode ser editado à mão depois; ver DUBLAR.md)
"""
import argparse, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request

P = {"wps": 2.7, "alvo": 75.0, "min": 65.0, "max": 110.0, "giria": "media"}

SISTEMA = ("Você é roteirista de vídeos curtos verticais (Shorts, TikTok, Reels) para o público gamer brasileiro. "
           "Escreve em português do Brasil FALADO: natural, direto, com energia, como um criador de canal de games. "
           "Responda SEMPRE e SOMENTE com JSON válido, sem texto antes ou depois.")

GIRIA = {
    "leve": "Fale simples e direto, como numa conversa. Use gíria só de vez em quando (1 a cada 4 frases), sem forçar.",
    "media": "Fale como gamer brasileiro de verdade: frases curtas, gírias naturais (mano, tipo, bizarro, absurdo, bora, "
             "olha só, simples assim, se liga) em cerca de 1 a cada 2 ou 3 frases. Termos de jogo quando cabem "
             "(farmar, loot, grana, meta, bugado, nerfar, buffar).",
    "alta": "Fale solto, bem de gamer: gírias e expressões em quase toda frase, energia alta, exclamações. "
            "Nunca use palavrão e nada ofensivo.",
}

# Guia de roteiro (resumo do que presta no PDF + pesquisa de SEO/retenção; ver GUIA_ROTEIRO.md)
PLAYBOOK = """REGRAS DO ROTEIRO (siga todas):
1. GANCHO (primeira fala, até 3 segundos, no máximo 12 palavras): entra direto, sem "fala galera" nem "bem-vindos".
   Já cita o assunto principal (a palavra-chave que a pessoa buscaria) e promete algo que o vídeo REALMENTE entrega.
   Tipos que funcionam: curiosidade/segredo, afirmação forte, pergunta, número ("3 jeitos de..."), erro comum,
   comparação, urgência sem mentir. Nada de clickbait falso e nada de dizer "confirmado/vazou" se o vídeo não confirma.
2. PROMESSA/LOOP: logo depois do gancho, deixe claro o que vem ("o último é o que mais dá grana") para a pessoa ficar.
3. RITMO: frases curtas (até 18 palavras), uma ideia por frase. A cada 15 a 20 segundos um re-gancho
   ("mas calma, tem mais", "agora vem a parte boa", "e aqui está o pulo do gato").
4. CONTEÚDO: passos concretos, números e nomes corretos do vídeo original. Nunca invente fatos. Se for rumor ou
   hipótese, diga que é rumor ou hipótese.
5. VALOR PRÓPRIO: perto do fim, 1 ou 2 frases de veredito/opinião ("na minha visão...", "o que isso muda pra você é...")
   baseadas só no que o vídeo mostrou. Isso é o toque do canal, não pode faltar.
6. FECHAMENTO: entrega o resultado, termina a ideia (começo, meio e fim) e faz UM pedido que gera comentário, salvamento
   ou seguidor ("qual você testaria? comenta aí", "salva pra quando precisar"). NUNCA mande a pessoa ver o vídeo
   completo, ir para outro canal ou clicar em link. Se der, a última frase ecoa o gancho para estimular rever.
7. INDEPENDENTE: quem vê só esta parte entende tudo. Abra com contexto em uma frase. Proibido: "como vimos", "na parte
   anterior", "continuando", "voltando", "como eu falei", "no vídeo passado" (a não ser que seja uma série marcada).
8. PROIBIDO: palavrão, ofensa, texto formal/rebuscado ("outrossim", "conforme supracitado"), listas e parênteses na fala,
   emojis na fala. Números como se fala ("cinco mil dólares")."""

PROIBIDAS = re.compile(r"\b(como (vimos|falei|mencionei|disse)|na parte anterior|parte anterior|continuando|"
                       r"voltando (ao|a|para)|no v[ií]deo (anterior|passado)|como eu (disse|falei)|conforme (visto|dito))\b", re.I)
FORA = re.compile(r"(v[ií]deo completo|link na descri[cç][aã]o|canal principal|link na bio)", re.I)

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


def estimar(falas):
    return sum(palavras(f["texto"]) / P["wps"] + 0.25 for f in falas)


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
- ESTILO: {GIRIA[P['giria']]}
- No total, cerca de {orc} palavras (entre {int(orc * 0.8)} e {int(orc * 1.2)}). Corte enrolação, repetição, pedido de like/inscrição, patrocínio e tudo que não ajuda quem assiste.
- Cada fala: UMA frase de no máximo 20 palavras, feita para ser FALADA (sem parênteses, sem emoji, sem listas). Números e valores como se fala ("cinco mil dólares").
- Não traduza palavra por palavra: reconte as ideias, na ordem do vídeo, mantendo nomes, valores, lugares e passos corretos. Não invente nada que não esteja no trecho.
- Cada fala deve fazer sentido sozinha (sem "isso", "ele" soltos que dependam de uma frase muito anterior).
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


def dividir_por_tempo(falas, alvo, n=0):
    """Reserva sem IA / ajuste: fatias sequenciais de ~alvo segundos (ou exatamente n fatias)."""
    n = n or max(1, round(estimar(falas) / alvo))
    por = estimar(falas) / n
    grupos, atual, t = [], [], 0.0
    for f in falas:
        atual.append(f); t += palavras(f["texto"]) / P["wps"] + 0.25
        if t >= por and len(grupos) < n - 1:
            grupos.append(atual); atual, t = [], 0.0
    if atual:
        grupos.append(atual)
    return grupos


def estruturar(llm, falas, meta, n_partes):
    lista = "\n".join(f"{i} | {palavras(f['texto'])} palavras | {f['texto']}" for i, f in enumerate(falas))
    quer = f"Faça EXATAMENTE {n_partes} partes." if n_partes else "Faça quantas partes o conteúdo pedir."
    prompt = f"""Estas são, em ordem, as falas da narração de um vídeo ("{meta.get('titulo', '')}").
Divida em PARTES. Cada parte vira um vídeo curto INDEPENDENTE: quem assistir só uma parte precisa entender tudo e sentir começo, meio e fim.
{quer}
REGRAS:
- Corte por TEMA FECHADO (um método, uma dica, uma etapa, uma polêmica). Nunca corte no meio de uma explicação nem entregue uma parte que seja só "continuação" de outra.
- Duração de cada parte: ideal {int(P['alvo'])} s, mínimo {int(P['min'])} s, máximo {int(P['max'])} s. Estimativa = (soma das palavras / {P['wps']}) + 0,25 s por fala.
- Se UM tema fechado não cabe no máximo, divida esse tema em 2 partes e marque nelas "serie":{{"n":1,"de":2}} e "serie":{{"n":2,"de":2}}. Só nesse caso uma parte pode depender da outra.
- Falas que não ajudam (apresentação do canal, pedido de like, patrocínio, enrolação) podem ficar de fora: não precisam estar em nenhuma parte. As partes não podem se sobrepor.
- Para cada parte: titulo_tema (o tema em poucas palavras).
- Também: titulo_serie (título geral do vídeo original, em português) e hashtags_gerais.
"de" e "ate" são os índices (inclusivos) das falas.

Responda: {{"titulo_serie":"","hashtags_gerais":[],"partes":[{{"de":0,"ate":0,"titulo_tema":"","serie":null}}]}}

FALAS:
{lista}"""
    return llm.json(prompt, 2500)


def montar_partes(falas, est, alvo):
    """Valida o que a IA devolveu; se algo estiver torto, cai para a divisão por tempo."""
    cortes = []
    try:
        ult = -1
        for p in sorted(est.get("partes", []), key=lambda p: int(p["de"])):
            de, ate = int(p["de"]), int(p["ate"])
            if de <= ult or ate < de or ate >= len(falas):
                raise ValueError("faixas inválidas ou sobrepostas")
            cortes.append((falas[de:ate + 1], p))
            ult = ate
        if not cortes:
            raise ValueError("sem partes")
    except (KeyError, TypeError, ValueError) as e:
        print(f"   divisão da IA descartada ({e}); dividindo por tempo", flush=True)
        cortes = [(g, {}) for g in dividir_por_tempo(falas, alvo)]
    saida = []
    for g, p in cortes:  # parte longa demais -> divide em partes de uma série
        if estimar(g) > P["max"] * 1.35 and not p.get("serie"):  # tema grande de verdade (a lapidação já comprime o resto)
            n = math.ceil(estimar(g) / (P["alvo"] * 1.3))
            for k, s in enumerate(dividir_por_tempo(g, alvo, n=n), 1):
                saida.append((s, {**p, "serie": {"n": k, "de": n}}))
        else:
            saida.append((g, p))
    final = []
    for g, p in saida:  # parte curta demais -> junta com a anterior, se couber (nunca junta série)
        if (final and estimar(g) < P["min"] and not p.get("serie") and not final[-1][1].get("serie")
                and estimar(final[-1][0]) + estimar(g) <= P["max"]):
            final[-1] = (final[-1][0] + g, final[-1][1])
        else:
            final.append((g, p))
    return final


def lapidar_parte(llm, meta, ctx, falas, info, vizinhas):
    """Reescreve a parte como um vídeo curto completo (gancho, re-ganchos, fechamento, CTA) + metadados."""
    s0 = min(f["src_inicio"] for f in falas)
    s1 = max(f["src_fim"] for f in falas)
    serie = info.get("serie")
    alvo_pal = int(P["alvo"] * P["wps"])
    pmin, pmax = int(P["min"] * P["wps"] * 1.04), int(P["max"] * P["wps"])
    material = "\n".join(f"- [{f['src_inicio']:.1f}-{f['src_fim']:.1f}] {f['texto']}" for f in falas)
    nota_serie = (f'ESTA PARTE É A {serie["n"]} DE {serie["de"]} de uma série sobre o mesmo tema. Deixe isso claro no gancho '
                  f'ou no fim ("parte {serie["n"]}"). Mesmo assim, faça cada parte ter começo, meio e fim.'
                  if serie else "Esta parte NÃO é série: não mencione outras partes.")

    def pedir(extra=""):
        prompt = f"""Vídeo original: "{meta.get('titulo', '')}" (canal {meta.get('canal', '')}).
Contexto geral (só para você entender o assunto; NÃO cite outras partes): {ctx}
Tema desta parte: {info.get('titulo_tema', '')}
Outras partes que existem (NÃO cite): {vizinhas}
{nota_serie}

ESTILO: {GIRIA[P['giria']]}

{PLAYBOOK}

TAREFA: reescreva o MATERIAL abaixo como o roteiro final de UM vídeo curto independente.
- Tamanho: entre {pmin} e {pmax} palavras no total (ideal {alvo_pal}), para durar de {int(P['min'])} a {int(P['max'])} segundos falando. O vídeo PRECISA ter mais de 60 segundos: se o material for curto, aprofunde com contexto, explicação passo a passo, exemplo e a opinião do canal, SEM inventar fatos.
- Cada fala = 1 frase falada (máx. 20 palavras). Cada fala tem src_inicio e src_fim: o trecho do vídeo original (entre {s0:.1f} e {s1:.1f} s) que aparece na tela enquanto ela é dita. Mantenha a ordem do vídeo; só o GANCHO (primeira fala) pode usar o momento mais impactante da parte.
- titulo: até 60 caracteres, palavra-chave principal no começo, promete algo real, sem clickbait falso, sem ponto final.
- titulos_alternativos: 2 opções diferentes (um tipo pergunta, um tipo número/lista).
- gancho_tela: 4 a 7 palavras em CAIXA ALTA para aparecer no primeiro frame.
- descricao: 3 linhas curtas; a 1ª tem a palavra-chave e a promessa; a 2ª dá o contexto; a 3ª é uma pergunta para comentar.
- hashtags: 3 a 5, relevantes e específicas (jogo, tema, nicho), com #.
- palavras_chave: 4 a 6 termos que a pessoa buscaria.
- comentario_fixado: 1 pergunta curta que gera resposta.
{extra}
Responda: {{"titulo":"","titulos_alternativos":["",""],"gancho_tela":"","descricao":"","hashtags":[],"palavras_chave":[],"comentario_fixado":"","falas":[{{"texto":"","src_inicio":0.0,"src_fim":0.0}}]}}

MATERIAL:
{material}"""
        return llm.json(prompt, 3500)

    def limpar(r):
        out = []
        for f in r.get("falas", []):
            try:
                txt = " ".join(str(f["texto"]).split())
                a, b = float(f["src_inicio"]), float(f["src_fim"])
            except (KeyError, TypeError, ValueError):
                continue
            if not txt:
                continue
            a = min(max(a, s0 - 2), s1)
            b = min(max(b, a + 1.0), s1 + 4.0)
            out.append({"texto": txt, "src_inicio": round(a, 2), "src_fim": round(b, 2)})
        return out

    melhor, melhor_nota, extra = None, None, ""
    for tentativa in range(3):
        try:
            r = pedir(extra)
        except RuntimeError:
            if melhor is not None:
                break
            raise
        fs = limpar(r)
        if not fs:
            continue
        est = estimar(fs)
        texto = " ".join(f["texto"] for f in fs)
        problemas = []
        if est < P["min"]:
            faltam = int((P["min"] * 1.05 - est) * P["wps"]) + 5
            problemas.append(f"O roteiro está CURTO (cerca de {int(est)} s). Acrescente uns {faltam} palavras de contexto, "
                             "explicação e opinião do canal, sem inventar fatos.")
        if not serie and PROIBIDAS.search(texto):
            problemas.append("Remova qualquer referência a outra parte ou vídeo anterior (\"como vimos\", \"continuando\", etc.): "
                             "a parte precisa ser independente.")
        if FORA.search(texto):
            problemas.append("Não mande a pessoa para o vídeo completo, link ou outro canal. Feche com comentário, salvar ou seguir.")
        nota = (len(problemas), abs(est - P["alvo"]))
        if melhor_nota is None or nota < melhor_nota:
            melhor, melhor_nota = r, nota
        if not problemas:
            break
        print(f"   ajustando parte ({'; '.join(p[:45] for p in problemas)})", flush=True)
        extra = "\nCORREÇÃO NECESSÁRIA NA VERSÃO ANTERIOR:\n- " + "\n- ".join(problemas) + "\n"
    r = melhor
    fs = limpar(r) if r else []
    if not fs:
        fs = falas  # reserva: usa o material como está
        r = r or {}
    return fs, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--partes", type=int, default=0, help="número de partes (0 = automático)")
    ap.add_argument("--alvo", type=float, default=75.0, help="duração alvo de cada parte, em segundos")
    ap.add_argument("--min-parte", type=float, default=65.0, help="duração mínima estimada (precisa passar de 60 s)")
    ap.add_argument("--max-parte", type=float, default=110.0)
    ap.add_argument("--giria", default="media", choices=list(GIRIA))
    ap.add_argument("--wps", type=float, default=2.7, help="palavras por segundo da voz (estimativa)")
    ap.add_argument("--resumo", type=float, default=0.0, help="fração das palavras do original que sobra (0 = automático)")
    ap.add_argument("--llm", default="auto", choices=["auto", "github", "gemini"])
    ap.add_argument("--modelo-llm", default="")
    a = ap.parse_args()
    P.update({"wps": a.wps, "alvo": a.alvo, "min": a.min_parte, "max": max(a.max_parte, a.min_parte + 10),
              "giria": a.giria})

    pasta = os.path.join("jobs", a.job)
    tr = json.load(open(os.path.join(pasta, "fonte_transcricao.json"), encoding="utf-8"))
    mp = os.path.join(pasta, "meta.json")
    meta = json.load(open(mp, encoding="utf-8")) if os.path.isfile(mp) else {}
    trechos = tr["trechos"]
    pal_total = sum(palavras(t["text"]) for t in trechos)
    # o resumo é um pouco MAIOR que o necessário: a lapidação depois aperta ou aprofunda cada parte
    razao = a.resumo
    if not razao:
        alvo_total = (a.partes or max(1, round(pal_total / P["wps"] / 60 * 0.4 / (P["alvo"] / 60)))) * P["alvo"]
        razao = alvo_total * P["wps"] * 1.1 / max(pal_total, 1)
    razao = min(0.75, max(0.15, razao))
    print(f"fonte: {pal_total} palavras, resumo para ~{razao:.0%} (partes de ~{P['alvo']:.0f}s, mín {P['min']:.0f}s)", flush=True)

    llm = LLM(a.llm, a.modelo_llm)
    vocab = f"{meta.get('titulo', '')}, {meta.get('canal', '')}"
    falas = []
    for k, jan in enumerate(janelas(trechos), 1):
        print(f"   janela {k}: {jan[0]['start'] / 60:.1f}-{jan[-1]['end'] / 60:.1f} min", flush=True)
        falas += falas_da_janela(llm, meta, tr.get("idioma", "en"), jan, razao, vocab)
    print(f"{len(falas)} falas, ~{estimar(falas):.0f}s de locução", flush=True)

    try:
        est = estruturar(llm, falas, meta, a.partes)
    except Exception as e:
        print(f"   estruturação falhou ({str(e)[:120]}); dividindo por tempo", flush=True)
        est = {}
    partes = montar_partes(falas, est, P["alvo"])
    temas = [p.get("titulo_tema") or f"parte {i}" for i, (_, p) in enumerate(partes, 1)]
    ctx = f"{est.get('titulo_serie') or meta.get('titulo', '')}. Assuntos do vídeo: " + "; ".join(temas)

    roteiro = {"titulo_original": meta.get("titulo", ""), "canal": meta.get("canal", ""), "url": meta.get("url", ""),
               "titulo_serie": est.get("titulo_serie") or meta.get("titulo", ""),
               "hashtags_gerais": est.get("hashtags_gerais") or [], "config": {}, "partes": []}
    for i, (g, info) in enumerate(partes, 1):
        print(f"   lapidando parte {i}/{len(partes)}: {info.get('titulo_tema', '')}", flush=True)
        viz = "; ".join(t for j, t in enumerate(temas, 1) if j != i)
        try:
            fs, r = lapidar_parte(llm, meta, ctx, g, info, viz)
        except RuntimeError as e:
            print(f"   AVISO lapidação falhou ({str(e)[:140]}); usando o resumo simples", flush=True)
            fs, r = g, {}
        serie = info.get("serie")
        titulo = (r.get("titulo") or info.get("titulo_tema") or f"Parte {i}").strip().rstrip(".")
        hashtags = [h if h.startswith("#") else "#" + h.lstrip("#") for h in (r.get("hashtags") or roteiro["hashtags_gerais"])][:5]
        if serie:
            titulo += f" (Parte {serie['n']}/{serie['de']})"
            hashtags = hashtags[:4] + [f"#parte{serie['n']}"]
        roteiro["partes"].append({
            "id": f"{i:02d}", "titulo": titulo, "titulos_alternativos": r.get("titulos_alternativos") or [],
            "gancho_tela": (r.get("gancho_tela") or "").upper(), "gancho": "", "serie": serie,
            "descricao": r.get("descricao") or "", "hashtags": hashtags,
            "palavras_chave": r.get("palavras_chave") or [], "comentario_fixado": r.get("comentario_fixado") or "",
            "falas": fs})
    with open(os.path.join(pasta, "roteiro.json"), "w", encoding="utf-8") as f:
        json.dump(roteiro, f, ensure_ascii=False, indent=1)
    for p in roteiro["partes"]:
        print(f"ROTEIRO parte {p['id']}: ~{estimar(p['falas']):.0f}s, {len(p['falas'])} falas - {p['titulo']}", flush=True)


if __name__ == "__main__":
    main()
