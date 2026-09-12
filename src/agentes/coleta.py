"""
Agente 1 - Coleta.

Responsabilidade unica: obter a previsao meteorologica das localidades onde ha
segurados e devolve-la em um formato normalizado (PrevisaoLocal), independente
da fonte usada.

Fonte principal: Open-Meteo (https://open-meteo.com) - API publica e gratuita,
sem necessidade de chave, que entrega dados de previsao em resolucao horaria
usando os codigos de tempo do padrao WMO.

O agente tambem possui um modo "simulacao", que gera cenarios sinteticos com a
mesma estrutura de dados. Ele existe por dois motivos: permitir demonstrar o
fluxo completo sem depender da rede e possibilitar testes deterministicos das
regras de negocio (um dia de ceu limpo nao produziria nenhum alerta).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import requests

from src import config
from src.models import JanelaPrevisao, PrevisaoLocal, Segurado


class AgenteColeta:
    """Coleta previsoes agrupando segurados por coordenada."""

    nome = "AgenteColeta"

    def __init__(self, modo: str = "api", logger=None) -> None:
        self.modo = modo  # "api" | "simulacao"
        self.log = logger or (lambda _msg: None)

    # -- API publica --------------------------------------------------------
    def _consultar_open_meteo(self, lat: float, lon: float) -> dict:
        parametros = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,precipitation,wind_gusts_10m,weather_code",
            "timezone": "America/Sao_Paulo",
            "forecast_days": config.FORECAST_DIAS,
        }
        resposta = requests.get(
            config.OPEN_METEO_URL,
            params=parametros,
            timeout=config.OPEN_METEO_TIMEOUT,
        )
        resposta.raise_for_status()
        return resposta.json()

    @staticmethod
    def _normalizar(payload: dict) -> list[JanelaPrevisao]:
        horario = payload.get("hourly", {})
        instantes = horario.get("time", [])
        janelas: list[JanelaPrevisao] = []
        for i, instante in enumerate(instantes):
            def valor(chave: str):
                serie = horario.get(chave) or []
                return serie[i] if i < len(serie) else None

            janelas.append(
                JanelaPrevisao(
                    instante=datetime.fromisoformat(instante).replace(tzinfo=config.FUSO),
                    temperatura_c=valor("temperature_2m"),
                    precipitacao_mm=valor("precipitation"),
                    rajada_vento_kmh=valor("wind_gusts_10m"),
                    codigo_tempo=valor("weather_code"),
                )
            )
        return janelas

    # -- Execucao -----------------------------------------------------------
    def executar(self, segurados: list[Segurado]) -> list[PrevisaoLocal]:
        # Agrupa por coordenada: varios segurados da mesma cidade geram
        # uma unica chamada a API.
        locais: dict[str, Segurado] = {}
        for segurado in segurados:
            locais.setdefault(segurado.chave_local, segurado)

        self.log(
            f"[{self.nome}] {len(segurados)} segurados em {len(locais)} localidades distintas "
            f"(modo: {self.modo})"
        )

        previsoes: list[PrevisaoLocal] = []
        for chave, referencia in locais.items():
            if self.modo == "simulacao":
                from src.simulacao import gerar_previsao_simulada

                previsao = gerar_previsao_simulada(referencia)
                self.log(f"[{self.nome}] cenario simulado gerado para {referencia.local}")
                previsoes.append(previsao)
                continue

            try:
                payload = self._consultar_open_meteo(referencia.latitude, referencia.longitude)
                janelas = self._normalizar(payload)
                limite = datetime.now(tz=config.FUSO) + timedelta(
                    hours=config.JANELA_ANTECEDENCIA_H
                )
                agora = datetime.now(tz=config.FUSO)
                janelas = [j for j in janelas if agora <= j.instante <= limite]
                previsoes.append(
                    PrevisaoLocal(
                        chave_local=chave,
                        cidade=referencia.cidade,
                        uf=referencia.uf,
                        latitude=referencia.latitude,
                        longitude=referencia.longitude,
                        fonte="Open-Meteo (API publica)",
                        coletado_em=agora,
                        janelas=janelas,
                    )
                )
                self.log(
                    f"[{self.nome}] {referencia.local}: {len(janelas)} janelas horarias coletadas"
                )
            except Exception as erro:  # falha de rede nao derruba o pipeline
                self.log(f"[{self.nome}] ERRO em {referencia.local}: {erro}")

        return previsoes
