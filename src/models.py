"""
Modelos de dados do projeto.

Estes modelos funcionam como o "contrato" entre os agentes: cada agente recebe
um tipo bem definido e devolve outro tipo bem definido. Isso mantém as etapas
de coleta, analise, decisao e comunicacao desacopladas umas das outras.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumeracoes de dominio
# ---------------------------------------------------------------------------
class RamoSeguro(str, Enum):
    RESIDENCIAL = "residencial"
    AUTOMOVEL = "automovel"
    AGRICOLA = "agricola"
    EMPRESARIAL = "empresarial"


class TipoEvento(str, Enum):
    CHUVA_INTENSA = "chuva_intensa"
    GRANIZO = "granizo"
    VENTO_FORTE = "vento_forte"
    TEMPESTADE = "tempestade"
    ONDA_CALOR = "onda_calor"
    GEADA = "geada"


class Severidade(str, Enum):
    BAIXA = "baixa"
    MODERADA = "moderada"
    ALTA = "alta"
    SEVERA = "severa"

    @property
    def nivel(self) -> int:
        return {"baixa": 1, "moderada": 2, "alta": 3, "severa": 4}[self.value]


class Canal(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------
class Segurado(BaseModel):
    """Cliente da seguradora (base simulada, sem dados reais)."""

    id_segurado: str
    nome: str
    cidade: str
    uf: str
    latitude: float
    longitude: float
    ramo: RamoSeguro
    apolice: str
    canal: Canal
    observacao: str = ""

    @property
    def local(self) -> str:
        return f"{self.cidade}/{self.uf}"

    @property
    def chave_local(self) -> str:
        """Chave usada para agrupar consultas a API por coordenada."""
        return f"{self.latitude:.2f},{self.longitude:.2f}"


class JanelaPrevisao(BaseModel):
    """Uma janela horaria da previsao meteorologica."""

    instante: datetime
    temperatura_c: float | None = None
    precipitacao_mm: float | None = None
    rajada_vento_kmh: float | None = None
    codigo_tempo: int | None = None


class PrevisaoLocal(BaseModel):
    """Previsao consolidada de um ponto geografico."""

    chave_local: str
    cidade: str
    uf: str
    latitude: float
    longitude: float
    fonte: str
    coletado_em: datetime
    janelas: list[JanelaPrevisao] = Field(default_factory=list)

    def resumo(self) -> dict:
        precipitacoes = [j.precipitacao_mm or 0.0 for j in self.janelas]
        rajadas = [j.rajada_vento_kmh or 0.0 for j in self.janelas]
        temperaturas = [j.temperatura_c for j in self.janelas if j.temperatura_c is not None]
        return {
            "local": f"{self.cidade}/{self.uf}",
            "janelas": len(self.janelas),
            "chuva_max_mm_h": round(max(precipitacoes), 1) if precipitacoes else 0.0,
            "chuva_total_mm": round(sum(precipitacoes), 1) if precipitacoes else 0.0,
            "rajada_max_kmh": round(max(rajadas), 1) if rajadas else 0.0,
            "temp_max_c": round(max(temperaturas), 1) if temperaturas else None,
            "temp_min_c": round(min(temperaturas), 1) if temperaturas else None,
        }


class EventoClimatico(BaseModel):
    """Evento relevante identificado pelo agente de analise."""

    chave_local: str
    cidade: str
    uf: str
    tipo: TipoEvento
    severidade: Severidade
    inicio: datetime
    fim: datetime
    metrica: str
    valor: float
    unidade: str
    justificativa: str

    @property
    def horas_ate_evento(self) -> float:
        delta = self.inicio - datetime.now(tz=self.inicio.tzinfo)
        return round(delta.total_seconds() / 3600, 1)


class Decisao(BaseModel):
    """Resultado da aplicacao das regras de negocio para um par segurado/evento."""

    id_segurado: str
    nome: str
    local: str
    ramo: RamoSeguro
    tipo_evento: TipoEvento
    severidade: Severidade
    notificar: bool
    regra: str
    motivo: str
    prioridade: Literal["informativa", "atencao", "urgente"] = "informativa"
    orientacoes: list[str] = Field(default_factory=list)
    evento: EventoClimatico | None = None


class Mensagem(BaseModel):
    """Mensagem personalizada gerada pelo agente de redacao."""

    id_segurado: str
    nome: str
    canal: Canal
    assunto: str | None = None
    corpo: str
    gerado_por: str
    tipo_evento: TipoEvento
    severidade: Severidade
    prioridade: str


class Notificacao(BaseModel):
    """Registro da simulacao de envio."""

    id_notificacao: str
    id_segurado: str
    nome: str
    local: str
    ramo: RamoSeguro
    canal: Canal
    tipo_evento: TipoEvento
    severidade: Severidade
    prioridade: str
    assunto: str | None
    mensagem: str
    gerado_por: str
    status_simulado: str
    enviado_em: datetime


class ResultadoPipeline(BaseModel):
    """Saida completa de uma execucao, usada pela interface e pelos relatorios."""

    executado_em: datetime
    modo_dados: str
    modo_llm: str
    previsoes: list[PrevisaoLocal] = Field(default_factory=list)
    eventos: list[EventoClimatico] = Field(default_factory=list)
    decisoes: list[Decisao] = Field(default_factory=list)
    mensagens: list[Mensagem] = Field(default_factory=list)
    notificacoes: list[Notificacao] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)

    @property
    def total_notificados(self) -> int:
        return len(self.notificacoes)

    @property
    def total_suprimidos(self) -> int:
        return len([d for d in self.decisoes if not d.notificar])
