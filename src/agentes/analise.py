"""
Agente 2 - Analise.

Responsabilidade unica: transformar series horarias de previsao em EVENTOS
CLIMATICOS relevantes, com tipo, severidade, janela de ocorrencia e
justificativa numerica.

A deteccao e deterministica e baseada em limiares (config.LIMIARES), e nao em
LLM. Essa escolha e proposital: a decisao de acionar um segurado precisa ser
auditavel e reproduzivel. O LLM entra depois, apenas na camada de redacao.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src import config
from src.models import EventoClimatico, PrevisaoLocal, Severidade, TipoEvento


def _classificar(valor: float, limiares: dict[str, float], invertido: bool = False) -> Severidade | None:
    """Converte um valor numerico em severidade conforme a escala configurada."""
    ordem = ["severa", "alta", "moderada", "baixa"]
    for nivel in ordem:
        limite = limiares[nivel]
        if (not invertido and valor >= limite) or (invertido and valor <= limite):
            return Severidade(nivel)
    return None


class AgenteAnalise:
    """Identifica eventos climaticos relevantes em cada localidade."""

    nome = "AgenteAnalise"

    def __init__(self, logger=None) -> None:
        self.log = logger or (lambda _msg: None)

    def executar(self, previsoes: list[PrevisaoLocal]) -> list[EventoClimatico]:
        eventos: list[EventoClimatico] = []
        agora = datetime.now(tz=config.FUSO)
        limite = agora + timedelta(hours=config.JANELA_ANTECEDENCIA_H)

        for previsao in previsoes:
            janelas = [j for j in previsao.janelas if agora <= j.instante <= limite]
            if not janelas:
                self.log(f"[{self.nome}] {previsao.cidade}: sem janelas na antecedencia configurada")
                continue

            encontrados = []
            encontrados += self._detectar_chuva(previsao, janelas)
            encontrados += self._detectar_vento(previsao, janelas)
            encontrados += self._detectar_codigos(previsao, janelas)
            encontrados += self._detectar_temperatura(previsao, janelas)

            if encontrados:
                resumo = ", ".join(f"{e.tipo.value}/{e.severidade.value}" for e in encontrados)
                self.log(f"[{self.nome}] {previsao.cidade}/{previsao.uf}: {resumo}")
            else:
                self.log(f"[{self.nome}] {previsao.cidade}/{previsao.uf}: nenhum evento relevante")
            eventos += encontrados

        self.log(f"[{self.nome}] total de eventos relevantes: {len(eventos)}")
        return eventos

    # -- Detectores individuais --------------------------------------------
    def _detectar_chuva(self, previsao: PrevisaoLocal, janelas) -> list[EventoClimatico]:
        pico = max(janelas, key=lambda j: j.precipitacao_mm or 0.0)
        valor = pico.precipitacao_mm or 0.0
        severidade = _classificar(valor, config.LIMIARES["chuva_intensa"])
        if not severidade:
            return []
        afetadas = [j for j in janelas if (j.precipitacao_mm or 0) >= config.LIMIARES["chuva_intensa"]["baixa"]]
        acumulado = round(sum(j.precipitacao_mm or 0 for j in afetadas), 1)
        return [
            EventoClimatico(
                chave_local=previsao.chave_local,
                cidade=previsao.cidade,
                uf=previsao.uf,
                tipo=TipoEvento.CHUVA_INTENSA,
                severidade=severidade,
                inicio=afetadas[0].instante,
                fim=afetadas[-1].instante,
                metrica="precipitacao horaria maxima",
                valor=round(valor, 1),
                unidade="mm/h",
                justificativa=(
                    f"Pico de {valor:.1f} mm/h previsto para {pico.instante:%d/%m às %Hh}; "
                    f"acumulado de {acumulado} mm no episódio."
                ),
            )
        ]

    def _detectar_vento(self, previsao: PrevisaoLocal, janelas) -> list[EventoClimatico]:
        pico = max(janelas, key=lambda j: j.rajada_vento_kmh or 0.0)
        valor = pico.rajada_vento_kmh or 0.0
        severidade = _classificar(valor, config.LIMIARES["vento_forte"])
        if not severidade:
            return []
        afetadas = [j for j in janelas if (j.rajada_vento_kmh or 0) >= config.LIMIARES["vento_forte"]["baixa"]]
        return [
            EventoClimatico(
                chave_local=previsao.chave_local,
                cidade=previsao.cidade,
                uf=previsao.uf,
                tipo=TipoEvento.VENTO_FORTE,
                severidade=severidade,
                inicio=afetadas[0].instante,
                fim=afetadas[-1].instante,
                metrica="rajada maxima de vento",
                valor=round(valor, 1),
                unidade="km/h",
                justificativa=(
                    f"Rajadas de até {valor:.0f} km/h previstas para {pico.instante:%d/%m às %Hh}."
                ),
            )
        ]

    def _detectar_codigos(self, previsao: PrevisaoLocal, janelas) -> list[EventoClimatico]:
        """Granizo e tempestade eletrica vem dos codigos de tempo WMO."""
        eventos: list[EventoClimatico] = []

        granizo = [j for j in janelas if (j.codigo_tempo or 0) in config.WMO_GRANIZO]
        if granizo:
            severidade = Severidade.SEVERA if len(granizo) >= 3 else Severidade.ALTA
            eventos.append(
                EventoClimatico(
                    chave_local=previsao.chave_local,
                    cidade=previsao.cidade,
                    uf=previsao.uf,
                    tipo=TipoEvento.GRANIZO,
                    severidade=severidade,
                    inicio=granizo[0].instante,
                    fim=granizo[-1].instante,
                    metrica="codigo de tempo WMO",
                    valor=float(granizo[0].codigo_tempo or 0),
                    unidade="codigo",
                    justificativa=(
                        f"Código WMO {granizo[0].codigo_tempo} (tempestade com granizo) previsto "
                        f"em {len(granizo)} hora(s), a partir de {granizo[0].instante:%d/%m às %Hh}."
                    ),
                )
            )

        tempestade = [j for j in janelas if (j.codigo_tempo or 0) in config.WMO_TEMPESTADE]
        if tempestade:
            severidade = Severidade.ALTA if len(tempestade) >= 3 else Severidade.MODERADA
            eventos.append(
                EventoClimatico(
                    chave_local=previsao.chave_local,
                    cidade=previsao.cidade,
                    uf=previsao.uf,
                    tipo=TipoEvento.TEMPESTADE,
                    severidade=severidade,
                    inicio=tempestade[0].instante,
                    fim=tempestade[-1].instante,
                    metrica="codigo de tempo WMO",
                    valor=float(tempestade[0].codigo_tempo or 0),
                    unidade="codigo",
                    justificativa=(
                        f"Tempestade com descargas elétricas prevista a partir de "
                        f"{tempestade[0].instante:%d/%m às %Hh}."
                    ),
                )
            )
        return eventos

    def _detectar_temperatura(self, previsao: PrevisaoLocal, janelas) -> list[EventoClimatico]:
        eventos: list[EventoClimatico] = []
        temperaturas = [j for j in janelas if j.temperatura_c is not None]
        if not temperaturas:
            return eventos

        mais_quente = max(temperaturas, key=lambda j: j.temperatura_c)
        severidade_calor = _classificar(mais_quente.temperatura_c, config.LIMIARES["onda_calor"])
        if severidade_calor:
            eventos.append(
                EventoClimatico(
                    chave_local=previsao.chave_local,
                    cidade=previsao.cidade,
                    uf=previsao.uf,
                    tipo=TipoEvento.ONDA_CALOR,
                    severidade=severidade_calor,
                    inicio=mais_quente.instante,
                    fim=mais_quente.instante,
                    metrica="temperatura maxima",
                    valor=round(mais_quente.temperatura_c, 1),
                    unidade="C",
                    justificativa=(
                        f"Máxima de {mais_quente.temperatura_c:.1f} °C prevista para "
                        f"{mais_quente.instante:%d/%m às %Hh}."
                    ),
                )
            )

        mais_frio = min(temperaturas, key=lambda j: j.temperatura_c)
        severidade_frio = _classificar(
            mais_frio.temperatura_c, config.LIMIARES["geada"], invertido=True
        )
        if severidade_frio:
            eventos.append(
                EventoClimatico(
                    chave_local=previsao.chave_local,
                    cidade=previsao.cidade,
                    uf=previsao.uf,
                    tipo=TipoEvento.GEADA,
                    severidade=severidade_frio,
                    inicio=mais_frio.instante,
                    fim=mais_frio.instante,
                    metrica="temperatura minima",
                    valor=round(mais_frio.temperatura_c, 1),
                    unidade="C",
                    justificativa=(
                        f"Mínima de {mais_frio.temperatura_c:.1f} °C prevista para "
                        f"{mais_frio.instante:%d/%m às %Hh}, com risco de geada."
                    ),
                )
            )
        return eventos
