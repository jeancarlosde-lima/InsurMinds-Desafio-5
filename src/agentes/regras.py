"""
Agente 3 - Regras de negocio.

Responsabilidade unica: decidir QUEM deve ser notificado, cruzando os eventos
identificados com a carteira de segurados.

Tres regras compoem a politica:

R1 - Pertinencia por ramo: cada ramo tem uma severidade minima por tipo de
     evento (config.MATRIZ_REGRAS). Granizo importa muito para automovel e
     lavoura; chuva moderada importa para residencial, mas nao para automovel.

R2 - Antecedencia util: o evento precisa estar dentro da janela configurada
     (padrao 48h). Avisar com antecedencia demais gera ruido; avisar tarde
     demais nao permite acao preventiva.

R3 - Cooldown / anti-spam: o mesmo segurado nao recebe o mesmo tipo de alerta
     duas vezes dentro de COOLDOWN_H horas. O historico fica em outputs/.

Toda decisao - inclusive a de NAO notificar - e registrada com o motivo, o que
torna a politica auditavel.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from src import config
from src.models import Decisao, EventoClimatico, Segurado, Severidade


def _prioridade(severidade: Severidade) -> str:
    return {
        Severidade.BAIXA: "informativa",
        Severidade.MODERADA: "atencao",
        Severidade.ALTA: "urgente",
        Severidade.SEVERA: "urgente",
    }[severidade]


class AgenteRegras:
    """Aplica a politica de comunicacao sobre eventos x carteira."""

    nome = "AgenteRegras"

    def __init__(self, logger=None, usar_historico: bool = True) -> None:
        self.log = logger or (lambda _msg: None)
        self.usar_historico = usar_historico
        self.historico = self._carregar_historico()

    # -- Historico (cooldown) ----------------------------------------------
    def _carregar_historico(self) -> list[dict]:
        if not self.usar_historico or not config.ARQ_HISTORICO.exists():
            return []
        try:
            return json.loads(config.ARQ_HISTORICO.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _em_cooldown(self, id_segurado: str, tipo: str) -> bool:
        if not self.usar_historico:
            return False
        limite = datetime.now(tz=config.FUSO) - timedelta(hours=config.COOLDOWN_H)
        for registro in self.historico:
            if registro.get("id_segurado") != id_segurado:
                continue
            if registro.get("tipo_evento") != tipo:
                continue
            try:
                enviado = datetime.fromisoformat(registro["enviado_em"])
            except Exception:
                continue
            if enviado.tzinfo is None:
                enviado = enviado.replace(tzinfo=config.FUSO)
            if enviado >= limite:
                return True
        return False

    # -- Execucao -----------------------------------------------------------
    def executar(
        self, segurados: list[Segurado], eventos: list[EventoClimatico]
    ) -> list[Decisao]:
        decisoes: list[Decisao] = []
        agora = datetime.now(tz=config.FUSO)

        eventos_por_local: dict[str, list[EventoClimatico]] = {}
        for evento in eventos:
            eventos_por_local.setdefault(evento.chave_local, []).append(evento)

        for segurado in segurados:
            for evento in eventos_por_local.get(segurado.chave_local, []):
                decisoes.append(self._avaliar(segurado, evento, agora))

        aprovadas = [d for d in decisoes if d.notificar]
        self.log(
            f"[{self.nome}] {len(decisoes)} pares segurado/evento avaliados -> "
            f"{len(aprovadas)} notificacoes aprovadas, "
            f"{len(decisoes) - len(aprovadas)} suprimidas"
        )
        return decisoes

    def _avaliar(
        self, segurado: Segurado, evento: EventoClimatico, agora: datetime
    ) -> Decisao:
        base = {
            "id_segurado": segurado.id_segurado,
            "nome": segurado.nome,
            "local": segurado.local,
            "ramo": segurado.ramo,
            "tipo_evento": evento.tipo,
            "severidade": evento.severidade,
            "evento": evento,
        }

        # R1 - pertinencia por ramo
        politica = config.MATRIZ_REGRAS.get(segurado.ramo.value, {})
        minima = politica.get(evento.tipo.value)
        if minima is None:
            return Decisao(
                **base,
                notificar=False,
                regra="R1-pertinencia",
                motivo=(
                    f"O ramo {segurado.ramo.value} nao possui politica de comunicacao "
                    f"para eventos do tipo {evento.tipo.value}."
                ),
            )

        if evento.severidade.nivel < Severidade(minima).nivel:
            return Decisao(
                **base,
                notificar=False,
                regra="R1-severidade",
                motivo=(
                    f"Severidade {evento.severidade.value} abaixo do minimo "
                    f"'{minima}' exigido para {segurado.ramo.value}/{evento.tipo.value}."
                ),
            )

        # R2 - antecedencia util
        horas = (evento.inicio - agora).total_seconds() / 3600
        if horas > config.JANELA_ANTECEDENCIA_H:
            return Decisao(
                **base,
                notificar=False,
                regra="R2-antecedencia",
                motivo=(
                    f"Evento previsto para daqui a {horas:.0f}h, fora da janela de "
                    f"{config.JANELA_ANTECEDENCIA_H}h."
                ),
            )

        # R3 - cooldown
        if self._em_cooldown(segurado.id_segurado, evento.tipo.value):
            return Decisao(
                **base,
                notificar=False,
                regra="R3-cooldown",
                motivo=(
                    f"Segurado ja recebeu alerta de {evento.tipo.value} nas ultimas "
                    f"{config.COOLDOWN_H}h."
                ),
            )

        orientacoes = config.ORIENTACOES.get(
            (segurado.ramo.value, evento.tipo.value),
            ["Acione a assistência 24h em caso de sinistro"],
        )
        return Decisao(
            **base,
            notificar=True,
            regra="R1+R2+R3",
            motivo=(
                f"Evento {evento.tipo.value} ({evento.severidade.value}) atinge o minimo "
                f"'{minima}' do ramo {segurado.ramo.value} e ocorre em {horas:.0f}h."
            ),
            prioridade=_prioridade(evento.severidade),
            orientacoes=list(orientacoes),
        )
