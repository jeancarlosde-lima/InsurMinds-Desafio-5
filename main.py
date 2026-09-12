"""
Execucao do fluxo completo pela linha de comando.

Exemplos:
    python main.py                      # API publica + LLM (se houver chave)
    python main.py --modo simulacao     # cenarios sinteticos, sem rede
    python main.py --sem-llm            # mensagens por template
"""

from __future__ import annotations

import argparse
import sys

# O console do Windows nem sempre usa UTF-8; sem isso, acentos quebram a saida.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.orquestrador import executar_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="InsurMinds - Desafio 5: comunicacao proativa com o segurado"
    )
    parser.add_argument(
        "--modo",
        choices=["api", "simulacao"],
        default="api",
        help="fonte dos dados meteorologicos (padrao: api)",
    )
    parser.add_argument(
        "--sem-llm",
        action="store_true",
        help="gera as mensagens por template, sem chamar o modelo de linguagem",
    )
    parser.add_argument(
        "--ignorar-historico",
        action="store_true",
        help="desativa a regra de cooldown (util para demonstracoes repetidas)",
    )
    argumentos = parser.parse_args()

    resultado = executar_pipeline(
        modo_dados=argumentos.modo,
        usar_llm=not argumentos.sem_llm,
        usar_historico=not argumentos.ignorar_historico,
    )

    print("\n".join(resultado.log))
    print("\n" + "=" * 78)
    print(f"Fonte de dados : {resultado.modo_dados}")
    print(f"Gerador de texto: {resultado.modo_llm}")
    print(f"Eventos identificados: {len(resultado.eventos)}")
    print(f"Notificacoes simuladas: {resultado.total_notificados}")
    print(f"Decisoes suprimidas   : {resultado.total_suprimidos}")
    print("=" * 78)

    for notificacao in resultado.notificacoes:
        print(
            f"\n[{notificacao.id_notificacao}] {notificacao.nome} - {notificacao.local} "
            f"({notificacao.ramo.value}) via {notificacao.canal.value} "
            f"| {notificacao.tipo_evento.value}/{notificacao.severidade.value}"
        )
        if notificacao.assunto:
            print(f"Assunto: {notificacao.assunto}")
        print(notificacao.mensagem)


if __name__ == "__main__":
    main()
