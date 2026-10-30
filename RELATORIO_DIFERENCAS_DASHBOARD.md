# Relatório de diferenças: `DASHBOARD - Copia` x `DASHBOARD`

**Data da análise:** 22/09/2026  
**Projeto de produção:** `C:\Users\raniel.veiga\Desktop\DASHBOARD`  
**Projeto de testes analisado:** `C:\Users\raniel.veiga\Desktop\DASHBOARD - Copia`

## Garantia de escopo

O diretório de produção foi somente lido. Nenhum arquivo, configuração, cache ou
log foi alterado em `DASHBOARD`.

## Resumo executivo

| Área | `DASHBOARD - Copia` | `DASHBOARD` |
|---|---:|---:|
| Arquivos considerados (excluindo ambiente/cache/runtime) | 321 | 254 |
| Apenas nesse projeto | 71 | 4 |
| Mesmo caminho, conteúdo diferente | 21 | 21 |
| Mesmo caminho e mesmo SHA-256 | 229 | 229 |
| Arquivos totais incluindo ambiente/cache/runtime | 209 | 26.655 |
| Diretórios totais incluindo ambiente/cache/runtime | 135 | 3.193 |

A contagem ampla inclui artefatos locais e não deve ser usada para decidir uma
migração. A produção contém `.venv`, `.kilo` e `.kilocode`; a cópia contém uma
quantidade muito menor de ambiente local. Esses diretórios não devem ser
copiados entre projetos.

## Diferenças funcionais e de configuração

### 1. Entrada, navegação e apresentação (`main.py`)

- A cópia importa `apply_dashboard_theme` e `page_header` de `ui_theme.py`,
  desabilita exportação de dados e usa o tema compartilhado.
- A produção remove esse tema compartilhado e injeta CSS diretamente com
  `unsafe_allow_html=True`, incluindo sidebar vermelha e estilos de métricas.
- A cópia registra `page_experience.py` (“Competição Experience”).
- A produção registra `page_acompanhamento.py` (“Acompanhamento do Dia”) e
  `page_pedidos.py` (“Acompanhamento de Pedidos”).
- A lista por perfil mudou:
  - **admin/diretoria:** cópia inclui Experience; produção inclui
    Acompanhamento e Pedidos.
  - **gerente/inteligência:** cópia inclui Análise e Previsão e Estoque;
    produção inclui Acompanhamento e Pedidos e não inclui Análise e Previsão.
  - **supervisor:** cópia não inclui Painel; produção inclui Painel,
    Acompanhamento e Pedidos.
  - **televendas:** cópia inclui Análise e Previsão; produção inclui
    Setores, Comissão, Acompanhamento e Pedidos e não inclui Análise e Previsão.
- Essa mudança altera diretamente o RBAC percebido pelos usuários; não é apenas
  uma diferença visual.

### 2. Carregamento, cache e warming (`cache_loaders.py`)

A cópia possui loaders centralizados para Comissão, Estoque, Positivação,
Financeiro, Painel, Comparativo e listas de supervisores/vendedores/televendas.
Também possui `warm_all_caches()` abrangente e TTLs separados (24 horas geral e
1 hora para Estoque).

A produção substitui grande parte desses loaders por:

- loaders de base única, Comparativo, Experience e Pedidos do dia;
- TTL geral de 1 hora;
- `_executar_warming()` e scheduler em thread;
- `start_hourly_scheduler()`, `stop_hourly_scheduler()`,
  `get_scheduler_state()` e `is_scheduler_running()`.

Consequências: copiar apenas `main.py` da produção para a cópia quebra
referências às páginas e loaders da cópia; copiar apenas `cache_loaders.py` da
produção pode remover as funções usadas pelas páginas Financeiro, Comissão,
Estoque, Positivação e listas de filtros da cópia.

### 3. Página de aquecimento (`pages/_cache_warm.py`)

- A cópia usa `warm_all_caches`, estado `warm_paused`, botão de pausar/retomar e
  suporta chave por query parameter `warm_key`.
- A produção usa autorização em `st.session_state`, controles do scheduler,
  `_executar_warming()` e estado de thread.
- A produção contém a função interna `_painel_status`; a cópia contém
  `toggle_warm_pause`.
- A secret `warm_key` existe estruturalmente nos dois arquivos
  `.streamlit/secrets.toml`, mas os arquivos têm conteúdo diferente. Os valores
  não foram reproduzidos neste relatório.

### 4. Páginas e consultas exclusivas

Somente na cópia:

- `pages/page_experience.py`
- `queries/experience_queries.py`
- `modules/kpi_utils.py`

Somente na produção:

- `pages/page_acompanhamento.py`
- `pages/page_pedidos.py`
- `queries/pedidos_2_queries.py`
- `queries/pedidos_queries.py`

### 5. Configuração de usuários (`config.yaml`)

