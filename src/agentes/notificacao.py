"""
Agente 5 - Notificacao.

Responsabilidade unica: SIMULAR o despacho das mensagens pelo canal preferido de
cada segurado e registrar o resultado.

Nao ha envio real de SMS, e-mail ou push - o desafio pede explicitamente apenas
a simulacao. O agente emula o comportamento de um gateway de mensageria:
  - gera um identificador de protocolo por notificacao;
  - registra canal, horario e status simulado;
  - grava a fila em outputs/ (JSON + CSV) para inspecao;
  - atualiza o historico usado pela regra de cooldown (R3).

Trocar esta classe por uma integracao real (Twilio, SendGrid, WhatsApp Business)
nao exigiria mudar nenhum outro agente.
"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime

from src import config
from src.models import Mensagem, Notificacao, Segurado


class AgenteNotificacao:
    """Simula o envio e persiste o resultado."""

    nome = "AgenteNotificacao"

    def __init__(self, logger=None, registrar_historico: bool = True) -> None:
        self.log = logger or (lambda _msg: None)
        self.registrar_historico = registrar_historico

    def executar(
        self, mensagens: list[Mensagem], segurados: dict[str, Segurado]
    ) -> list[Notificacao]:
        agora = datetime.now(tz=config.FUSO)
        notificacoes: list[Notificacao] = []

        for mensagem in mensagens:
            segurado = segurados[mensagem.id_segurado]
            protocolo = f"NTF-{agora:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
            notificacoes.append(
                Notificacao(
                    id_notificacao=protocolo,
                    id_segurado=segurado.id_segurado,
                    nome=segurado.nome,
                    local=segurado.local,
                    ramo=segurado.ramo,
                    canal=mensagem.canal,
                    tipo_evento=mensagem.tipo_evento,
                    severidade=mensagem.severidade,
                    prioridade=mensagem.prioridade,
                    assunto=mensagem.assunto,
                    mensagem=mensagem.corpo,
                    gerado_por=mensagem.gerado_por,
                    status_simulado="SIMULADO_ENVIADO",
                    enviado_em=agora,
                )
            )
            self.log(
                f"[{self.nome}] {protocolo} -> {segurado.nome} ({segurado.local}) "
                f"via {mensagem.canal.value} | {mensagem.tipo_evento.value}"
            )

        if notificacoes:
            self._persistir(notificacoes, agora)
            if self.registrar_historico:
                self._atualizar_historico(notificacoes)
        else:
            self.log(f"[{self.nome}] nenhuma notificacao a despachar nesta execucao")

        return notificacoes

    # -- Persistencia -------------------------------------------------------
    def _persistir(self, notificacoes: list[Notificacao], agora: datetime) -> None:
        carimbo = agora.strftime("%Y%m%d_%H%M%S")
        arquivo_json = config.DIR_SAIDA / f"notificacoes_{carimbo}.json"
        arquivo_csv = config.DIR_SAIDA / f"notificacoes_{carimbo}.csv"

        arquivo_json.write_text(
            json.dumps(
                [n.model_dump(mode="json") for n in notificacoes],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        with arquivo_csv.open("w", newline="", encoding="utf-8-sig") as destino:
            campos = [
                "id_notificacao",
                "id_segurado",
                "nome",
                "local",
                "ramo",
                "canal",
                "tipo_evento",
                "severidade",
                "prioridade",
                "assunto",
                "mensagem",
                "gerado_por",
                "status_simulado",
                "enviado_em",
            ]
            escritor = csv.DictWriter(destino, fieldnames=campos, delimiter=";")
            escritor.writeheader()
            for notificacao in notificacoes:
                linha = notificacao.model_dump(mode="json")
                linha["mensagem"] = linha["mensagem"].replace("\n", " | ")
                escritor.writerow({campo: linha.get(campo) for campo in campos})

        self.log(f"[{self.nome}] fila gravada em {arquivo_json.name} e {arquivo_csv.name}")

    def _atualizar_historico(self, notificacoes: list[Notificacao]) -> None:
        historico = []
        if config.ARQ_HISTORICO.exists():
            try:
                historico = json.loads(config.ARQ_HISTORICO.read_text(encoding="utf-8"))
            except Exception:
                historico = []
        historico += [
            {
                "id_segurado": n.id_segurado,
                "tipo_evento": n.tipo_evento.value,
                "enviado_em": n.enviado_em.isoformat(),
            }
            for n in notificacoes
        ]
        config.ARQ_HISTORICO.write_text(
            json.dumps(historico[-500:], ensure_ascii=False, indent=2), encoding="utf-8"
        )
