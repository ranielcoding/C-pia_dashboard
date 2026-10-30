# GUIA DE DESENVOLVIMENTO — Dashboard Divimed

> Documento vivo: revisar quando novas skills, tools ou workflows forem adicionados ao ecossistema.

---

## 1. INTEGRAÇÕES DE AI

| Ferramenta | Tipo | Como ativar |
|---|---|---|
| **Claude Dev** (`saoudrizwan.claude-dev`) | Extensão VS Code | `Ctrl+Shift+P` → "Claude: Chat" |
| **Kilo Code** (`kilocode.kilo-code`) | Extensão VS Code | `Ctrl+Shift+P` → "Kilo Code" |
| **SpecKit Assistant** (`rfsales.speckit-assistant`) | Extensão VS Code | `Ctrl+Shift+P` → comandos SpecKit |
| **Hermes Agent** (CLI) | Terminal | Esta sessão — use `delegate_task` para subtarefas paralelas |

**Qual usar?**

- Coding rápido inline → Claude Dev ou Kilo Code na sidebar
- Trabalho estruturado (spec → plan → tasks → implement) → **SpecKit Assistant**
- Tarefas pesadas / background / paralelo → **Hermes Agent**

---

## 2. SPECKIT (Spec → Plan → Tasks → Implement)

O SpecKit é o workflow estruturado de desenvolvimento. **É o core do fluxo de trabalho no projeto.**

### Arquivos chave

```
.specify/
├── workflows/speckit/
│   └── workflow.yml          # Workflow completo: specify → plan → tasks → implement + gates
├── templates/
│   ├── constitution-template.md
│   └── checklist-template.md
└── memory/
    └── constitution.md       # Constitution do projeto (regras não-negociáveis)

.github/skills/
├── speckit-specify/
├── speckit-plan/
├── speckit-tasks/
├── speckit-implement/
├── speckit-constitution/
├── speckit-checklist/
└── speckit-taskstoissues/
```

### Comandos

```
/speckit.specify    "descrição do que quer construir"
  → Cria spec.md com problema, solução, user stories

/speckit.plan
  → Gera plan.md com arquitetura, decisões, dependências

/speckit.tasks
  → Gera tasks.md com tarefas numeradas, blocos de código, acceptance criteria

/speckit.implement
  → Executa tarefas uma a uma, com review gate entre elas

/speckit.constitution
  → Revisa/gera a constitution do projeto

/speckit.checklist
  → Gera checklist de verificação para uma feature

/speckit.taskstoissues
  → Converte tasks em GitHub Issues (usa .github/agents/speckit.taskstoissues.agent.md)
```

### Workflow completo para feature nova

1. `/speckit.specify` → escreve o spec
2. `/speckit.plan` → planeia a implementação
3. `/speckit.tasks` → quebra em tarefas
4. `/speckit.implement` → implementa com gates de review
5. Opcional: `/speckit.taskstoissues` → cria issues no GitHub

**Integrações suportadas pelo workflow:** `claude`, `copilot`, `gemini`, `opencode` (seleciona-se na execução).

---

## 3. SKILLS (Ecossistema Matt Pocock)

Instaladas via `skills-lock.json` — **45 skills** no total. Cada skill é um workflow de engineering/auto-helpo.

### Engineering (spec / código)

| Skill | Gatilho de uso |
|---|---|
| `speckit.*` | Já coberto na seção 2 |
| `implement` / `implement-spec` | Implementar specs/tickets |
| `tdd` | TDD: red → green → refactor |
| `code-review` | Review de branch/PR (Standards + Spec, em paralelo) |
| `diagnosing-bugs` | Debug sistemático: 4 fases |
| `codebase-design` | Vocabulário para design de módulos profundos |
| `improve-codebase-architecture` | Scan + relatório HTML + grill por oportunidade |
| `wayfinder` | Planejar trabalho grande como mapa de decision tickets |
| `prototype` | Protótipo throwaway para testar ideias |
| `research` | Pesquisa com fontes confiáveis, salva em markdown |
| `spike` | Experimento para validar ideia antes do build |
| `systematic-debugging` | Root cause debugging em 4 fases |

### Productivity / Planning

| Skill | Gatilho de uso |
|---|---|
| `grill-me` | Questionar decisões antes de implementar |
| `grilling` | Grill o usuário sobre plan/decision/idea |
| `grill-with-docs` | Grill + cria docs (ADR/glossário) |
| `ask-matt` | Router: pergunta qual skill/flow se encaixa |
| `handoff` | Compactar conversa para handoff document |
| `to-spec` | Converter conversa em spec (sem entrevista) |
| `to-tickets` | Quebrar plan/spec em tickets numerados |
| `teach` | Ensinar conceito |
| `loop-me` | Grill spec de workflows que quer construir |
| `wait-what` | Re-pitch quando a mensagem anterior não landou |
| `retro` | Retrospectiva de sessão de coding |

