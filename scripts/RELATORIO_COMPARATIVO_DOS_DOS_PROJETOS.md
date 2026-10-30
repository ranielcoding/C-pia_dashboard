# Relatório Comparativo: DASHBOARD - Copia vs DASHBOARD MIGRAÇÃO

**Data**: 2026-09-29  
**Versão origem**: DASHBOARD - Copia (produção, com SQL real)  
**Versão destino**: DASHBOARD MIGRAÇÃO (anonimização tentativa, dados hardcoded)  
**Objetivo do relatório**: Documentar todas as diferenças entre os dois projetos para embasar o Spec-003 (Query Vault).

---

## 1. Visão Geral das Mudanças

A versão de migração substituiu **todo o acesso ao banco de dados** por dados fictícios hardcoded, removeu as dependências de conectividade (SQLAlchemy, pyodbc) e manteve apenas a estrutura de UI. O resultado é um app Streamlit que roda off-line com dados inventados, mas **não é mais funcional como dashboard real**.

A operação tocou **31 arquivos** de forma diferente entre os dois projetos.

---

## 2. Diferenças por Camada

### 2.1 Módulo `queries/` — 13 arquivos diferentes

| Arquivo | O que mudou | Impacto |
|---|---|---|
| `queries/__init__.py` | Vazio (produção) → contém docstring explicando que é módulo anonimizado com stubs (migração) | Quebra imports em produção; migração usa imports diretos nos loaders |
| `vendas_queries.py` | SQL real com `f"""..."""` retornado por `get_dados_brutos(data_ini, data_fim)` → DataFrame hardcoded com dados fictícios + `TELEVENDAS_MAP` anonimizado (OPER_TST_* → 10001...) | Função inteira substituída; perde parametrização por data; perde mapeamento real de televendedoras |
| `comparativo_queries.py` | SQL real em `get_dados_agrupados(data_ini, data_fim)` → função que retorna DataFrame fictício com colunas esperadas pelas páginas | Perde filtro por data, perde dados reais; mantém assinatura da função |
| `comissao_queries.py` | `obter_dados_comissao(conexao, data_inicio, data_fim)` com SQL real → função com DataFrame fictício | Perde parametrização por período; perde relação com tabela `titulo_parcela_comissao` |
| `estoque_queries.py` | `obter_dados_estoque(conexao)` com SQL CTE real (WMSRX.dbo.lote, WMSRX.dbo.lote_estoque, etc.) → DataFrame fictício | Perde toda a lógica de estoque (WMS, validade, vendas 90 dias) |
| `experience_queries.py` | Duas funções reais (`obter_dados_experience`, `obter_dados_vendas_dia`) com SQL → funções com DataFrames fictícios | Perde filtros por fornecedores reais (B.BRASIL, NATCOFARMA, etc.) e por período dinâmico |
| `financeiro_queries.py` | 7 funções SQL com CTE base (`_get_base_contas_cte`) + *6 funções derivadas (get_kpis_financeiros, get_fluxo_caixa_mensal, etc.) → stubs que retornam None | Perde completamente o módulo financeiro |
| `painel_queries.py` | SQL real → DataFrame fictício | Perde dados do painel geral |
| `pedidos_2_queries.py` | Duas funções SQL reais (`obter_dados_experience`, `obter_dados_vendas_dia`) → DataFrames fictícios | Perde vendas do dia e acumulado do mês |
| `pedidos_queries.py` | Duas funções SQL reais (`obter_pedidos_do_dia`, `obter_detalhamento_pedidos_do_dia`) → DataFrames fictícios | Perde lista de pedidos do dia e detalhamento |
| `positivacao_queries.py` | SQL real com 13 joins (produto_venda, entidade, cep, cidade, bandeira, etc.) → DataFrame fictício | Perde positivação real (3 meses de vendas por cliente/setor/supervisor) |
| `setores_queries.py` | SQL real com joins (entidade, entidade_ender, cep, cidade, setor_venda) → DataFrame fictício | Perde lista de setores com supervisores reais |
| `teste.py` | Script utility com Regex + pandas (leitura de Excel com planilha de contatos) → script equivalente com dados fictícios | Diferença menor; script utility mantido mas com dados de teste diferentes |

**Padrão identificado**: Todas as funções de query na migração foram substituídas por funções que retornam DataFrames com dados inventados, mantendo o nome da função e (quando possível) as colunas esperadas. Não há mais execução de SQL.

---

### 2.2 `cache_loaders.py` — diferencial crítico

**Versão produção** (723 linhas):
- Usa `SQLAlchemy` + `pyodbc` para conectar ao SQL Server
- Lê `st.secrets["database"]` para montar connection string
- Gerencia pool de conexões (`_engine`) com `create_engine`
- Usa `ContextVar` para rastrear origem da execução (page / background / scheduler)
- TTL de 75 minutos com `refresh_mode="background"`
- Double-buffering com `_get_pointer_registry()` (active_key / pending_key / version)
- `warm_all_caches()` publica atomicamente novo snapshot
- Scheduler server-side com thread demoníaca
- Todas as funções de cache recebem `cache_key` como parâmetro

