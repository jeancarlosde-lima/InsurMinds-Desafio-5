"""
Orquestrador do fluxo multiagente.

Encadeia os cinco agentes especializados e devolve um objeto unico
(ResultadoPipeline) com tudo que aconteceu em uma execucao - previsoes,
eventos, decisoes (aprovadas e suprimidas), mensagens e notificacoes - alem de
um log passo a passo que permite auditar o raciocinio da solucao.

    Coleta -> Analise -> Regras -> Redacao -> Notificacao
"""

from __future__ import annotations

import csv
from datetime import datetime

from src import config
from src.agentes.analise import AgenteAnalise
from src.agentes.coleta import AgenteColeta
from src.agentes.notificacao import AgenteNotificacao
from src.agentes.redacao import AgenteRedacao
from src.agentes.regras import AgenteRegras
from src.models import ResultadoPipeline, Segurado


def carregar_segurados(caminho=None) -> list[Segurado]:
    """Le a carteira simulada de segurados (CSV)."""
    caminho = caminho or config.ARQ_SEGURADOS
    segurados: list[Segurado] = []
    with open(caminho, newline="", encoding="utf-8") as origem:
        for linha in csv.DictReader(origem, delimiter=";"):
            segurados.append(
                Segurado(
                    id_segurado=linha["id_segurado"],
                    nome=linha["nome"],
                    cidade=linha["cidade"],
                    uf=linha["uf"],
                    latitude=float(linha["latitude"]),
                    longitude=float(linha["longitude"]),
                    ramo=linha["ramo"],
                    apolice=linha["apolice"],
                    canal=linha["canal"],
                    observacao=linha.get("observacao", ""),
                )
            )
    return segurados


def executar_pipeline(
    modo_dados: str = "api",
    usar_llm: bool = True,
    usar_historico: bool = True,
    segurados: list[Segurado] | None = None,
) -> ResultadoPipeline:
    """Executa o fluxo completo e devolve o resultado consolidado."""
    registros: list[str] = []

    def log(mensagem: str) -> None:
        carimbo = datetime.now(tz=config.FUSO).strftime("%H:%M:%S")
        registros.append(f"{carimbo} {mensagem}")

    log("[Orquestrador] inicio da execucao")
    carteira = segurados if segurados is not None else carregar_segurados()
    indice = {s.id_segurado: s for s in carteira}
    log(f"[Orquestrador] carteira carregada: {len(carteira)} segurados")

    coleta = AgenteColeta(modo=modo_dados, logger=log)
    analise = AgenteAnalise(logger=log)
    regras = AgenteRegras(logger=log, usar_historico=usar_historico)
    redacao = AgenteRedacao(usar_llm=usar_llm, logger=log)
    notificacao = AgenteNotificacao(logger=log, registrar_historico=usar_historico)

    previsoes = coleta.executar(carteira)
    eventos = analise.executar(previsoes)
    decisoes = regras.executar(carteira, eventos)
    mensagens = redacao.executar(decisoes, indice)
    notificacoes = notificacao.executar(mensagens, indice)

    log("[Orquestrador] execucao concluida")

    return ResultadoPipeline(
        executado_em=datetime.now(tz=config.FUSO),
        modo_dados="API publica Open-Meteo" if modo_dados == "api" else "Simulacao interna",
        modo_llm=redacao.modo,
        previsoes=previsoes,
        eventos=eventos,
        decisoes=decisoes,
        mensagens=mensagens,
        notificacoes=notificacoes,
        log=registros,
    )
