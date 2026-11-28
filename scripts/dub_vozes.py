#!/usr/bin/env python3
"""
Gera uma AMOSTRA de áudio de cada voz disponível em português do Brasil (e das vozes "Multilingual", de outros
países, que também falam português), todas lendo o mesmo texto, para você ouvir e escolher.

  dub_vozes.py [--texto "..."] [--ritmo +8%] [--saida saida/vozes]

Grava saida/vozes/<voz>.mp3 e saida/vozes/LISTA.md. Depois use o nome da voz no campo `voz` do workflow de dublagem.
"""
import argparse, asyncio, os, sys

TEXTO = ("Mano, olha só esse método que rende uma grana absurda no GTA 6. Bora ver como funciona, "
         "porque quase ninguém tá usando direito ainda!")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texto", default=TEXTO)
    ap.add_argument("--ritmo", default="+8%")
    ap.add_argument("--saida", default=os.path.join("saida", "vozes"))
    ap.add_argument("--so-pt", action="store_true", help="só vozes pt-BR (sem as Multilingual de outros países)")
    a = ap.parse_args()
    import edge_tts
    os.makedirs(a.saida, exist_ok=True)
    todas = await edge_tts.list_voices()
    sel = [v for v in todas if v["Locale"] == "pt-BR" or (not a.so_pt and "Multilingual" in v["ShortName"])]
    sel.sort(key=lambda v: (v["Locale"] != "pt-BR", v["ShortName"]))
    print(f"{len(sel)} vozes encontradas ({sum(v['Locale'] == 'pt-BR' for v in sel)} em pt-BR)", flush=True)
    linhas = ["# Vozes testadas\n", f"Texto: {a.texto}\n", "| Voz (use este nome) | Gênero | Origem | Arquivo |", "|---|---|---|---|"]
    ok = 0
    for v in sel:
        nome = v["ShortName"]
        arq = os.path.join(a.saida, nome + ".mp3")
        try:
            await edge_tts.Communicate(a.texto, nome, rate=a.ritmo).save(arq)
            ok += 1
            print(f"OK    {nome} ({v['Gender']}, {v['Locale']})", flush=True)
            linhas.append(f"| `{nome}` | {v['Gender']} | {v['Locale']} | {nome}.mp3 |")
        except Exception as e:
            print(f"FALHOU {nome}: {str(e)[:100]}", flush=True)
    open(os.path.join(a.saida, "LISTA.md"), "w", encoding="utf-8").write("\n".join(linhas) + "\n")
    if not ok:
        sys.exit("ERRO_VOZES nenhuma voz gerou áudio (o serviço de voz pode estar bloqueado)")


if __name__ == "__main__":
    asyncio.run(main())
