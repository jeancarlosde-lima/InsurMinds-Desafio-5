"""
Configuracao central do projeto.

Todos os parametros de negocio (limiares climaticos, janela de antecedencia,
cooldown de notificacao) ficam concentrados aqui, para que ajustar a politica
de comunicacao nao exija alterar o codigo dos agentes.

Credenciais NUNCA sao versionadas: sao lidas do arquivo .env (veja .env.example).
"""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "data"
DIR_SAIDA = RAIZ / "outputs"
DIR_SAIDA.mkdir(exist_ok=True)

ARQ_SEGURADOS = DIR_DADOS / "segurados.csv"
ARQ_SIMULACAO = DIR_DADOS / "simulacao_meteorologia.json"
ARQ_HISTORICO = DIR_SAIDA / "historico_notificacoes.json"

FUSO = ZoneInfo("America/Sao_Paulo")

# ---------------------------------------------------------------------------
# Fonte de dados meteorologicos (API publica, sem necessidade de chave)
# ---------------------------------------------------------------------------
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_TIMEOUT = 20  # segundos
FORECAST_DIAS = 3

# ---------------------------------------------------------------------------
# LLM (mensagens personalizadas)
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
MODELO_LLM = os.getenv("MODELO_LLM", "gemini-3.6-flash").strip()
TEMPERATURA_LLM = float(os.getenv("TEMPERATURA_LLM", "0.4"))

# ---------------------------------------------------------------------------
# Parametros de negocio
# ---------------------------------------------------------------------------
# Antecedencia maxima: so comunicamos eventos previstos para as proximas N horas.
JANELA_ANTECEDENCIA_H = int(os.getenv("JANELA_ANTECEDENCIA_H", "48"))

# Cooldown: nao repetir o mesmo tipo de alerta para o mesmo segurado dentro de N horas.
COOLDOWN_H = int(os.getenv("COOLDOWN_H", "24"))

# Limiares por tipo de evento -> severidade.
# Fontes de referencia: escalas de aviso do INMET (chuva e vento) e praticas de
# subscricao para granizo/geada. Os valores estao documentados no relatorio.
LIMIARES = {
    "chuva_intensa": {  # mm acumulados em 1 hora
        "baixa": 5.0,
        "moderada": 10.0,
        "alta": 20.0,
        "severa": 35.0,
    },
    "vento_forte": {  # rajada em km/h
        "baixa": 40.0,
        "moderada": 55.0,
        "alta": 75.0,
        "severa": 95.0,
    },
    "onda_calor": {  # temperatura maxima em C
        "baixa": 32.0,
        "moderada": 35.0,
        "alta": 38.0,
        "severa": 40.0,
    },
    "geada": {  # temperatura minima em C (quanto menor, pior)
        "baixa": 5.0,
        "moderada": 3.0,
        "alta": 1.0,
        "severa": -1.0,
    },
}

# Codigos WMO (padrao usado pelo Open-Meteo) relevantes para o negocio.
WMO_TEMPESTADE = {95}
WMO_GRANIZO = {96, 99}

# Severidade minima exigida por ramo e por tipo de evento.
# Este dicionario e a materializacao da politica de comunicacao da seguradora:
# ramos diferentes tem sensibilidades diferentes ao mesmo fenomeno.
MATRIZ_REGRAS = {
    "residencial": {
        "chuva_intensa": "moderada",
        "vento_forte": "moderada",
        "granizo": "baixa",
        "tempestade": "alta",
    },
    "automovel": {
        "granizo": "baixa",
        "chuva_intensa": "alta",
        "vento_forte": "alta",
        "tempestade": "moderada",
    },
    "agricola": {
        "granizo": "baixa",
        "geada": "baixa",
        "onda_calor": "moderada",
        "chuva_intensa": "alta",
        "vento_forte": "alta",
    },
    "empresarial": {
        "chuva_intensa": "alta",
        "vento_forte": "moderada",
        "tempestade": "alta",
    },
}

