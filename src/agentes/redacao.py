"""
Agente 4 - Redacao (IA Generativa).

Responsabilidade unica: transformar uma decisao tecnica em uma mensagem que um
segurado leia e entenda, adaptada ao canal, ao ramo e a urgencia.

Arquitetura do prompt:
  - o CONTEUDO FACTUAL (evento, severidade, horario, orientacoes preventivas)
    vem das camadas anteriores e entra no prompt como contexto fechado;
  - o LLM cuida apenas de linguagem, tom e formato.
Essa separacao reduz drasticamente o risco de alucinacao: o modelo nao inventa
previsao, ele redige a partir do que as regras de negocio ja decidiram.

Modelo: Gemini via LangChain (ChatGoogleGenerativeAI). Caso a chave nao esteja
configurada ou a API falhe, o agente cai para um gerador por template, para que
o fluxo completo continue demonstravel. O campo "gerado_por" registra qual dos
dois produziu cada mensagem.
"""

from __future__ import annotations

from src import config
from src.models import Canal, Decisao, Mensagem, Segurado

INSTRUCOES_SISTEMA = """Voce e redator de comunicacao preventiva de uma seguradora brasileira.
Escreve avisos curtos que ajudam o segurado a proteger seu bem ANTES de um evento climatico.

Regras obrigatorias:
1. Use somente os fatos fornecidos no contexto. Nunca invente horarios, indices, valores,
   coberturas, franquias ou garantias da apolice.
2. Nunca prometa indenizacao, nao afirme que o evento vai acontecer com certeza e nao
   use linguagem alarmista. Trate-se de previsao, use "previsao", "risco", "possibilidade".
3. Portugues do Brasil, tom cordial e direto, tratamento por "voce".
4. Cite o primeiro nome do segurado, a cidade e a janela prevista do evento.
5. Inclua as orientacoes preventivas fornecidas, reescritas de forma natural.
6. Encerre lembrando o canal de assistencia 24h informado.
7. Nao use emojis, hashtags nem markdown. Devolva apenas o texto final da mensagem.
"""

FORMATO_CANAL = {
    "sms": "SMS: no maximo 3 frases curtas, texto corrido, sem saudacao longa.",
    "whatsapp": (
        "WhatsApp: saudacao curta, 1 paragrafo de contexto e ate 3 orientacoes em "
        "linhas separadas iniciadas por hifen. Sem assunto."
    ),
    "email": (
        "E-mail: primeira linha no formato 'Assunto: ...' (ate 60 caracteres), "
        "depois saudacao, contexto, orientacoes em lista com hifen e despedida."
    ),
}

TOM_PRIORIDADE = {
    "informativa": "Tom informativo e tranquilo.",
    "atencao": "Tom de atencao: peca uma acao preventiva ainda hoje.",
    "urgente": "Tom de urgencia responsavel: acao imediata, sem panico.",
}