- Ambos têm 13 usuários e os mesmos grupos de função.
- A cópia não tem campos `supervisor` explícitos nos usuários.
- A produção tem 3 campos `supervisor`, associados aos usuários de supervisão
  (`VITOR`, `IUSSEF` e `CARLINHO`), além de diferenças de identificador/nome
  nesses usuários.
- `config.yaml` e `.streamlit/secrets.toml` têm hashes diferentes.
- Esses arquivos contêm credenciais, chaves e dados de conexão; não devem ser
  sobrescritos cegamente nem versionados. A migração deve usar variáveis de
  ambiente/segredos locais.

### 6. Tema e ambiente Streamlit

- Apenas a cópia possui `.streamlit/config.toml`, com uma seção `[theme]`.
- A produção não possui esse arquivo.
- Ambos possuem `.streamlit/secrets.toml`, com seções
  `[database]`, `[general]` e `[client]`; os tamanhos e conteúdo diferem.
- A cópia também possui `AGENTS.md`, `README.md`, `.vscode/settings.json` e
  toda a configuração Speckit (`.github`, `.specify` e skills Speckit).

## Arquivos com conteúdo diferente

Os 21 caminhos abaixo têm o mesmo nome nos dois projetos, mas conteúdo diferente:

```text
.streamlit/secrets.toml
cache_loaders.py
config.yaml
main.py
pages/_cache_warm.py
pages/page_analise_previsao.py
pages/page_comissao.py
pages/page_comparativo.py
pages/page_estoque.py
pages/page_financeiro.py
pages/page_painel.py
pages/page_positivacao.py
pages/page_setores.py
pages/page_venda_geral.py
queries/comparativo_queries.py
queries/estoque_queries.py
queries/financeiro_queries.py
queries/painel_queries.py
queries/setores_queries.py
queries/vendas_queries.py
ui_status.py
```

Observações relevantes nos SQLs:

- A produção acrescenta `WITH (NOLOCK)` em diversas consultas.
- `comparativo_queries.py` adiciona três vendedores/identificadores e altera
  joins, aliases e regras de supervisor.
- `painel_queries.py` e `vendas_queries.py` da cópia expõem funções de listas
  de supervisores, vendedores e televendas; as versões de produção expõem
  apenas `get_dados_brutos`.
- `page_painel.py` e `page_venda_geral.py` têm diferenças extensas na forma de
  calcular KPIs, projeções, filtros e gráficos.
- As páginas de Comissão, Estoque, Financeiro e Positivação da produção incluem
  loaders diretos/cacheados próprios (`get_connection` e funções de carga);
  as versões da cópia usam a camada central `cache_loaders.py`.
- `ui_status.py` difere apenas em conteúdo/formatação, mantendo os três
  símbolos principais.

## Arquivos somente na cópia (71)

### Skills e configuração de agentes

```text
.agents/skills/speckit-analyze/SKILL.md
.agents/skills/speckit-checklist/SKILL.md
.agents/skills/speckit-clarify/SKILL.md
.agents/skills/speckit-constitution/SKILL.md
.agents/skills/speckit-converge/SKILL.md
.agents/skills/speckit-implement/SKILL.md
.agents/skills/speckit-plan/SKILL.md
.agents/skills/speckit-specify/SKILL.md
.agents/skills/speckit-tasks/SKILL.md
.agents/skills/speckit-taskstoissues/SKILL.md
.github/agents/speckit.analyze.agent.md
.github/agents/speckit.checklist.agent.md
.github/agents/speckit.clarify.agent.md
.github/agents/speckit.constitution.agent.md
.github/agents/speckit.converge.agent.md
.github/agents/speckit.implement.agent.md
.github/agents/speckit.plan.agent.md
.github/agents/speckit.specify.agent.md
.github/agents/speckit.tasks.agent.md
.github/agents/speckit.taskstoissues.agent.md
.github/copilot-instructions.md
.github/prompts/speckit.analyze.prompt.md
.github/prompts/speckit.checklist.prompt.md
.github/prompts/speckit.clarify.prompt.md
.github/prompts/speckit.constitution.prompt.md
.github/prompts/speckit.converge.prompt.md
.github/prompts/speckit.implement.prompt.md
.github/prompts/speckit.plan.prompt.md
.github/prompts/speckit.specify.prompt.md
.github/prompts/speckit.tasks.prompt.md
.github/prompts/speckit.taskstoissues.prompt.md
.github/skills/speckit-analyze/SKILL.md
.github/skills/speckit-checklist/SKILL.md
.github/skills/speckit-clarify/SKILL.md
.github/skills/speckit-constitution/SKILL.md
.github/skills/speckit-converge/SKILL.md
.github/skills/speckit-implement/SKILL.md
.github/skills/speckit-plan/SKILL.md
.github/skills/speckit-specify/SKILL.md
.github/skills/speckit-tasks/SKILL.md
.github/skills/speckit-taskstoissues/SKILL.md
.specify/feature.json
.specify/init-options.json
.specify/integration.json
.specify/integrations/copilot.manifest.json
.specify/integrations/speckit.manifest.json
.specify/memory/.constitution-template.json
.specify/memory/constitution.md
.specify/memory/constitution.md.new
.specify/scripts/powershell/check-prerequisites.ps1
.specify/scripts/powershell/common.ps1
.specify/scripts/powershell/create-new-feature.ps1
.specify/scripts/powershell/setup-plan.ps1
.specify/scripts/powershell/setup-tasks.ps1
.specify/templates/checklist-template.md
.specify/templates/constitution-template.md
.specify/templates/plan-template.md
.specify/templates/spec-template.md
.specify/templates/tasks-template.md
.specify/workflows/speckit/workflow.yml
.specify/workflows/workflow-registry.json
```

