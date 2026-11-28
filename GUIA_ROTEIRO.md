# Guia de roteiro, SEO e engajamento (Shorts / TikTok / Reels)

Este guia junta o que **serve** do PDF de ideias (100 temas, 150 ganchos, 100 títulos, 60 roteiros) com o que a pesquisa
mostrou sobre retenção e busca. Boa parte do PDF é para criar vídeo **do zero** (escolher tema, gravar, "POV", memes sem
fala). Isso **não** se aplica a vídeos prontos/lives. O que aproveitamos é a técnica, não os temas.
O robô já aplica estas regras no `scripts/dub_roteiro.py` (constante `PLAYBOOK`). Para escrever roteiro à mão (Claude),
siga o mesmo guia.

## O que aproveitamos do PDF
| Do PDF | Como entra no robô |
|---|---|
| Anatomia do roteiro: **gancho (0 a 3 s) → conteúdo em cortes rápidos → CTA** | Estrutura de toda parte |
| Os **10 tipos de gancho** (curiosidade, afirmação forte, pergunta, POV, lista/número, polêmica, urgência, comparação, revelação, emoção) | A IA escolhe o tipo que combina com o trecho; POV e meme sem fala não se aplicam |
| Texto grande de **4 a 7 palavras no primeiro quadro** + falar o gancho | `gancho_tela` (aparece nos 3 primeiros segundos) |
| **Título SEO:** palavra-chave no começo; número no título ajuda no clique | Regra do `titulo` (até 60 caracteres) |
| **CTA por objetivo:** comentar, salvar, seguir ("tem parte 2") | Fechamento de cada vídeo + `comentario_fixado` |
| **5 a 8 hashtags** misturando gigante + nicho + Brasil; **customizar por plataforma**; não colar legenda idêntica nas redes | `publicacao.md` (YouTube, TikTok e Instagram separados) |
| "Separe **fato de especulação**; não prometa o que não é confirmado" | Regra 4 do roteiro |
| "Tema bom tem **promessa, curiosidade e entrega real**" | Gancho promete só o que o vídeo entrega |

## O que NÃO usamos (e por quê)
- **100 temas e 60 roteiros prontos:** são para criar conteúdo do zero. Aqui o conteúdo vem do vídeo original.
- **Ganchos "Confirmado/Vazou/Oficial":** só valem se o vídeo original realmente confirma. Mentir no gancho derruba retenção e pode gerar denúncia.
- **Ganchos de polêmica pesada:** gera comentário, mas arrisca desmonetização. O robô usa opinião leve.
- **Voz de IA "sem aparecer" como solução mágica:** funciona, mas veja o aviso de originalidade abaixo.

## O que a pesquisa acrescenta
1. **Retenção manda mais que duração.** O que importa é quanto do vídeo as pessoas assistem. Um vídeo de 30 s visto até o fim costuma ir melhor que um de 60 s abandonado no meio. Por isso, para passar de 60 s sem perder gente: gancho forte, frases curtas e **re-ganchos a cada 15 a 20 s** ("mas calma, tem mais").
2. **Os 2 a 3 primeiros segundos decidem.** Quando muita gente "passa" logo no início, o vídeo para de ser entregue. Nada de "fala galera" ou apresentação.
3. **Fale a palavra-chave em voz alta.** O YouTube transcreve o áudio e usa na busca: a palavra principal vai no título, na 1ª linha da descrição **e na fala** do começo.
4. **Loop:** quando o fim "emenda" no começo, a pessoa revê (revisualização é sinal forte). Por isso a última frase ecoa o gancho.
5. **Não mande a pessoa sair do feed** ("veja o vídeo completo", "link na bio"): derruba a retenção. O CTA é comentar, salvar ou seguir.
6. **Poucas hashtags, bem escolhidas** (3 a 5). Mais que isso não ajuda; o esforço vale mais no título, no gancho e na retenção.
7. **As primeiras horas** definem o alcance: poste num horário de pico e responda os primeiros comentários.
8. **Cada parte independente:** quem cai numa parte precisa entender tudo. Só use "Parte 1/2" quando um tema fechado realmente não cabe no limite.

## Modelos (adapte; troque [assunto])
**Ganchos (até 12 palavras):**
- Curiosidade: "Quase ninguém usa esse método de grana no [jogo]."
- Pergunta: "Você sabia que dá pra [resultado] em [jogo]?"
- Número: "3 jeitos de [resultado] no [jogo], o último é absurdo."
- Erro: "Para de fazer isso no [jogo], tá te custando [coisa]."
- Comparação: "[A] ou [B]? A diferença é bizarra."

**Re-ganchos:** "Mas calma, tem mais." · "Agora vem a parte boa." · "E aqui tá o pulo do gato."

**CTA que gera comentário:** "Qual você testaria? Comenta aí." · **Salvar:** "Salva pra quando precisar." · **Seguir:** "Segue pra não perder o próximo."

**Título (60 caracteres):** `[Palavra-chave]: [promessa específica]`. Ex.: "GTA 6 dinheiro: o método mais rápido".

**Descrição (3 linhas):** (1) palavra-chave + promessa · (2) contexto em uma frase + crédito do vídeo original · (3) pergunta para comentar. Depois, 3 a 5 hashtags.

## Linguagem gamer
`opcoes.giria`: `leve` (simples, pouca gíria) · `media` (padrão) · `alta` (bem solto). Sem palavrão, sem ofensa. Evite gíria forçada: se soar artificial, volte para `leve`.

## Monetização e originalidade (leia)
- **TikTok Creator Rewards** (o programa que exige **mais de 1 minuto**) também exige conteúdo **original**; cópias e republicações levemente alteradas ficam de fora.
- **YouTube:** não existe duração mínima para Shorts (de 1 a 3 minutos na vertical ainda contam como Short). O que pesa é entrar no Programa de Parcerias e **não ser "conteúdo reutilizado"**: a regra vale **mesmo com permissão do dono**, e exige comentário, edição ou valor próprios que tornem seu vídeo claramente diferente do original.
- O que o robô já adiciona de "valor próprio": roteiro **reescrito** (não é tradução), opinião/veredito do canal, estrutura nova, narração, legenda, efeitos e edição. Isso ajuda, mas **não é garantia**: quem decide é a plataforma, olhando o canal como um todo. Quanto mais opinião, análise e contexto **seus** (revise o `roteiro.json`), melhor.
- Se um vídeo for **claimado por direitos autorais** (por exemplo, música de fundo do jogo), Shorts acima de 1 minuto com claim são **bloqueados** no YouTube. Por isso os efeitos são gerados por código e a música de fundo é opcional.