class AgenteRedacao:
    """Gera mensagens personalizadas com IA Generativa."""

    nome = "AgenteRedacao"

    def __init__(self, usar_llm: bool = True, logger=None) -> None:
        self.log = logger or (lambda _msg: None)
        self.cadeia = None
        self.modo = "template"
        if usar_llm and config.GOOGLE_API_KEY:
            self.cadeia = self._montar_cadeia()
        elif usar_llm:
            self.log(f"[{self.nome}] GOOGLE_API_KEY ausente - usando gerador por template")

    def _montar_cadeia(self):
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=config.MODELO_LLM,
                temperature=config.TEMPERATURA_LLM,
                google_api_key=config.GOOGLE_API_KEY,
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", INSTRUCOES_SISTEMA),
                    (
                        "human",
                        "Contexto do aviso:\n"
                        "- Seguradora: {seguradora}\n"
                        "- Segurado: {nome}\n"
                        "- Cidade: {local}\n"
                        "- Produto contratado: seguro {ramo} (apolice {apolice})\n"
                        "- Evento previsto: {evento} (severidade {severidade})\n"
                        "- Janela prevista: {janela}\n"
                        "- Base tecnica: {justificativa}\n"
                        "- Orientacoes preventivas a incluir: {orientacoes}\n"
                        "- Assistencia 24h: {assistencia}\n\n"
                        "Formato exigido: {formato}\n"
                        "{tom}\n"
                        "Limite: {limite} caracteres.",
                    ),
                ]
            )
            self.modo = f"LLM ({config.MODELO_LLM} via LangChain)"
            self.log(f"[{self.nome}] cadeia LangChain + {config.MODELO_LLM} inicializada")
            return prompt | llm | StrOutputParser()
        except Exception as erro:
            self.log(f"[{self.nome}] falha ao inicializar o LLM ({erro}) - usando template")
            return None

    # -- Execucao -----------------------------------------------------------
    def executar(
        self, decisoes: list[Decisao], segurados: dict[str, Segurado]
    ) -> list[Mensagem]:
        mensagens: list[Mensagem] = []
        for decisao in [d for d in decisoes if d.notificar]:
            segurado = segurados[decisao.id_segurado]
            texto, origem = self._redigir(decisao, segurado)
            assunto = None
            if segurado.canal == Canal.EMAIL:
                assunto, texto = self._separar_assunto(texto, decisao)
            mensagens.append(
                Mensagem(
                    id_segurado=segurado.id_segurado,
                    nome=segurado.nome,
                    canal=segurado.canal,
                    assunto=assunto,
                    corpo=texto.strip(),
                    gerado_por=origem,
                    tipo_evento=decisao.tipo_evento,
                    severidade=decisao.severidade,
                    prioridade=decisao.prioridade,
                )
            )
        self.log(f"[{self.nome}] {len(mensagens)} mensagens geradas ({self.modo})")
        return mensagens

    def _redigir(self, decisao: Decisao, segurado: Segurado) -> tuple[str, str]:
        if self.cadeia is not None:
            try:
                evento = decisao.evento
                texto = self.cadeia.invoke(
                    {
                        "seguradora": config.NOME_SEGURADORA,
                        "nome": segurado.nome,
                        "local": segurado.local,
                        "ramo": segurado.ramo.value,
                        "apolice": segurado.apolice,
                        "evento": decisao.tipo_evento.value.replace("_", " "),
                        "severidade": decisao.severidade.value,
                        "janela": (
                            f"{evento.inicio:%d/%m às %Hh} até {evento.fim:%d/%m às %Hh}"
                            if evento
                            else "próximas horas"
                        ),
                        "justificativa": evento.justificativa if evento else "",
                        "orientacoes": "; ".join(decisao.orientacoes),
                        "assistencia": config.TELEFONE_ASSISTENCIA,
                        "formato": FORMATO_CANAL[segurado.canal.value],
                        "tom": TOM_PRIORIDADE[decisao.prioridade],
                        "limite": config.CANAL_LIMITES[segurado.canal.value],
                    }
                )
                if texto and texto.strip():
                    return texto, self.modo
            except Exception as erro:
                self.log(f"[{self.nome}] erro no LLM para {segurado.nome}: {erro}")
        return self._template(decisao, segurado), "template (fallback)"

    def _template(self, decisao: Decisao, segurado: Segurado) -> str:
        evento = decisao.evento
        primeiro_nome = segurado.nome.split()[0]
        rotulo = decisao.tipo_evento.value.replace("_", " ")
        janela = (
            f"entre {evento.inicio:%d/%m às %Hh} e {evento.fim:%d/%m às %Hh}"
            if evento
            else "nas próximas horas"
        )
        base_tecnica = evento.justificativa if evento else ""
        orientacoes = decisao.orientacoes[:3]

        if segurado.canal == Canal.SMS:
            return (
                f"{config.NOME_SEGURADORA}: {primeiro_nome}, há previsão de {rotulo} "
                f"({decisao.severidade.value}) em {segurado.cidade} {janela}. "
                f"{orientacoes[0]}. Assistência 24h: {config.TELEFONE_ASSISTENCIA}."
            )

        linhas = [
            f"Olá, {primeiro_nome}!",
            "",
            f"A previsão indica {rotulo} de intensidade {decisao.severidade.value} em "
            f"{segurado.local} {janela}. {base_tecnica}",
            "",
            f"Como você tem seguro {segurado.ramo.value} conosco (apólice {segurado.apolice}), "
            "seguem orientações preventivas:",
        ]
        linhas += [f"- {o}" for o in orientacoes]
        linhas += [
            "",
            f"Em caso de ocorrência, acione nossa assistência 24h: {config.TELEFONE_ASSISTENCIA}.",
        ]
        corpo = "\n".join(linhas)

        if segurado.canal == Canal.EMAIL:
            assunto = f"Assunto: Alerta de {rotulo} em {segurado.cidade}"
            return f"{assunto}\n{corpo}"
        return corpo

    @staticmethod
    def _separar_assunto(texto: str, decisao: Decisao) -> tuple[str, str]:
        linhas = texto.strip().splitlines()
        if linhas and linhas[0].lower().startswith("assunto:"):
            return linhas[0].split(":", 1)[1].strip(), "\n".join(linhas[1:]).strip()
        padrao = f"Alerta de {decisao.tipo_evento.value.replace('_', ' ')}"
        return padrao, texto.strip()
