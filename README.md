# InsurMinds — Desafio 5
## Ferramenta Inteligente para Comunicação Proativa com o Segurado

Protótipo funcional (MVP) que monitora eventos meteorológicos a partir de uma **API pública**,
identifica automaticamente situações de risco, aplica **regras de negócio** para decidir quais
segurados devem ser avisados, gera **mensagens personalizadas com IA Generativa** e **simula o
envio** das notificações.

> Grupo **Squad 4one** — Curso InsurMinds, Instituto de Inteligência Artificial Aplicada (I2A2).

---

## Arquitetura

Fluxo composto por cinco agentes especializados, cada um com uma única responsabilidade:

```
 [carteira de segurados .csv]
             │
             ▼
 ┌──────────────────────┐   previsão horária normalizada
 │ 1. AgenteColeta      │──────────────────────────────┐
 │    Open-Meteo (API)  │                              │
 └──────────────────────┘                              ▼
 ┌──────────────────────┐   eventos com tipo, severidade e justificativa
 │ 2. AgenteAnalise     │──────────────────────────────┐
 │    limiares WMO/INMET│                              │
 └──────────────────────┘                              ▼
 ┌──────────────────────┐   decisões (notificar / suprimir + motivo)
 │ 3. AgenteRegras      │──────────────────────────────┐
 │    R1 · R2 · R3      │                              │
 └──────────────────────┘                              ▼
 ┌──────────────────────┐   mensagem por canal, ramo e urgência
 │ 4. AgenteRedacao     │──────────────────────────────┐
 │    LangChain + Gemini│                              │
 └──────────────────────┘                              ▼
 ┌──────────────────────┐   protocolo, status e arquivo em outputs/
 │ 5. AgenteNotificacao │
 │    gateway simulado  │
 └──────────────────────┘
```

A detecção de eventos e a decisão de quem notificar são **determinísticas e auditáveis**
(limiares numéricos, não LLM). A IA Generativa atua apenas na camada de redação, a partir de um
contexto fechado — o modelo nunca inventa previsão, valores ou coberturas.

---

## Regras de negócio

| Regra | Nome | O que faz |
|-------|------|-----------|
| **R1** | Pertinência por ramo | Cada ramo tem uma severidade mínima por tipo de evento (`config.MATRIZ_REGRAS`). Granizo é crítico para automóvel e lavoura; chuva moderada importa para residencial, não para automóvel. |
| **R2** | Antecedência útil | Só comunica eventos previstos para as próximas 48 h (configurável). |
| **R3** | Cooldown anti-spam | Não repete o mesmo tipo de alerta para o mesmo segurado dentro de 24 h. |

Toda decisão — inclusive a de **não** notificar — é registrada com regra e motivo.

### Matriz de severidade mínima (ramo × evento)

| Evento | Residencial | Automóvel | Agrícola | Empresarial |
|--------|-------------|-----------|----------|-------------|
| Chuva intensa | moderada | alta | alta | alta |
| Vento forte | moderada | alta | alta | moderada |
| Granizo | baixa | baixa | baixa | — |
| Tempestade elétrica | alta | moderada | — | alta |
| Onda de calor | — | — | moderada | — |
| Geada | — | — | baixa | — |

---

## Tecnologias

