"""
Gera o relatório técnico em PDF exigido pelo Desafio 5.

O relatório não é um documento estático: ele executa o pipeline e escreve os
exemplos de mensagens a partir do resultado real da execução. Assim, basta
regerar o arquivo para que o PDF reflita a versão atual da solução.

No modo api, a seção 6 é complementada por mensagens de um cenário simulado
(amostra da carteira), rotuladas como tal: em dias de tempo estável a execução
real aprova poucas notificações, e o relatório precisa exemplificar canais e
ramos diferentes.

Uso:
    python docs/gerar_relatorio.py                 # modo simulação, sem LLM
    python docs/gerar_relatorio.py --modo api      # dados reais da API
    python docs/gerar_relatorio.py --com-llm       # mensagens geradas pelo Gemini
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.orquestrador import carregar_segurados, executar_pipeline  # noqa: E402

AZUL = colors.HexColor("#1F4E79")
AZUL_CLARO = colors.HexColor("#D6E4F0")
CINZA = colors.HexColor("#F2F2F2")

estilos = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=estilos["Heading1"], textColor=AZUL, fontSize=16, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=estilos["Heading2"], textColor=AZUL, fontSize=12.5, spaceBefore=12)
H3 = ParagraphStyle("H3", parent=estilos["Heading3"], textColor=colors.HexColor("#333333"), fontSize=10.5)
CORPO = ParagraphStyle(
    "Corpo", parent=estilos["BodyText"], fontSize=9.5, leading=14, alignment=TA_JUSTIFY
)
CELULA = ParagraphStyle("Celula", parent=estilos["BodyText"], fontSize=8.5, leading=11)
CELULA_B = ParagraphStyle("CelulaB", parent=CELULA, fontName="Helvetica-Bold", textColor=colors.white)
MONO = ParagraphStyle(
    "Mono",
    parent=estilos["BodyText"],
    fontName="Courier",
    fontSize=8,
    leading=10.5,
    backColor=CINZA,
    borderPadding=6,
    spaceBefore=4,
    spaceAfter=8,
)


def tabela(dados: list[list[str]], larguras: list[float]) -> Table:
    linhas = [[Paragraph(c, CELULA_B) for c in dados[0]]]
    linhas += [[Paragraph(str(c), CELULA) for c in linha] for linha in dados[1:]]
    t = Table(linhas, colWidths=larguras, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, AZUL_CLARO]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B0B0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(2 * cm, 1.2 * cm, "InsurMinds - Desafio 5 | Squad 4one")
    canvas.drawRightString(19 * cm, 1.2 * cm, f"pág. {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
    canvas.line(2 * cm, 1.6 * cm, 19 * cm, 1.6 * cm)
    canvas.restoreState()


def escapar(texto: str) -> str:
    return (
        texto.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


# Amostra do complemento simulado da seção 6: um segurado por ramo, cobrindo
# SMS, WhatsApp e e-mail (automóvel, residencial, empresarial e agrícola).
SEGURADOS_EXEMPLO = ("SEG-002", "SEG-006", "SEG-007", "SEG-008")


def selecionar_exemplos(notificacoes) -> list:
    """Escolhe mensagens variadas: uma por combinação ramo/canal e por segurado."""
    exemplos, combinacoes, segurados_vistos = [], set(), set()
    for n in notificacoes:
        chave = (n.ramo.value, n.canal.value)
        if chave in combinacoes or n.id_segurado in segurados_vistos:
            continue
        combinacoes.add(chave)
        segurados_vistos.add(n.id_segurado)
        exemplos.append(n)
        if len(exemplos) >= 6:
            break
    for n in notificacoes:  # completa se houver poucas combinacoes
        if len(exemplos) >= 5:
            break
        if n.id_segurado not in segurados_vistos:
            segurados_vistos.add(n.id_segurado)
            exemplos.append(n)
    return exemplos


def blocos_exemplo(n) -> list:
    """Elementos do PDF que apresentam uma mensagem gerada."""
    blocos = [
        Paragraph(
            f"{n.nome} — {n.local} · seguro {n.ramo.value} · canal {n.canal.value} · "
            f"{n.tipo_evento.value.replace('_', ' ')} ({n.severidade.value}, {n.prioridade})",
            H3,
        )
    ]
    if n.assunto:
        blocos.append(Paragraph(f"<b>Assunto:</b> {escapar(n.assunto)}", CORPO))
    blocos.append(Paragraph(escapar(n.mensagem), MONO))
    blocos.append(
        Paragraph(
            f"<font size=7.5 color='#666666'>Protocolo {n.id_notificacao} · status "
            f"{n.status_simulado} · gerado por {escapar(n.gerado_por)}</font>",
            CORPO,
        )
    )
    blocos.append(Spacer(1, 0.25 * cm))
    return blocos


def construir(resultado, destino: Path, complemento=None) -> None:
    doc = SimpleDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="InsurMinds - Desafio 5 - Relatório Técnico",
        author="Squad 4one",
    )
    s: list = []

    # ---------------------------------------------------------------- capa
    s.append(Spacer(1, 3 * cm))
    s.append(
        Paragraph(
            "<font size=22 color='#1F4E79'><b>Ferramenta Inteligente para "
            "Comunicação Proativa com o Segurado</b></font>",
            estilos["Title"],
        )
    )
    s.append(Spacer(1, 0.6 * cm))
    s.append(
        Paragraph(
            "<para align='center'><font size=13>Relatório Técnico — Desafio 5</font><br/>"
            "<font size=11>Curso InsurMinds · Instituto de Inteligência Artificial "
            "Aplicada (I2A2)</font></para>",
            estilos["Normal"],
        )
    )
    s.append(Spacer(1, 2 * cm))
    s.append(
        Paragraph(
            f"<para align='center'><b>Grupo:</b> Squad 4one<br/>"
            f"<b>Data:</b> {datetime.now(tz=config.FUSO):%d/%m/%Y}<br/>"
            f"<b>Licença:</b> MIT</para>",
            estilos["Normal"],
        )
    )
    s.append(Spacer(1, 1.5 * cm))
    s.append(
        Paragraph(
            "<para align='center'><i>Protótipo funcional que monitora uma API pública de "
            "dados meteorológicos, identifica eventos de risco, aplica regras de negócio por "
            "ramo de seguro, gera comunicações personalizadas com IA Generativa e simula o "
            "envio das notificações aos segurados.</i></para>",
            CORPO,
        )
    )
    s.append(PageBreak())

    # ------------------------------------------------------- 1. o problema
    s.append(Paragraph("1. Problema abordado", H1))
    s.append(
        Paragraph(
            "A maior parte das interações entre seguradora e cliente acontece depois do "
            "sinistro: o segurado liga para avisar que o carro foi atingido por granizo ou que "
            "a água entrou na loja. O prejuízo já ocorreu, o relacionamento começa por uma "
            "perda e a seguradora arca com uma indenização que, em muitos casos, uma ação "
            "preventiva simples teria evitado ou reduzido.",
            CORPO,
        )
    )
    s.append(
        Paragraph(
            "Esta solução inverte esse fluxo. Ela monitora continuamente a previsão do tempo "
            "nas localidades onde a carteira está exposta e, quando identifica um evento com "
            "potencial de dano, avisa apenas os segurados cujo produto é efetivamente sensível "
            "àquele fenômeno — com orientações específicas para o que ele tem a proteger. O "
            "ganho é duplo: reduz frequência e severidade de sinistros e transforma um contato "
            "operacional em um contato de cuidado.",
            CORPO,
        )
    )

    # ------------------------------------------------------ 2. arquitetura
    s.append(Paragraph("2. Arquitetura da solução", H1))
    s.append(
        Paragraph(
            "A solução foi modelada como um fluxo de cinco agentes especializados, cada um com "
            "uma única responsabilidade e um contrato de dados explícito (classes Pydantic). "
            "Nenhum agente conhece a implementação do anterior: o AgenteAnalise recebe uma "
            "previsão normalizada, sem saber se ela veio da API ou do gerador de cenários; o "
            "AgenteNotificacao recebe mensagens prontas, sem saber se foram escritas pelo LLM "
            "ou por template.",
            CORPO,
        )
    )
    s.append(Spacer(1, 0.2 * cm))
    s.append(
        Paragraph(
            "Carteira (CSV) &rarr; <b>1. Coleta</b> &rarr; <b>2. Análise</b> &rarr; "
            "<b>3. Regras</b> &rarr; <b>4. Redação (IA)</b> &rarr; <b>5. Notificação</b> "
            "&rarr; fila simulada (JSON/CSV)",
            ParagraphStyle("fluxo", parent=CORPO, alignment=1, backColor=CINZA, borderPadding=8),
        )
    )
    s.append(Spacer(1, 0.3 * cm))
    s.append(
        Paragraph(
            "<b>Decisão arquitetural central:</b> a identificação do evento e a decisão de quem "
            "notificar são determinísticas, baseadas em limiares numéricos — não em LLM. Um "
            "aviso enviado a um segurado precisa ser reproduzível e auditável: dado o mesmo "
            "dado meteorológico, o sistema sempre toma a mesma decisão, e o motivo fica "
            "registrado. A IA Generativa entra apenas na camada de redação, recebendo um "
            "contexto fechado com os fatos já apurados. Isso reduz drasticamente o risco de o "
            "modelo inventar previsões, valores ou coberturas.",
            CORPO,
        )
    )

    s.append(Paragraph("2.1 Descrição dos agentes", H2))
    s.append(
        tabela(
            [
                ["Agente", "Responsabilidade", "Entrada &rarr; Saída"],
                [
                    "<b>1. AgenteColeta</b><br/>src/agentes/coleta.py",
                    "Consulta a API pública Open-Meteo e normaliza a previsão horária. Agrupa "
                    "segurados por coordenada, de modo que uma cidade com vários clientes gere "
                    "uma única chamada. Possui modo de simulação com a mesma estrutura de dados.",
                    "list[Segurado] &rarr;<br/>list[PrevisaoLocal]",
                ],
                [
                    "<b>2. AgenteAnalise</b><br/>src/agentes/analise.py",
                    "Varre a série horária e identifica eventos relevantes por limiares "
                    "(chuva, vento, calor, geada) e por códigos WMO (granizo, tempestade). "
                    "Atribui severidade e produz a justificativa numérica.",
                    "list[PrevisaoLocal] &rarr;<br/>list[EventoClimatico]",
                ],
                [
                    "<b>3. AgenteRegras</b><br/>src/agentes/regras.py",
                    "Cruza eventos com a carteira e aplica a política de comunicação (R1, R2, "
                    "R3). Registra também as decisões negativas, com a regra e o motivo.",
                    "eventos + carteira &rarr;<br/>list[Decisao]",
                ],
                [
                    "<b>4. AgenteRedacao</b><br/>src/agentes/redacao.py",
                    "Gera a mensagem com Gemini via LangChain, adaptando tom, formato e limite "
                    "de caracteres ao canal e à urgência. Em caso de falha ou ausência de "
                    "chave, cai para um gerador por template.",
                    "list[Decisao] &rarr;<br/>list[Mensagem]",
                ],
                [
                    "<b>5. AgenteNotificacao</b><br/>src/agentes/notificacao.py",
                    "Emula um gateway de mensageria: atribui protocolo, registra status e "
                    "horário, grava a fila em JSON/CSV e atualiza o histórico usado no cooldown.",
                    "list[Mensagem] &rarr;<br/>list[Notificacao]",
                ],
            ],
            [3.6 * cm, 8.4 * cm, 4.5 * cm],
        )
    )
    s.append(PageBreak())

    # ------------------------------------------------------ 3. tecnologias
    s.append(Paragraph("3. Tecnologias utilizadas", H1))
    s.append(
        tabela(
            [
                ["Camada", "Tecnologia", "Justificativa"],
                ["Linguagem", "Python 3.11+", "Ecossistema de dados e integração com os frameworks do curso."],
                [
                    "Fonte meteorológica",
                    "Open-Meteo (API pública)",
                    "Gratuita, sem necessidade de chave, cobertura global, resolução horária e "
                    "códigos de tempo no padrão WMO — o que permite detectar granizo e "
                    "tempestade elétrica diretamente.",
                ],
                [
                    "Orquestração / LLM",
                    "LangChain (LCEL) + Google Gemini",
                    "LCEL compõe prompt, modelo e parser em uma cadeia enxuta; o Gemini atende "
                    "bem português do Brasil e possui camada gratuita.",
                ],
                [
                    "Contratos de dados",
                    "Pydantic v2",
                    "Valida e documenta a fronteira entre os agentes, evitando acoplamento por "
                    "dicionários soltos.",
                ],
                ["Interface", "Streamlit", "Demonstra o fluxo etapa a etapa com baixo custo de desenvolvimento."],
                [
                    "Segredos",
                    "python-dotenv",
                    "Chaves ficam em .env, fora do versionamento (.gitignore), conforme boa "
                    "prática exigida no desafio.",
                ],
            ],
            [3.2 * cm, 4.3 * cm, 9 * cm],
        )
    )

    # ----------------------------------------------- 4. regras de negócio
    s.append(Paragraph("4. Regras de negócio", H1))
    s.append(
        Paragraph(
            "A política de comunicação foi separada do código e concentrada em "
            "<font face='Courier' size=8.5>src/config.py</font>. Ajustar a sensibilidade da "
            "seguradora — por exemplo, passar a avisar frotas em caso de vento moderado — não "
            "exige alterar nenhum agente.",
            CORPO,
        )
    )
    s.append(
        tabela(
            [
                ["Regra", "Descrição", "Fundamento"],
                [
                    "<b>R1 — Pertinência por ramo</b>",
                    "Cada ramo possui uma severidade mínima por tipo de evento. Abaixo dela, o "
                    "segurado não é notificado.",
                    "Granizo de qualquer intensidade é crítico para automóvel e lavoura; chuva "
                    "moderada preocupa o residencial, mas não o motorista. Avisar todo mundo de "
                    "tudo destrói a credibilidade do canal.",
                ],
                [
                    "<b>R2 — Antecedência útil</b>",
                    f"Só entram eventos previstos para as próximas "
                    f"{config.JANELA_ANTECEDENCIA_H} horas.",
                    "Abaixo desse horizonte a previsão é confiável e ainda há tempo de ação "
                    "preventiva (recolher o carro, limpar a calha, antecipar a colheita).",
                ],
                [
                    "<b>R3 — Cooldown</b>",
                    f"O mesmo segurado não recebe o mesmo tipo de alerta duas vezes em "
                    f"{config.COOLDOWN_H} horas.",
                    "Evita que reexecuções do monitoramento gerem spam e o segurado passe a "
                    "ignorar os avisos.",
                ],
            ],
            [4.2 * cm, 5.3 * cm, 7 * cm],
        )
    )

    s.append(Paragraph("4.1 Limiares de severidade", H2))
    s.append(
        Paragraph(
            "Os limiares seguem a lógica das escalas de aviso meteorológico usadas no Brasil "
            "(faixas de chuva acumulada e de rajada de vento) e práticas de subscrição para "
            "geada e granizo:",
            CORPO,
        )
    )
    s.append(
        tabela(
            [
                ["Evento", "Métrica", "Baixa", "Moderada", "Alta", "Severa"],
                ["Chuva intensa", "mm/h", "5", "10", "20", "35"],
                ["Vento forte", "rajada km/h", "40", "55", "75", "95"],
                ["Onda de calor", "temp. máx. °C", "32", "35", "38", "40"],
                ["Geada", "temp. mín. °C", "5", "3", "1", "-1"],
                ["Granizo", "código WMO 96/99", "—", "—", "1-2 h", "3+ h"],
                ["Tempestade", "código WMO 95", "—", "1-2 h", "3+ h", "—"],
            ],
            [3.4 * cm, 3.4 * cm, 2.3 * cm, 2.4 * cm, 2.2 * cm, 2.3 * cm],
        )
    )

    s.append(Paragraph("4.2 Matriz ramo × evento (severidade mínima)", H2))
    linhas = [["Evento", "Residencial", "Automóvel", "Agrícola", "Empresarial"]]
    eventos_ordem = [
        ("chuva_intensa", "Chuva intensa"),
        ("vento_forte", "Vento forte"),
        ("granizo", "Granizo"),
        ("tempestade", "Tempestade elétrica"),
        ("onda_calor", "Onda de calor"),
        ("geada", "Geada"),
    ]
    for chave, rotulo in eventos_ordem:
        linha = [rotulo]
        for ramo in ["residencial", "automovel", "agricola", "empresarial"]:
            linha.append(config.MATRIZ_REGRAS[ramo].get(chave, "—"))
        linhas.append(linha)
    s.append(tabela(linhas, [4 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 3.4 * cm]))
    s.append(PageBreak())

    # ------------------------------------------------------- 5. fluxo real
    s.append(Paragraph("5. Fluxo de processamento — execução demonstrada", H1))
    s.append(
        Paragraph(
            f"Execução de {resultado.executado_em:%d/%m/%Y às %H:%M:%S}. "
            f"<b>Fonte de dados:</b> {resultado.modo_dados}. "
            f"<b>Gerador de mensagens:</b> {resultado.modo_llm}.",
            CORPO,
        )
    )
    s.append(
        tabela(
            [
                ["Etapa", "Resultado"],
                ["1. Coleta", f"{len(resultado.previsoes)} localidades consultadas"],
                ["2. Análise", f"{len(resultado.eventos)} eventos climáticos relevantes identificados"],
                [
                    "3. Regras",
                    f"{len(resultado.decisoes)} pares segurado/evento avaliados — "
                    f"{len([d for d in resultado.decisoes if d.notificar])} aprovados, "
                    f"{resultado.total_suprimidos} suprimidos",
                ],
                ["4. Redação", f"{len(resultado.mensagens)} mensagens personalizadas geradas"],
                ["5. Notificação", f"{resultado.total_notificados} notificações simuladas e registradas"],
            ],
            [4 * cm, 13 * cm],
        )
    )

    s.append(Paragraph("5.1 Eventos identificados", H2))
    if resultado.eventos:
        linhas = [["Local", "Evento", "Severidade", "Janela prevista", "Justificativa"]]
        for e in resultado.eventos[:14]:
            linhas.append(
                [
                    f"{e.cidade}/{e.uf}",
                    e.tipo.value.replace("_", " "),
                    e.severidade.value,
                    f"{e.inicio:%d/%m %Hh}–{e.fim:%d/%m %Hh}",
                    escapar(e.justificativa),
                ]
            )
        s.append(tabela(linhas, [3 * cm, 2.6 * cm, 2 * cm, 3 * cm, 6.4 * cm]))
    else:
        s.append(Paragraph("Nenhum evento atingiu os limiares nesta execução.", CORPO))

    s.append(Paragraph("5.2 Decisões suprimidas (auditoria da política)", H2))
    s.append(
        Paragraph(
            "O registro das decisões negativas é parte do resultado: ele mostra que o sistema "
            "filtra, e não apenas dispara.",
            CORPO,
        )
    )
    suprimidas = [d for d in resultado.decisoes if not d.notificar][:8]
    if suprimidas:
        linhas = [["Segurado", "Ramo", "Evento", "Regra", "Motivo"]]
        for d in suprimidas:
            linhas.append(
                [d.nome, d.ramo.value, d.tipo_evento.value.replace("_", " "), d.regra, escapar(d.motivo)]
            )
        s.append(tabela(linhas, [3.2 * cm, 2.4 * cm, 2.6 * cm, 2.6 * cm, 6.2 * cm]))
    else:
        s.append(Paragraph("Nenhuma decisão suprimida nesta execução.", CORPO))
    s.append(PageBreak())

    # ------------------------------------------------ 6. exemplos de saída
    s.append(Paragraph("6. Exemplos de mensagens geradas", H1))
    s.append(
        Paragraph(
            "Mensagens produzidas pelo fluxo, cobrindo ramos, canais e níveis de urgência "
            "diferentes. Observe que o conteúdo técnico (horário, intensidade, orientações) "
            "vem das camadas determinísticas; o modelo apenas dá forma ao texto.",
            CORPO,
        )
    )

    s.append(Paragraph("6.1 Mensagens da execução demonstrada", H2))
    exemplos = selecionar_exemplos(resultado.notificacoes)
    if exemplos:
        for n in exemplos:
            s.extend(blocos_exemplo(n))
    else:
        s.append(Paragraph("Nenhuma notificação foi aprovada nesta execução.", CORPO))

    if complemento is not None:
        s.append(Paragraph("6.2 Mensagens em cenário simulado", H2))
        s.append(
            Paragraph(
                "Para exemplificar outros canais e ramos independentemente do tempo real na data "
                "da execução, o mesmo fluxo foi aplicado a cenários simulados — com a mesma "
                "estrutura de dados da API — para uma amostra da carteira. A origem de cada "
                "texto aparece na linha de protocolo.",
                CORPO,
            )
        )
        for n in selecionar_exemplos(complemento.notificacoes):
            s.extend(blocos_exemplo(n))

    s.append(PageBreak())

    # --------------------------------------- 7. simulação e rastreabilidade
    s.append(Paragraph("7. Simulação de envio e rastreabilidade", H1))
    s.append(
        Paragraph(
            "Conforme o escopo do desafio, não há envio real de SMS, e-mail ou push. O "
            "AgenteNotificacao emula o comportamento de um gateway de mensageria: gera um "
            "protocolo por notificação, registra canal, horário e status, grava a fila em "
            "<font face='Courier' size=8.5>outputs/notificacoes_AAAAMMDD_HHMMSS.json</font> e "
            "no CSV correspondente, e atualiza o histórico consultado pela regra de cooldown. "
            "Substituir esse agente por uma integração real (Twilio, SendGrid, WhatsApp "
            "Business API) não exigiria alteração em nenhum outro componente.",
            CORPO,
        )
    )
    s.append(Paragraph("7.1 Trecho do log de execução", H2))
    s.append(Paragraph(escapar("\n".join(resultado.log[:26])), MONO))

    # -------------------------------------------------- 8. limitações
    s.append(Paragraph("8. Limitações conhecidas", H1))
    for item in [
        "A carteira de segurados é fictícia e georreferenciada por cidade, não por endereço; "
        "em produção a granularidade seria por CEP ou coordenada do risco.",
        "Os limiares são gerais para o país. Uma versão de produção usaria limiares regionais "
        "calibrados com o histórico de sinistros da própria carteira.",
        "O granizo é inferido pelos códigos WMO 96/99 do modelo de previsão, que têm resolução "
        "espacial limitada para fenômenos convectivos locais.",
        "O envio é simulado e não há confirmação de entrega, opt-out do segurado nem controle "
        "de horário de silêncio — itens obrigatórios em uma implantação real.",
        "As mensagens não são revisadas por humano antes do despacho; em produção seria "
        "recomendável uma fila de aprovação para alertas de severidade máxima.",
    ]:
        s.append(Paragraph(f"• {item}", CORPO))

    s.append(Paragraph("9. Evolução futura", H1))
    for item in [
        "Cruzar a previsão com o histórico de sinistros para calibrar limiares por região e por "
        "produto, priorizando os riscos com maior perda esperada.",
        "Incluir outras fontes (INMET, radar meteorológico, alertas do CEMADEN) e consolidar "
        "por consenso entre modelos, reduzindo falso positivo.",
        "Medir a efetividade: comparar frequência e severidade de sinistros entre segurados "
        "notificados e grupo de controle, transformando o projeto em caso de ROI.",
        "Integrar com um gateway real e com o CRM, registrando o aviso na linha do tempo do "
        "cliente e na eventual regulação do sinistro.",
        "Estender o mesmo pipeline a eventos não meteorológicos: seca prolongada para o "
        "agrícola, ondas de calor para linhas de vida e saúde, alertas de enchente urbana.",
    ]:
        s.append(Paragraph(f"• {item}", CORPO))

    s.append(Paragraph("10. Como executar", H1))
    s.append(
        Paragraph(
            escapar(
                "pip install -r requirements.txt\n"
                "cp .env.example .env        # informe a GOOGLE_API_KEY\n"
                "streamlit run app.py        # interface de demonstração\n"
                "python main.py --modo simulacao --sem-llm   # execução offline"
            ),
            MONO,
        )
    )
    s.append(
        Paragraph(
            "O repositório é público e está licenciado sob a licença MIT. O README.md traz "
            "instruções completas de instalação, execução e estrutura do projeto.",
            CORPO,
        )
    )

    doc.build(s, onFirstPage=rodape, onLaterPages=rodape)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modo", choices=["api", "simulacao"], default="simulacao")
    parser.add_argument("--com-llm", action="store_true")
    argumentos = parser.parse_args()

    resultado = executar_pipeline(
        modo_dados=argumentos.modo,
        usar_llm=argumentos.com_llm,
        usar_historico=False,
    )
    complemento = None
    if argumentos.modo == "api":
        amostra = [seg for seg in carregar_segurados() if seg.id_segurado in SEGURADOS_EXEMPLO]
        complemento = executar_pipeline(
            modo_dados="simulacao",
            usar_llm=argumentos.com_llm,
            usar_historico=False,
            segurados=amostra,
        )
    destino = Path(__file__).resolve().parent / "InsurMinds_Desafio5_Relatorio_Tecnico.pdf"
    construir(resultado, destino, complemento)
    print(f"Relatório gerado: {destino}")


if __name__ == "__main__":
    main()