**Versão migração** (621 linhas):
- Substituiu SQLAlchemy por `_FakeConnection` (context manager que não abre banco)
- Removeu `ContextVar`, `get_connection()` com SQLAlchemy
- TTL simplificado para 3600s (1h)
- Double-buffering mantido mas com estrutura simplificada (`_active_cache_ptr`)
- `warm_all_caches()` mantido mas chamando loaders fictícios
- Scheduler mantido com mesma estrutura
- `get_connection()` retorna `_FakeConnection()` — inócuo, não conecta

**Impacto**: A arquitetura de cache e warming foi preservada, mas toda a camada de acesso ao banco foi neutralizada. O app migrado roda, mas mostra dados inventados.

**Ou seja**: os loaders sobreviveram à anonimização, mas o conteúdo que eles carregam (as queries) foi substituído.

---

### 2.3 Páginas que diferem

| Página | Alterações |
|---|---|
| `page_venda_geral.py` | Lógica de UI preservada; importa `cache_loaders` (novo loader) e `queries.vendas_queries` (novo mapeamento anonimizado); a lógica de filtro de televendas usa `TELEVENDAS_MAP` anonimizado |
| `page_painel.py` | Alterações similares — importa loaders e queries da versão anonimizada |
| `page_comparativo.py` | Alterações similares |
| `page_experience.py` | Alterações similares |
| `page_financeiro.py` | Alterações similares — importa financeiro_queries que na migração retorna None |
| `_cache_warm.py` | Versão produção exige `warm_key` no secrets e para se não encontrado; versão migração tem fallback para variável de ambiente `DASHBOARD_WARM_KEY` com valor fictício |

---

### 2.4 Arquivos de suporte

| Arquivo | Mudança |
|---|---|
| `access_rules.py` | Diferente — provavelmente ajustado para usar dados fictícios nos testes de supervisor |
| `app_config.py` | Diferente — ajustes de configuração |
| `gerador_hash.py` | Diferente — provavelmente ajustado |

---

### 2.5 Documentação e configuração

| Arquivo | Mudança |
|---|---|
| `README.md` | Diferente — provavelmente atualizado para refletir a versão anonimizada |
| `RELATORIO_DIFERENCAS_DASHBOARD.md` | Diferente — existe na migração, documentando as diferenças |
| `requirements.txt` | Diferente — removida dependência de SQLAlchemy/pyodbc na migração |

---

### 2.6 Testes

| Teste | Mudança |
|---|---|
| `test_access_rules.py` | Diferente — provavelmente ajustado para usar dados fictícios |
| `test_supervisor_login_scope.py` | Diferente |
| `test_televendas_filter_regression.py` | Diferente — usa códigos hardcodeados nas assertions (17414, 8338, 17141) |

---

## 3. O que foi preservado

A migração foi seletiva: preservou a estrutura do app Streamlit (páginas, UI, cache, warming, scheduler) mas neutralizou a camada de dados. O app roda, mostra dashboards com dados fictícios — mas não é mais o dashboard real.

**O que sobrou intacto:**
- Estrutura de páginas e navegação
- Lógica de UI (filtros, gráficos, KPIs)
- Máquina de cache (double-buffering, versionamento)
- Scheduler de warming
- Autenticação (config.yaml, credential structure)
- `ui_theme.py`, `ui_status.py`

**O que foi neutralizado:**
- Todo o conteúdo de `queries/` (SQL → DataFrames fictícios)
- Conexão com banco (SQLAlchemy → FakeConnection)
- Dependências de banco (requirements.txt)

---

## 4. Problemas da abordagem atual da migração

1. **Dados hardcoded**: Cada query agora tem dados inventados estáticos. Sem parametrização por data — o dashboard sempre mostra os mesmos dados.
2. **Duplicação de esforço**: Para atualizar uma query, é preciso alterar o código em `queries/*.py` E garantir que os dados fictícios correspondam.
3. **Sem transição suave**: A migração é binária — ou o app roda com dados reais (produção) ou com dados fictícios (migração). Não há modo híbrido.
4. **Testes comprometidos**: Os testes agora validam contra dados fictícios, não contra a lógica real das queries.
5. **TELEVENDAS_MAP frágil**: O mapeamento de televendedoras ficou com códigos TST, perdendo a relação real entre operadores e códigos.

---

## 5. Por que a solução proposta (Query Vault em secrets.toml) é superior

A proposta é: **manter as queries SQL reais nos `queries/*.py`, mas ler o conteúdo sensível (a própria SQL string, os mapeamentos de códigos) do `st.secrets` em runtime.**

Isso resolve os problemas porque:

1. **O código permanece funcional em produção** — as queries continuam sendo as mesmas, executadas contra o banco real
2. **O repo é seguro para GitHub** — o que vai pro repo é o código que lê do secrets, não o conteúdo sensível; o `secrets.toml` real fica apenas no `.gitignore`
3. **Um `secrets.example.toml`** pode ser commitado com a estrutura (chaves, seções) e valores placeholder, servindo como documentação da estrutura esperada
4. **Transição reversível**: basta restaurar os arquivos originais e remover as leituras do `st.secrets` para voltar ao estado anterior
5. **Sem dados hardcoded**: as queries continuam parametrizeis por data, com a lógica real intacta

