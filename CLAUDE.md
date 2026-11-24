# Robô de cortes de live

Siga `SKILL.md` (fluxo completo) e `LEGENDAR.md` (legenda). O robô já está montado neste repositório, então pule o passo 0 dele.

## Ajustes para rodar no Claude Code (sessão na nuvem / projeto)
- O repositório fica em `/home/user/gta06` (não em `/home/claude/...`). `R=repos/joaogabrieliost06-spec/gta06`.
- Onde o `SKILL.md` diz `SendUserFile`: copie o arquivo para `/mnt/project-files/cortes/<job>/` e entregue anexando em `post_message` (`attached_outputs`). Vídeo grande (>100 MB): mande a versão 720p ou o link da Release.
- Checagens de live ao vivo: use `send_later` (lembrete único) ou `create_trigger` (tarefa recorrente, ex.: as três tarefas de hora em hora do vigia).
- Sem `sleep` em primeiro plano: para esperar um workflow, use um loop com `timeout 20 tail -f /dev/null` ou a ferramenta Monitor.
- **Todo corte tem no máximo 90 segundos** (regra do usuário).
- Live brasileira com jogo em inglês: o idioma automático já prefere português; se a transcrição sair em inglês, refaça com `idioma=pt`.
- Fale com o usuário em português simples.
