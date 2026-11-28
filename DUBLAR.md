# Resumir e dublar vídeo (inglês → português), de graça

Pega **um vídeo inteiro** (ex.: 25 min em inglês), resume o roteiro, divide em partes, dubla em português, legenda palavra por palavra e monta em 9:16. Roda no GitHub Actions, sem pagar nada.

## Novidades (v2)
- **Roteiro de gamer:** linguagem simples com gírias (`giria`: leve/media/alta) e regras de gancho, retenção e SEO ([GUIA_ROTEIRO.md](GUIA_ROTEIRO.md)).
- **Vídeos independentes:** cada parte tem começo, meio e fim. Só quando um tema fechado não cabe no máximo ele vira "Parte 1/2" (com `#parte1`).
- **Mais de 1 minuto garantido:** alvo 75 s, mínimo 65 s no roteiro; na montagem, se ficar abaixo de 61 s a voz desacelera e as pausas aumentam.
- **Efeitos sonoros** (whoosh, impacto, ding de grana, riser) gerados por código, sem direitos autorais. `sfx`: off/leve/medio/forte.
- **Marca d'água** (logo PNG em `marca/marca.png` ou texto `marca_texto`).
- **Texto do gancho** nos 3 primeiros segundos e **publicacao.md** completo (YouTube, TikTok, Instagram, comentário fixado).
- **Testar vozes:** workflow **"6 - Testar vozes"** gera uma amostra de cada voz para você ouvir.

## O que sai
- `parte_01.mp4`, `parte_02.mp4`... (1080x1920, ~60 s cada) + `publicacao.md` (título, descrição, hashtags e **crédito do vídeo original**) numa Release chamada `dub-<job>`.
- Visual: fundo = o próprio vídeo ampliado e borrado, vídeo nítido 16:9 no meio, legenda em caixa alta (Montserrat Black) com a **palavra falada em caixa roxa**. Sem o áudio original (está em inglês); só a voz em português.

## Como usar
**Actions → "5 - Resumir e dublar vídeo" → Run workflow**

| Campo | O que colocar |
|---|---|
| `etapa` | `tudo` (faz tudo) · `roteiro` (para antes de renderizar, para você revisar) · `renderizar` (usa o `roteiro.json` já salvo) |
| `url` | link do vídeo, ou `release:<tag>/<arquivo.mp4>` |
| `job` | nome sem espaço, ex.: `2026-11-25-gta6-dinheiro` |
| `idioma` | idioma do vídeo original (`en`, `es`, `auto`) |
| `partes` | número de partes (`0` = a IA decide pelos assuntos do vídeo) |
| `alvo` | duração alvo de cada vídeo, em segundos (75). Para o TikTok pagar, precisa passar de 60 |
| `voz` | `pt-BR-AntonioNeural` (homem) · `pt-BR-FranciscaNeural` (mulher) |
| `so` | refazer só algumas partes (`01,03`) |
| `opcoes` | JSON, tudo opcional: `{"giria":"media","sfx":"medio","marca_texto":"@seucanal","marca_pos":"painel_dir","tom":"+0Hz","ritmo":"+8%","min":65,"max":110,"llm":"auto","whisper":"small"}` |

Fluxo recomendado na primeira vez: `etapa=roteiro` → abra `jobs/<job>/roteiro.json`, leia/ajuste as falas → rode de novo com `etapa=renderizar`. Se confiar no resultado, `tudo` já entrega as partes.

## O que cada passo usa (tudo grátis)
| Passo | Ferramenta | Script |
|---|---|---|
| baixar | yt-dlp | `scripts/dub_baixar.py` |
| transcrever | faster-whisper (roda no próprio runner) | `scripts/dub_transcrever.py` |
| resumir, traduzir e dividir em partes | **GitHub Models** (usa o token do repositório, sem chave) ou **Gemini** (se existir o segredo `GEMINI_API_KEY`) | `scripts/dub_roteiro.py` |
| voz em português | edge-tts (vozes neurais da Microsoft); reserva: gTTS | `scripts/dub_render.py` |
| legenda + edição + montagem | Pillow + ffmpeg | `scripts/dub_render.py` |

## Limites e problemas comuns
- **YouTube bloqueia servidores do GitHub** (`ERRO_YOUTUBE_BLOQUEOU`). Soluções: criar o segredo `YT_COOKIES` (cookies do navegador, formato Netscape; o robô já usa) ou baixar o vídeo no seu PC, subir numa Release e usar `release:<tag>/<arquivo.mp4>` no campo `url`.
- **Cota do GitHub Models**: é grátis mas limitada por dia. Um vídeo de 25 min usa ~8 pedidos. Se acabar a cota, o erro avisa: tente amanhã, crie o segredo `GEMINI_API_KEY` (chave grátis do Google AI Studio) ou escreva o `roteiro.json` à mão (o Claude pode fazer isso lendo `fonte_transcricao.txt`).
- **Tempo**: ~10 a 25 min por vídeo de 25 min (a transcrição é a parte mais lenta). Repositório público = minutos grátis ilimitados; privado = 2.000 min/mês.
- **Parte passou de 90 s**: o log avisa. Divida a parte no `roteiro.json` ou aumente `ritmo` (`+15%`).
- A voz da edge-tts depende de um serviço online da Microsoft, sem garantia de continuar grátis para sempre. Se ela falhar 3 vezes numa fala, o robô troca sozinho para o gTTS.

## `roteiro.json` (pode editar à mão)
```json
{"titulo_original": "...", "canal": "...", "url": "...",
 "config": {"voz": "pt-BR-AntonioNeural", "ritmo": "+8%", "gancho": true, "rotulo_parte": false,
            "cor_destaque": "#6D3EF2", "musica": "musicas/fundo.mp3", "vol_musica": 0.07},
 "partes": [{"id": "01", "titulo": "...", "gancho": "frase que abre o vídeo", "descricao": "...",
   "falas": [{"texto": "Frase em português, feita para ser falada.", "src_inicio": 125.4, "src_fim": 140.0}]}]}
```
- Cada **fala** é dita em voz alta e mostra o trecho `src_inicio`→`src_fim` do vídeo original (acelerado/desacelerado de 0,9x a 1,6x para durar o mesmo que a voz).
- `config` é opcional. `rotulo_parte: true` põe "PARTE 1/8" no topo. Música: coloque um arquivo **livre de direitos** em `musicas/` e aponte em `config.musica`.

## Direitos autorais
Resumir e dublar o vídeo de outro canal usa a imagem e o roteiro dele. Peça autorização ou escolha canais que liberem, mantenha o crédito do `publicacao.md` e saiba que o YouTube pode tratar como "conteúdo reutilizado" (risco de desmonetização/strike). Em repositório público, a transcrição fica visível; o vídeo original **não** é publicado (só as partes prontas).