**Diferença principal em relação à migração atual**: a migração substituiu o conteúdo das queries por dados fictícios. A proposta Query Vault substitui a *origem* dos dados sensíveis (de hardcoded no Python para o secrets.toml) — mas mantém as queries reais sendo executadas.

---

## 6. Mapa de migração: o que vai para o secrets.toml

| Origem (queries/*.py) | Destino no secrets.toml | Tipo |
|---|---|---|
| `vendas_queries.get_dados_brutos` SQL | `[queries.vendas]` → `get_dados_brutos_sql` | string multilinha |
| `vendas_queries.TELEVENDAS_MAP` | `[maps.televendas]` | dict TOML |
| `comparativo_queries.get_dados_agrupados` SQL | `[queries.comparativo]` → `get_dados_agrupados_sql` | string multilinha |
| `comissao_queries.obter_dados_comissao` SQL | `[queries.comissao]` → `obter_dados_comissao_sql` | string multilinha |
| `estoque_queries.obter_dados_estoque` SQL | `[queries.estoque]` → `obter_dados_estoque_sql` | string multilinha |
| `experience_queries.obter_dados_experience` SQL | `[queries.experience]` → `obter_dados_experience_sql` | string multilinha |
| `experience_queries.obter_dados_vendas_dia` SQL | `[queries.experience]` → `obter_dados_vendas_dia_sql` | string multilinha |
| `financeiro_queries.*` (7 funções) | `[queries.financeiro]` → 7 chaves | strings multilinha |
| `painel_queries.*` | `[queries.painel]` | strings multilinha |
| `pedidos_2_queries.*` (2 funções) | `[queries.pedidos_2]` | strings multilinha |
| `pedidos_queries.*` (2 funções) | `[queries.pedidos]` | strings multilinha |
| `positivacao_queries.obter_dados_positivacao` SQL | `[queries.positivacao]` | string multilinha |
| `setores_queries.obter_dados_setores` SQL | `[queries.setores]` | string multilinha |

**Total**: ~17 strings SQL + 1 dict (TELEVENDAS_MAP) a serem movidos.

---

## 7. Arquivos que serão modificados na solução proposta

| Arquivo | Mudança |
|---|---|
| `queries/vendas_queries.py` | Ler SQL do `st.secrets["queries"]["vendas"]` em vez de hardcoded |
| `queries/comparativo_queries.py` | Ler SQL do `st.secrets["queries"]["comparativo"]` |
| `queries/comissao_queries.py` | Ler SQL do `st.secrets["queries"]["comissao"]` |
| `queries/estoque_queries.py` | Ler SQL do `st.secrets["queries"]["estoque"]` |
| `queries/experience_queries.py` | Ler SQL do `st.secrets["queries"]["experience"]` |
| `queries/financeiro_queries.py` | Ler SQL do `st.secrets["queries"]["financeiro"]` |
| `queries/painel_queries.py` | Ler SQL do `st.secrets["queries"]["painel"]` |
| `queries/pedidos_2_queries.py` | Ler SQL do `st.secrets["queries"]["pedidos_2"]` |
| `queries/pedidos_queries.py` | Ler SQL do `st.secrets["queries"]["pedidos"]` |
| `queries/positivacao_queries.py` | Ler SQL do `st.secrets["queries"]["positivacao"]` |
| `queries/setores_queries.py` | Ler SQL do `st.secrets["queries"]["setores"]` |
| `queries/__init__.py` | Garantir que imports públicos continuam funcionando |
| `cache_loaders.py` | **Sem mudança** — já lê do `st.secrets["database"]`; não precisa mudar pois as queries continuam sendo funções que recebem conexão |
| `pages/_cache_warm.py` | **Sem mudança** — já lê `warm_key` do secrets |
| `pages/page_*.py` | **Sem mudança** — importam queries como antes; as funções de query agora leem do secrets internamente |
| `.streamlit/secrets.toml` | **Novo conteúdo**: adicionar seções `[queries.*]` com as SQL strings e `[maps.televendas]` com o TELEVENDAS_MAP real |
| `.streamlit/secrets.example.toml` | **Novo arquivo** (commitado): estrutura completa com placeholders |
| `scripts/verify_no_inline_sql.py` | **Novo arquivo** (commitado): script que scaneia `queries/*.py` e confirma que não há SQL inline |
| `requirements.txt` | **Sem mudança** — SQLAlchemy e pyodbc continuam necessários |
| `tests/` | **Sem mudança necessária** — os testes já usam mocks de DataFrame; a mudança é interna às queries |

**Quantidade de arquivos a modificar**: 11 arquivos de query + 1 `__init__.py`.  
**Quantidade de novos arquivos**: 3 (secrets.example.toml, verify_no_inline_sql.py, update no README).  
**Arquivos sem mudança**: todos os `pages/`, `cache_loaders.py`, `_cache_warm.py`, `config.yaml`, `requirements.txt`.