### Código/configuração adicional

```text
.streamlit/config.toml
.vscode/settings.json
AGENTS.md
README.md
modules/kpi_utils.py
pages/page_experience.py
queries/experience_queries.py
tests/unit/test_access_rules.py
tests/unit/test_analytics.py
tests/unit/test_data_quality.py
```

## Arquivos somente na produção (4)

```text
pages/page_acompanhamento.py
pages/page_pedidos.py
queries/pedidos_2_queries.py
queries/pedidos_queries.py
```

## Artefatos locais que não devem ser migrados

Não copiar, mesclar ou versionar:

- `.venv/`;
- `.kilo/` e `.kilocode/`;
- `__pycache__/` e `.pytest_cache/`;
- `logs/`;
- `.scratch/` de uma máquina para outra, salvo se o objetivo for preservar
  deliberadamente um histórico de trabalho;
- `.streamlit/secrets.toml` sem revisão manual dos segredos.

## Estratégia recomendada de migração

### Recomendação principal: merge seletivo em uma cópia de segurança

Não recomendo “sobrescrever `DASHBOARD - Copia` com `DASHBOARD`”. Recomendo:

1. Criar uma terceira cópia de segurança do projeto de testes.
2. Preservar integralmente na cópia:
   - `.agents`, `.github`, `.specify`, `.vscode`;
   - `AGENTS.md`, `README.md` e `.streamlit/config.toml`;
   - skills e testes adicionais;
   - `modules/kpi_utils.py`, Experience e seus testes.
3. Migrar da produção somente as quatro páginas/consultas exclusivas:
   `page_acompanhamento.py`, `page_pedidos.py`,
   `pedidos_2_queries.py` e `pedidos_queries.py`.
4. Integrar suas páginas no `main.py` da cópia, mantendo o tema e decidindo
   explicitamente a matriz de acesso por perfil.
5. Não substituir `cache_loaders.py` inteiro. Adaptar os loaders de Pedidos e
   o scheduler da produção à camada central da cópia, preservando as funções
   Financeiro/Comissão/Estoque/Positivação/Experience já usadas pelos testes.
6. Comparar e integrar os SQLs alterados um por vez, principalmente
   `painel_queries.py`, `vendas_queries.py` e `comparativo_queries.py`.
7. Migrar os três filtros `supervisor` de `config.yaml` para a configuração de
   testes somente após confirmar que `access_rules.py` e os testes de escopo
   devem usar exatamente esses nomes.
8. Manter segredos separados. Configurar `DASHBOARD_CONFIG_PATH`,
   `DASHBOARD_CREDENTIALS_JSON`, `DASHBOARD_COOKIE_*` e os segredos Streamlit
   por ambiente.
9. Rodar a suíte unitária e uma verificação manual de cada papel antes de
   considerar a cópia pronta.

### Ordem segura de integração

```text
1. páginas/queries de Pedidos e Acompanhamento
2. integração da navegação e RBAC
3. consultas SQL específicas, com testes/regressão
4. scheduler de warming, somente depois dos loaders
5. alterações de configuração/usuários
6. validação completa
```

### Critério de aceitação antes de substituir qualquer ambiente

- `python -m pytest tests/unit -q` sem regressões;
- teste de login de cada papel e conferência da lista de páginas;
- teste dos filtros de supervisor;
- teste de warming manual e scheduler, sem deixar thread duplicada;
- teste das páginas Experience, Pedidos, Acompanhamento, Financeiro, Estoque,
  Comissão e Positivação;
- confirmação de que `.streamlit/secrets.toml` não foi sobrescrito;
- comparação final por hashes e revisão dos SQLs.

## Validação realizada

Na cópia de testes, a suíte existente foi executada com sucesso:

```text
58 passed in 17.53s
```

Nenhum teste, build ou comando de escrita foi executado no projeto de produção.