| Camada | Tecnologia |
|--------|------------|
| Linguagem | Python 3.11 a 3.13 (validado no 3.13) |
| Dados meteorológicos | [Open-Meteo](https://open-meteo.com) — API pública, sem chave, códigos WMO |
| Orquestração de agentes | LangChain (LCEL) |
| IA Generativa | Google Gemini (`gemini-3.6-flash`) via `langchain-google-genai` |
| Validação de dados | Pydantic v2 |
| Interface | Streamlit |
| Configuração/segredos | python-dotenv (`.env` fora do versionamento) |

---

## Instalação

Requer Python 3.11, 3.12 ou 3.13.

```bash
git clone https://github.com/jeancarlosde-lima/InsurMinds-Desafio-5.git
cd InsurMinds-Desafio-5

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Configure as credenciais:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS
```

Edite o `.env` e informe sua `GOOGLE_API_KEY` (obtida gratuitamente no Google AI Studio).
Sem a chave a aplicação continua funcionando: as mensagens passam a ser geradas por template,
e o campo `gerado_por` de cada notificação indica qual gerador foi usado.

---

## Execução

**Interface web (recomendado para a demonstração):**

```bash
streamlit run app.py
```

A interface abre em `http://localhost:8501` com uma aba por etapa do fluxo: coleta, eventos,
decisões, mensagens, envio simulado e log de execução.

**Linha de comando:**

```bash
python main.py                      # API pública + IA Generativa
python main.py --modo simulacao     # cenários sintéticos, funciona offline
python main.py --sem-llm            # mensagens por template
python main.py --ignorar-historico  # desativa o cooldown (R3)
```

O modo `simulacao` gera cenários sintéticos (temporal com granizo, vendaval, onda de calor,
geada) com a **mesma estrutura de dados da API**. Ele existe porque em um dia de tempo estável
nenhum alerta seria disparado e o fluxo não poderia ser demonstrado.

**Relatório técnico (PDF):**

```bash
python docs/gerar_relatorio.py --modo api --com-llm   # dados reais + mensagens geradas pelo Gemini
```

O script executa o fluxo completo e grava o PDF em `docs/` com os resultados dessa execução.

### Saídas

Cada execução grava em `outputs/`:

- `notificacoes_AAAAMMDD_HHMMSS.json` — fila completa, com mensagem e protocolo;
- `notificacoes_AAAAMMDD_HHMMSS.csv` — mesma fila em formato tabular;
- `historico_notificacoes.json` — base usada pela regra de cooldown.

Nenhum SMS, e-mail ou push é efetivamente enviado: o `AgenteNotificacao` emula um gateway de
mensageria, conforme o escopo do desafio.

---

## Estrutura do projeto

```
InsurMinds-Desafio-5/
├── app.py                    # interface Streamlit (demonstração do fluxo)
├── main.py                   # execução via linha de comando
├── requirements.txt
├── .env.example              # modelo de configuração (sem segredos)
├── .gitignore                # mantém .env, .venv e saídas fora do versionamento
├── LICENSE                   # licença MIT
├── data/
│   └── segurados.csv         # carteira simulada (16 segurados, 8 cidades, 4 ramos)
├── docs/
│   ├── gerar_relatorio.py    # gera o relatório técnico a partir de uma execução real
│   └── InsurMinds_Desafio5_Relatorio_Tecnico.pdf
├── outputs/                  # filas de notificação geradas (não versionadas)
└── src/
    ├── config.py             # limiares, matriz de regras, orientações, credenciais
    ├── models.py             # contratos de dados entre os agentes (Pydantic)
    ├── simulacao.py          # gerador de cenários sintéticos
    ├── orquestrador.py       # encadeamento dos cinco agentes
    └── agentes/
        ├── coleta.py         # 1 — API meteorológica
        ├── analise.py        # 2 — detecção de eventos
        ├── regras.py         # 3 — regras de negócio
        ├── redacao.py        # 4 — IA Generativa
        └── notificacao.py    # 5 — envio simulado
```

---

## Limitações conhecidas

- A carteira de segurados é fictícia e georreferenciada por cidade, não por endereço.
- Os limiares são gerais para o Brasil; uma versão de produção usaria limiares regionais e
  histórico de sinistros por CEP.
- O granizo é inferido pelos códigos WMO 96/99 do modelo de previsão, que têm resolução espacial
  limitada para fenômenos convectivos.
- O envio é simulado; a integração com um gateway real exigiria apenas substituir o
  `AgenteNotificacao`, sem alterar os demais agentes.

---

## Integrantes — Squad 4one

| Nome | Papel |
|------|-------|
| Daiane Cristina de Oliveira Brito | Representante do grupo |
| Jean Carlos Oliveira de Lima | Desenvolvimento |
| Simone Teixeira da Silva | Integrante |
| Carolinne Vieira Costa | Integrante |
| Aline Cristina Goya | Integrante |

---

## Licença

Este projeto está licenciado sob a **licença MIT**. Veja o arquivo [LICENSE](LICENSE).
