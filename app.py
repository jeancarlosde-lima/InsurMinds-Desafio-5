"""
Interface de demonstracao (Streamlit).

A interface existe para atender ao requisito "permitir demonstrar o fluxo
completo da solucao": cada aba corresponde a uma etapa do pipeline, na ordem em
que ela acontece, incluindo as decisoes de NAO notificar.

Execucao:  streamlit run app.py
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src import config
from src.orquestrador import carregar_segurados, executar_pipeline

st.set_page_config(
    page_title="InsurMinds | Comunicacao Proativa",
    page_icon="⛈️",
    layout="wide",
)

st.title("Comunicacao Proativa com o Segurado")
st.caption(
    "InsurMinds - Desafio 5 | fluxo multiagente: coleta meteorologica -> analise de eventos "
    "-> regras de negocio -> geracao de mensagens com IA -> simulacao de envio"
)

# ---------------------------------------------------------------------------
# Barra lateral: parametros da execucao
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Parametros")
    modo_dados = st.radio(
        "Fonte dos dados meteorologicos",
        options=["api", "simulacao"],
        format_func=lambda v: (
            "API publica Open-Meteo" if v == "api" else "Cenarios simulados (offline)"
        ),
        help=(
            "A simulacao gera cenarios sinteticos com a mesma estrutura da API, "
            "para demonstrar o fluxo mesmo em dias de tempo estavel."
        ),
    )
    usar_llm = st.toggle(
        "Gerar mensagens com IA Generativa",
        value=bool(config.GOOGLE_API_KEY),
        help="Requer GOOGLE_API_KEY no arquivo .env. Sem chave, o sistema usa templates.",
    )
    usar_historico = st.toggle(
        "Aplicar regra de cooldown (R3)",
        value=False,
        help="Evita reenviar o mesmo tipo de alerta ao mesmo segurado em 24h.",
    )

    st.divider()
    st.subheader("Politica vigente")
    st.write(f"Antecedencia maxima: **{config.JANELA_ANTECEDENCIA_H}h**")
    st.write(f"Cooldown: **{config.COOLDOWN_H}h**")
    if config.GOOGLE_API_KEY:
        st.success("Chave do modelo de linguagem detectada")
    else:
        st.warning("Sem GOOGLE_API_KEY: as mensagens usarao template")

    executar = st.button("Executar fluxo completo", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Carteira
# ---------------------------------------------------------------------------
segurados = carregar_segurados()

if executar:
    with st.spinner("Executando os agentes..."):
        st.session_state["resultado"] = executar_pipeline(
            modo_dados=modo_dados,
            usar_llm=usar_llm,
            usar_historico=usar_historico,
            segurados=segurados,
        )

resultado = st.session_state.get("resultado")

if resultado is None:
    st.info(
        "Configure os parametros na barra lateral e clique em **Executar fluxo completo**. "
        f"A carteira simulada possui {len(segurados)} segurados em "
        f"{len({s.chave_local for s in segurados})} localidades."
    )
    st.subheader("Carteira de segurados")
    st.dataframe(
        pd.DataFrame([s.model_dump() for s in segurados])[
            ["id_segurado", "nome", "cidade", "uf", "ramo", "canal", "observacao"]
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.stop()

# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Localidades monitoradas", len(resultado.previsoes))
col2.metric("Eventos identificados", len(resultado.eventos))
col3.metric("Notificacoes simuladas", resultado.total_notificados)
col4.metric("Decisoes suprimidas", resultado.total_suprimidos)

st.caption(
    f"Fonte: {resultado.modo_dados} | Redacao: {resultado.modo_llm} | "
    f"Execucao: {resultado.executado_em:%d/%m/%Y %H:%M:%S}"
)

abas = st.tabs(
    [
        "1. Coleta",
        "2. Eventos",
        "3. Regras de negocio",
        "4. Mensagens",
        "5. Envio simulado",
        "Log de execucao",
    ]
)

# 1. Coleta ------------------------------------------------------------------
with abas[0]:
    st.subheader("Previsao coletada por localidade")
    if resultado.previsoes:
        st.dataframe(
            pd.DataFrame([p.resumo() | {"fonte": p.fonte} for p in resultado.previsoes]),
            use_container_width=True,
            hide_index=True,
        )
        escolha = st.selectbox(
            "Detalhar serie horaria",
            options=[f"{p.cidade}/{p.uf}" for p in resultado.previsoes],
        )
        previsao = next(
            p for p in resultado.previsoes if f"{p.cidade}/{p.uf}" == escolha
        )
        serie = pd.DataFrame([j.model_dump() for j in previsao.janelas])
        if not serie.empty:
            serie["instante"] = pd.to_datetime(serie["instante"]).dt.tz_localize(None)
            st.line_chart(
                serie.set_index("instante")[["precipitacao_mm", "rajada_vento_kmh"]]
            )
            st.dataframe(serie, use_container_width=True, hide_index=True)
    else:
        st.warning("Nenhuma previsao coletada.")

# 2. Eventos -----------------------------------------------------------------
with abas[1]:
    st.subheader("Eventos climaticos relevantes")
    if resultado.eventos:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Local": f"{e.cidade}/{e.uf}",
                        "Evento": e.tipo.value,
                        "Severidade": e.severidade.value,
                        "Inicio": e.inicio.strftime("%d/%m %H:%M"),
                        "Fim": e.fim.strftime("%d/%m %H:%M"),
                        "Metrica": e.metrica,
                        "Valor": f"{e.valor} {e.unidade}",
                        "Justificativa": e.justificativa,
                    }
                    for e in resultado.eventos
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhum evento atingiu os limiares configurados nesta execucao.")

# 3. Regras ------------------------------------------------------------------
with abas[2]:
    st.subheader("Decisoes por segurado")
    st.caption(
        "Cada linha mostra a regra aplicada. As decisoes negativas tambem sao registradas, "
        "o que torna a politica auditavel."
    )
    if resultado.decisoes:
        tabela = pd.DataFrame(
            [
                {
                    "Segurado": d.nome,
                    "Local": d.local,
                    "Ramo": d.ramo.value,
                    "Evento": d.tipo_evento.value,
                    "Severidade": d.severidade.value,
                    "Notificar": "Sim" if d.notificar else "Nao",
                    "Regra": d.regra,
                    "Motivo": d.motivo,
                }
                for d in resultado.decisoes
            ]
        )
        filtro = st.radio(
            "Exibir", ["Todas", "Somente notificadas", "Somente suprimidas"], horizontal=True
        )
        if filtro == "Somente notificadas":
            tabela = tabela[tabela["Notificar"] == "Sim"]
        elif filtro == "Somente suprimidas":
            tabela = tabela[tabela["Notificar"] == "Nao"]
        st.dataframe(tabela, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma decisao avaliada nesta execucao.")

    with st.expander("Matriz de regras vigente (severidade minima por ramo x evento)"):
        st.dataframe(
            pd.DataFrame(config.MATRIZ_REGRAS).fillna("-"),
            use_container_width=True,
        )

# 4. Mensagens ---------------------------------------------------------------
with abas[3]:
    st.subheader("Mensagens personalizadas")
    if resultado.mensagens:
        for mensagem in resultado.mensagens:
            rotulo = (
                f"{mensagem.nome} | {mensagem.canal.value} | "
                f"{mensagem.tipo_evento.value} ({mensagem.prioridade})"
            )
            with st.expander(rotulo):
                if mensagem.assunto:
                    st.markdown(f"**Assunto:** {mensagem.assunto}")
                st.text(mensagem.corpo)
                st.caption(f"Gerado por: {mensagem.gerado_por}")
    else:
        st.info("Nenhuma mensagem gerada nesta execucao.")

# 5. Envio -------------------------------------------------------------------
with abas[4]:
    st.subheader("Simulacao de envio")
    if resultado.notificacoes:
        tabela = pd.DataFrame(
            [
                {
                    "Protocolo": n.id_notificacao,
                    "Segurado": n.nome,
                    "Local": n.local,
                    "Canal": n.canal.value,
                    "Evento": n.tipo_evento.value,
                    "Prioridade": n.prioridade,
                    "Status": n.status_simulado,
                    "Horario": n.enviado_em.strftime("%d/%m/%Y %H:%M:%S"),
                }
                for n in resultado.notificacoes
            ]
        )
        st.dataframe(tabela, use_container_width=True, hide_index=True)
        st.download_button(
            "Baixar fila de notificacoes (JSON)",
            data=json.dumps(
                [n.model_dump(mode="json") for n in resultado.notificacoes],
                ensure_ascii=False,
                indent=2,
            ),
            file_name="notificacoes_simuladas.json",
            mime="application/json",
        )
        st.caption(
            "Nenhum SMS, e-mail ou push e efetivamente enviado: o agente emula um gateway "
            "de mensageria e grava a fila em outputs/."
        )
    else:
        st.info("Nenhuma notificacao despachada nesta execucao.")

# Log ------------------------------------------------------------------------
with abas[5]:
    st.subheader("Rastreabilidade da execucao")
    st.code("\n".join(resultado.log), language="text")