# Orientacoes preventivas por ramo/evento. Servem de insumo factual para o LLM:
# a IA cuida do tom e da personalizacao, o conteudo tecnico vem do negocio.
ORIENTACOES = {
    ("residencial", "chuva_intensa"): [
        "Desobstrua calhas, ralos e grelhas antes do início da chuva",
        "Retire objetos e documentos do chão de garagens e áreas rebaixadas",
        "Evite deixar equipamentos elétricos ligados na tomada durante o temporal",
    ],
    ("residencial", "vento_forte"): [
        "Recolha vasos, antenas, toldos e móveis de área externa",
        "Feche janelas e persianas e afaste-se de vidraças",
        "Verifique telhas soltas e galhos próximos ao telhado",
    ],
    ("residencial", "granizo"): [
        "Proteja claraboias, telhas translúcidas e coberturas de policarbonato",
        "Recolha veículos e bicicletas para área coberta",
        "Evite permanecer sob estruturas leves durante a queda de granizo",
    ],
    ("residencial", "tempestade"): [
        "Desligue aparelhos sensíveis da tomada para evitar danos elétricos",
        "Tenha lanterna e carregador portátil à mão em caso de queda de energia",
    ],
    ("automovel", "granizo"): [
        "Estacione em garagem coberta ou subsolo sempre que possível",
        "Na impossibilidade, use cobertura acolchoada e evite áreas abertas",
        "Não estacione sob árvores: galhos caem com o impacto do granizo",
    ],
    ("automovel", "chuva_intensa"): [
        "Evite atravessar alagamentos: 30 cm de água já arrastam um carro",
        "Reduza a velocidade e aumente a distância de segurança",
        "Se a visibilidade cair muito, pare em local seguro com o pisca-alerta",
    ],
    ("automovel", "vento_forte"): [
        "Evite estacionar sob árvores, placas e estruturas metálicas",
        "Segure firme o volante em trechos abertos e ao ultrapassar caminhões",
    ],
    ("automovel", "tempestade"): [
        "Prefira adiar deslocamentos durante o pico da tempestade",
        "Mantenha os faróis baixos ligados para ser visto",
    ],
    ("agricola", "granizo"): [
        "Antecipe a colheita de talhões em ponto de maturação, se viável",
        "Registre com fotos e data a situação atual da lavoura",
        "Acione o corretor para avaliação prévia em caso de dano",
    ],
    ("agricola", "geada"): [
        "Priorize a irrigação noturna nas áreas mais sensíveis",
        "Evite aplicações foliares nas horas que antecedem a geada",
        "Monitore as áreas de baixada, onde o ar frio se acumula",
    ],
    ("agricola", "onda_calor"): [
        "Reprograme pulverizações para o início da manhã ou o fim da tarde",
        "Reforce o manejo de irrigação nos estágios críticos da cultura",
        "Redobre a atenção com risco de incêndio em áreas de palhada seca",
    ],
    ("agricola", "chuva_intensa"): [
        "Verifique terraços, bacias de contenção e carreadores",
        "Proteja insumos e grãos armazenados contra a umidade",
    ],
    ("agricola", "vento_forte"): [
        "Suspenda pulverizações: há risco de deriva",
        "Verifique a fixação de estruturas, silos e coberturas",
    ],
    ("empresarial", "chuva_intensa"): [
        "Eleve estoques e equipamentos do nível do piso",
        "Confira bombas de recalque e sistemas de drenagem",
        "Revise o plano de continuidade para eventual interrupção de acesso",
    ],
    ("empresarial", "vento_forte"): [
        "Verifique a fixação de letreiros, toldos e coberturas metálicas",
        "Recolha materiais leves do pátio e das áreas externas",
    ],
    ("empresarial", "tempestade"): [
        "Teste nobreaks e geradores antes do evento",
        "Oriente a equipe sobre o procedimento de evacuação e desligamento",
    ],
}

CANAL_LIMITES = {
    "sms": 320,
    "whatsapp": 700,
    "email": 1400,
}

TELEFONE_ASSISTENCIA = "0800 000 0000"
NOME_SEGURADORA = "Seguradora InsurMinds"
