"""
Gerador de cenarios meteorologicos sinteticos.

Usado apenas no modo "simulacao" do AgenteColeta. Os cenarios sao ancorados no
horario atual (o evento sempre cai dentro da janela de antecedencia) e sao
deterministicos por cidade, o que torna a demonstracao reproduzivel.

Os dados seguem exatamente o mesmo formato entregue pela API publica, entao
todos os agentes seguintes funcionam sem nenhuma alteracao.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from src import config
from src.models import JanelaPrevisao, PrevisaoLocal, Segurado

# cenario -> (descricao, pico_chuva_mm, pico_rajada_kmh, codigo_wmo, temp_base, temp_pico)
CENARIOS = {
    "temporal_granizo": ("Temporal com granizo", 24.0, 82.0, 96, 24.0, 28.0),
    "chuva_forte": ("Chuva intensa persistente", 16.0, 48.0, 65, 21.0, 25.0),
    "vendaval": ("Vendaval costeiro", 3.0, 88.0, 80, 20.0, 24.0),
    "onda_calor": ("Onda de calor", 0.0, 22.0, 0, 30.0, 39.0),
    "geada": ("Geada agricola", 0.0, 14.0, 0, 8.0, 12.0),
    "estavel": ("Tempo estavel", 0.4, 18.0, 2, 22.0, 27.0),
}

# Atribuicao fixa de cenario por cidade, para que a demonstracao cubra
# eventos diferentes e ramos diferentes ao mesmo tempo.
MAPA_CIDADES = {
    "São Paulo": "temporal_granizo",
    "Itaquaquecetuba": "chuva_forte",
    "Santos": "vendaval",
    "Ribeirão Preto": "onda_calor",
    "Ponta Grossa": "geada",
    "Campinas": "estavel",
    "Sorriso": "temporal_granizo",
    "Curitiba": "chuva_forte",
}


def escolher_cenario(cidade: str) -> str:
    if cidade in MAPA_CIDADES:
        return MAPA_CIDADES[cidade]
    semente = sum(ord(c) for c in cidade)
    chaves = list(CENARIOS)
    return chaves[semente % len(chaves)]


def gerar_previsao_simulada(segurado: Segurado, horas: int = 48) -> PrevisaoLocal:
    cenario = escolher_cenario(segurado.cidade)
    _, pico_chuva, pico_rajada, codigo, temp_base, temp_pico = CENARIOS[cenario]

    rng = random.Random(sum(ord(c) for c in segurado.cidade))
    agora = datetime.now(tz=config.FUSO).replace(minute=0, second=0, microsecond=0)
    # O pico do evento ocorre entre 6 e 20 horas a frente.
    hora_pico = 6 + rng.randint(0, 14)

    janelas: list[JanelaPrevisao] = []
    for h in range(horas):
        instante = agora + timedelta(hours=h)
        distancia = abs(h - hora_pico)
        intensidade = max(0.0, 1 - distancia / 4)  # pico estreito de ~4 horas

        chuva = round(pico_chuva * intensidade + rng.uniform(0, 0.6), 1)
        rajada = round(
            pico_rajada * intensidade + (pico_rajada * 0.25) + rng.uniform(0, 4), 1
        )
        if cenario == "geada":
            # noite fria: minima nas madrugadas
            hora_do_dia = instante.hour
            temperatura = temp_base if 0 <= hora_do_dia <= 7 else temp_pico
            if distancia <= 2 and 0 <= hora_do_dia <= 7:
                temperatura = 0.5
        elif cenario == "onda_calor":
            temperatura = round(temp_base + (temp_pico - temp_base) * intensidade, 1)
        else:
            temperatura = round(temp_base + rng.uniform(-1.5, 2.5), 1)

        janelas.append(
            JanelaPrevisao(
                instante=instante,
                temperatura_c=float(temperatura),
                precipitacao_mm=chuva,
                rajada_vento_kmh=rajada,
                codigo_tempo=codigo if distancia <= 2 else 2,
            )
        )

    return PrevisaoLocal(
        chave_local=segurado.chave_local,
        cidade=segurado.cidade,
        uf=segurado.uf,
        latitude=segurado.latitude,
        longitude=segurado.longitude,
        fonte=f"Simulacao interna ({CENARIOS[cenario][0]})",
        coletado_em=datetime.now(tz=config.FUSO),
        janelas=janelas,
    )