### Misc (não crítico para o fluxo diário)

`scaffold-exercises`, `setup-pre-commit`, `setup-ts-deep-modules`, `migrate-to-shoehorn`, `wizard`, `writing-*` (writing-beats, writing-fragments, writing-shape, writing-for-agents), `email-*` (email-inbox-triage, himalaya)

### Como invocar

- **VS Code:** `Ctrl+Shift+P` → digita o nome da skill
- **Hermes Agent:** usa o sistema de skills do agente (ex: `/skill:<nome>`)
- **Diretório físico:** `C:\Users\raniel.veiga\Desktop\DASHBOARD - Copia\.github\skills\` (skills do SpecKit) e as skills de engenharia ficam no perfil do Hermes

---

## 4. EXTENSÕES DO VS CODE (16 extensões)

| Categoria | Extensões |
|---|---|
| **AI Coding** | Claude Dev, Kilo Code, SpecKit Assistant |
| **Python** | Python, Pylance, Debugpy, Python Env Manager |
| **SQL / MSSQL** | MSSQL, SQL Bindings, SQL Database Projects, Data Workspace |
| **DevOps / Runtime** | .NET Runtime, Containers, PowerShell |
| **UI** | Fluent Icons |
| **Custom** | DSH-VSCode (jager.dsh-vscode) |

**Configurações ativas** (`.vscode/settings.json`):

```json
{
  "chat.promptFilesRecommendations": {
    "speckit.constitution": true,
    "speckit.specify": true,
    "speckit.plan": true,
    "speckit.tasks": true,
    "speckit.implement": true
  },
  "chat.tools.terminal.autoApprove": {
    ".specify/scripts/bash/": true,
    ".specify/scripts/powershell/": true
  },
  "python-envs.defaultEnvManager": "ms-python.python:system"
}
```

- Prompts do SpecKit são recomendados automaticamente no chat AI
- Scripts em `.specify/scripts/bash/` e `.specify/scripts/powershell/` são auto-approvados pelo terminal AI

---

## 5. CONSTITUIÇÃO DO PROJETO (não-negociável)

Arquivo: `.specify/memory/constitution.md` — **Version 1.0.0, Ratified 2026-07-15**

### Core Principles

**I. SQL Query Encapsulation**
Todas as queries ficam em `queries/`, organizados por domínio de página. NUNCA SQL inline em páginas.
- Query functions: recebem params validados, retornam DataFrame/dict, tem docstring, são independentemente testáveis.

**II. Page-Driven Query Execution**
Páginas (`pages/page_*.py`) são orchestrators: importam query functions, chamam com params de session, renderizam com Streamlit, cacheiam com `@st.cache_data` ou `@st.cache_resource`.

**III. Test-First Validation (NON-NEGOTIABLE)**
Tests executam query functions diretamente.
- Unit tests: query functions isoladas com fixtures mockados
- Integration tests: queries contra staging
- Page validation: tests importam e chamam query functions como a página faz
- Partial failures reportados imediatamente

**IV. Role-Based Access Control (RBAC)**
- `streamlit_authenticator` para credenciais (config em `config.yaml`)
- `st.session_state["user_role"]` após login
- Páginas checam permissões antes de renderizar seções sensíveis
- Query functions recebem user context para filtrar resultados

**V. State & Caching Discipline**
- `st.session_state`: identidade do usuário + dados transientes de página (filters, selections)
- `@st.cache_data`: resultados de queries cacheados (TTL default ou expiry explícito)
- Cache functions: invalidação documentada (ex: reset diário às 04:00)
- Evitar DataFrames no session_state; usar cache keys

### Technology Stack

- **Framework:** Streamlit
- **Data Access:** pyodbc (SQL Server via ODBC), queries em `queries/`
- **Auth:** streamlit-authenticator com YAML config
- **Visualization:** Plotly
- **Data Handling:** pandas (DataFrames como estrutura canônica)
- **Dependencies:** `requirements.txt` com versions pinned
- **Pages Organized By:** Business domain (`venda_geral`, `financeiro`, `estoque`, etc.)

### Development Workflow

**Query Development:**
1. Write query function em `queries/*_queries.py`
2. Include parameter validation + docstring
3. Write integration test contra staging
4. Test passes → função pronta

**Page Development:**
1. Import query functions de `queries/`
2. Call functions com session-aware params
3. Add Streamlit rendering
4. Write page-level test chamando query functions
5. Verify rendered output structure

**Testing & Quality Gates:**
- Todas as query functions têm integration tests
- Todas as páginas têm tests validando query calls
- Antes de merge: full test suite, todos passando
- Cache invalidation logic testada (daily reset, event-driven clears)

### Governance

Esta constitution supersede practices ad-hoc. Emendas exigem:
1. Documented rationale + impact assessment
2. Update deste arquivo com nova versão
3. Re-run de todos os template sync checks (plan, spec, tasks)

PRs/code reviews devem verificar:
- Queries encapsuladas em `queries/`, não embedded em páginas
- Tests executam diretamente query e page-level code
- Role-based checks presentes em páginas sensíveis
- Caching strategy documentada e validada

---

## 6. ESTRUTURA DO PROJETO

```
DASHBOARD - Copia/
├── main.py                    # Página de entrada (sidebar gradiente, navegação)
├── app_config.py              # Configuração do app
├── cache_loaders.py           # Funções cacheadas centralizadas + warm_all_caches()
│                              #  (movido daqui para cá das páginas — reuse entre app e warming)
├── ui_theme.py                # CSS/tema (a refactorar → .streamlit/config.toml)
├── ui_status.py               # Componentes de status
├── analytics.py               # Análises de dados
├── data_quality.py            # Validação de qualidade de dados
├── access_rules.py            # Regras de acesso RBAC
├── access_logging.py          # Logging de acesso
├── config.yaml                # Credenciais (hash bcrypt), cookies, configuração de auth
├── requirements.txt           # Dependencies
├── gerador_hash.py            # Gerador de hash (BCrypt)
├── gerador_key.py             # Gerador de key
├── run_integrity_test.py     # Script de integridade
├── pages/
│   ├── _cache_warm.py         # Página de cache warming (protected por warm_key em secrets.toml)
│   ├── page_venda_geral.py    # Página principal de vendas
│   ├── page_painel.py         # Painel
│   ├── page_estoque.py        # Estoque
│   ├── page_setores.py        # Setores
│   └── ... (12 páginas total)
├── queries/                   # Módulo de queries — organizado por domínio de página
├── modules/                   # Módulos compartilhados
├── docs/                      # Documentação do projeto
├── specs/                     # Specs de features (ex: streamlit-1.63-improvements)
├── tests/                     # Testes (5 testes unitários)
├── .specify/                  # SpecKit workspace (ver seção 2)
├── .github/
│   ├── skills/                # Skills do SpecKit
│   └── agents/                # Agent configs (speckit.taskstoissues.agent.md)
├── .vscode/
│   └── settings.json          # Config VS Code (ver seção 4)
├── .scratch/                  # Issue tracker local (Markdown, sob .scratch/<feature>/)
├── .streamlit/                # Config Streamlit (secrets.toml — NÃO COMMITAR, config.toml — a criar)
├── logs/                      # Logs do app
├── .pytest_cache/
├── .venv/                     # Virtualenv
└── __pycache__/
```

---

## 7. COMANDOS DE AI RÁPIDOS (memorizar)

| Ação | Comando |
|---|---|
| Criar spec novo | `/speckit.specify "feature X"` |
| Fazer plan | `/speckit.plan` |
| Quebrar em tasks | `/speckit.tasks` |
| Implementar tarefas | `/speckit.implement` |
| Review de código | `/code-review` |
| Debugar algo | `/diagnosing-bugs` |
| Qual skill usar? | `/ask-matt` |
| Questionar decisão | `/grill-me` |
| Prototipar ideia | `/prototype` |
| Tasks → GitHub Issues | `/speckit.taskstoissues` |
| Conversa → spec | `/to-spec` |
| Conversa → tickets | `/to-tickets` |
| Testar feature para spec | `/implement-spec` |
| Sair de impasse | `/wait-what` |
| Retrospectiva | `/retro` |

---

## 8. ANTI-PATTERNS (o que nao fazer)

- **SQL inline nas páginas** → viola Constitution I. Colocar em `queries/`.
- **Duplicar funções de negócio** entre páginas → extrair para `modules/`.
- **`renderizar_pagina_*()` wrapper** nas páginas → páginas devem ser scripts Streamlit diretos.
- **CSS inline espalhado** em 3+ arquivos → migrar para `.streamlit/config.toml`.
- **`st.set_option("client.disableDataExport", True)`** em cada página → fazer uma vez em `main.py`.
- **`unsafe_allow_html=True`** com CSS injetado → usar elementos nativos do Streamlit.
- **Commit `.streamlit/secrets.toml`** → secrets nunca vão para o repo.
- **DataFrame direto no session_state** → usar cache keys.

---

## 9. CACHE WARMING (infra)

O app usa `@st.cache_data` para queries caras. Para garantir que o cache está quente antes do primeiro usuário:

**Mecânica:**
- `cache_loaders.py` contém todas as functions decoradas com `@st.cache_data`
- `pages/_cache_warm.py` — página que chama `warm_all_caches()` para preencher o cache do processo
- Acesso protegido por `warm_key` (configurar em `.streamlit/secrets.toml`)

**Agendamento (Windows Task Scheduler):**
- Criar tarefa diária às 04:00
- Ação: `powershell -ExecutionPolicy Bypass -File "C:\Users\raniel.veiga\Desktop\DASHBOARD - Copia\scripts\warm_cache.ps1" -Secret "<secret>"`
- Ou invocar direto: `Invoke-WebRequest -Uri 'http://localhost:8501/?page=_cache_warm&warm_key=<secret>'`

**Constraints:**
- O Streamlit app deve estar rodando às 04:00
- Se múltiplos processos/containers, agendar request para cada instância
- Secreto nunca entra no repo

---

## 10. TRILHAS DE MELHORIA (Streamlit 1.63 — já documentado)

Arquivo: `.scratch/streamlit-1.63-improvements/spec.md`

Oferece 7 trilhas independentes (pode implementar isoladamente):

1. **Tema e CSS** — migrar de CSS inline para `.streamlit/config.toml`
2. **Fragments e filtros** — `@st.fragment(key=...)` + `st.rerun("key")` para cadeias dependentes
3. **Cache e performance** — `max_entries` em caches, `on_change="ignore"`, `cacheBackgroundRefreshTTLMultiplier`
4. **Organização do código** — extrair funções compartilhadas para módulo, remover wrapper functions, centralizar `disableDataExport`
5. **Seleção e widgets** — `select_all="never"/"threshold"`, `wrap=False` em labels
6. **Testes** — cobertura de `data_quality.summarize_data_quality`, `access_rules.resolve_effective_access`
7. **Query construction** — parameter binding (SQLAlchemy/pandas) ao invés de f-string interpolation

**Novidades Streamlit 1.63 usadas:**
- `@st.fragment` + `st.rerun` — event-scoped fragment reruns
- `on_change="ignore"` — slider/text_input update sem rerun
- `type="step"` — timeline connected para expander/status
- `wrap` parameter estendido — `st.pills`, `st.segmented_control`, text elements
- `st.multiselect` com `select_all` — controle bulk select
- `st.title/header/subheader` com `icon` — Material Symbol/emoji nativo
- AppTest: `at.container(key=...)`, `at.get_by_key()`, `switch_page()`
- `runner.cacheBackgroundRefreshTTLMultiplier`

---

## 11. QUEM SOU EU (contexto do ambiente)

- **Modelo:** Solar Pro4 (Upstage AI) via Hermes Agent
- **Plataforma:** CLI (terminal), não VS Code extension
- **Papel:** Agent de coding — implementa, debuga, reviewa, planeja
- **Quando usar Hermes vs extensões VS Code:**
  - Uso Hermes para: tdd, code review, debugging, tasks paralelas, subagent delegation
  - Uso VS Code extensions para: coding assistência inline, chat rápido

---

## 12. O QUE NÃO ESTÁ AQUI (deliberadamente)

- **Plugins do VS Code além das extensões listadas** — não há plugin system separado; extensões = plugins
- **MCP Servers** — não há MCP Servers configurados neste projeto; se necessário, configurar via extensão ou configuração do agente
- **Hooks customizados** — `.specify/extensions.yml` não existe (hooks do SpecKit não são configurados)
- **Agents customizados** — apenas os agent configs do SpecKit em `.github/agents/` (speckit.taskstoissues.agent.md)
- **config.yaml de Hermes** — está em `C:\Users\raniel.veiga\Desktop\DASHBOARD - Copia\config.yaml` (contém credentials de auth do app, não de Hermes)

---

## 13. PRÓXIMOS PASSOS SUGERIDOS

1. **Criar `.streamlit/config.toml`** com tema do app (trilha 1 da melhoria Streamlit 1.63)
2. **Migrar CSS inline** de `ui_theme.py`, `main.py`, `ui_status.py` para config.toml
3. **Implementar fragment reruns** em páginas com cadeias de filtros dependentes (trilha 2)
4. **Extrair funções compartilhadas** para `modules/` (trilha 4)
5. **Configurar `.streamlit/secrets.toml`** com `warm_key` (se não tiver)
6. **Verificar se script `scripts/warm_cache.ps1` existe** e criar se não existir

---

**Versão do guia:** 1.0  
**Atualizado:** 2026-09-29  
**Próxima revisão:** quando novas skills, tools ou workflows forem adicionadas ao ecossistema