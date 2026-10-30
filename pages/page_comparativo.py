import streamlit as st
import pandas as pd
import threading
lazy import plotly.graph_objects as go
from datetime import datetime

from cache_loaders import (
    carregar_base_comparativo,
    get_active_cache_key,
    get_active_cache_version,
    load_if_cache_ready,
    trigger_warm,
)
from queries.comparativo_queries import TELEVENDAS_MAP
from ui_theme import apply_dashboard_theme, page_header

apply_dashboard_theme()


# =============================================================================
# HEARTBEAT — reroda a página quando um novo snapshot é publicado.
# =============================================================================
@st.fragment(run_every="15s")
def _keep_cache_warm():
    version_atual = get_active_cache_version()
    chave = "_cache_version_comparativo"
    anterior = st.session_state.get(chave)

    if anterior is None:
        st.session_state[chave] = version_atual
    elif version_atual != anterior:
        st.session_state[chave] = version_atual
        st.rerun()


# =============================================================================
# HELPERS DE FORMATAÇÃO
# =============================================================================
def format_moeda(v):
    if pd.isna(v):
        return "R$ 0,00"
    return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def format_qtd(v):
    if pd.isna(v):
        return "0"
    return f"{v:,.0f}".replace(',', '.')


def colorir_setas(val):
    if val == '↑':
        return 'color: #198754; font-weight: bold;'
    if val == '↓':
        return 'color: #dc3545; font-weight: bold;'
    return ''


# =============================================================================
# SUPERVISORES EXCLUÍDOS (mesma regra das outras páginas)
# =============================================================================
SUPERVISORES_EXCLUIDOS = {
    'LIVRE METROPOLITANO', 'LIVRE NORTE', 'VALMOR SUPERVISOR',
    'SUPERVISOR INTERNO', 'SUPERVISOR ADMINISTRATIVO',
    'SUPERVISOR ZONA DA MATA LESTE', 'GLICIA MELO'
}


# =============================================================================
# HELPER DE SESSION_STATE PARA MULTISELECT
# -----------------------------------------------------------------------------
# Preserva o filtro automático do login (que pode ter sido setado como string)
# e garante que o valor final seja sempre uma lista de opções válidas.
# =============================================================================
def _normalizar_multiselect(key, opcoes):
    valor = st.session_state.get(key)

    if valor is None:
        st.session_state[key] = []
        return

    # Login pode ter setado como string (formato antigo do selectbox).
    if isinstance(valor, str):
        valor = [valor] if valor else []

    # Qualquer outro tipo (tuple, set) também vira lista.
    if not isinstance(valor, list):
        try:
            valor = list(valor)
        except TypeError:
            valor = []

    # Descarta valores que não existem mais no conjunto de opções atual.
    st.session_state[key] = [v for v in valor if v in opcoes]


# =============================================================================
# DERIVAÇÃO DE FILTROS A PARTIR DO DATAFRAME (sem queries por combinação)
# =============================================================================
def obter_lista_supervisores(df):
    if df is None or df.empty:
        return []
    sups = df['Supervisor_Real'].dropna().astype(str).unique().tolist()
    sups = [s for s in sups if s.strip() and s not in SUPERVISORES_EXCLUIDOS]
    return sorted(sups)


def obter_lista_vendedores(df, supervisores=None):
    if df is None or df.empty:
        return []
    df_f = df
    if supervisores:
        sups_upper = [s.upper() for s in supervisores]
        df_f = df_f[df_f['Supervisor_Real'].str.upper().isin(sups_upper)]
    df_ext = df_f[df_f['Equipe'] == 'EXTERNA']
    vendedores = df_ext['Vendedor_Real'].dropna().astype(str).unique().tolist()
    vendedores = [v for v in vendedores if v.strip()]
    return sorted(vendedores)


def obter_lista_televendas(df, supervisores=None, vendedores=None):
    if df is None or df.empty:
        return []
    df_f = df
    if supervisores:
        sups_upper = [s.upper() for s in supervisores]
        df_f = df_f[df_f['Supervisor_Real'].str.upper().isin(sups_upper)]
    if vendedores:
        vends_upper = [v.upper() for v in vendedores]
        df_f = df_f[df_f['Vendedor_Real'].str.upper().isin(vends_upper)]
    df_tele = df_f[df_f['Equipe'] == 'TELEVENDAS']
    nomes_validos = set(TELEVENDAS_MAP.keys())
    televendas = df_tele['Vendedor_Real'].dropna().astype(str).unique().tolist()
    televendas = [t for t in televendas if t in nomes_validos]
    return sorted(televendas)


# =============================================================================
# PÁGINA
# =============================================================================
def renderizar_pagina_comparativo():
    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        page_header(
            "Análise Comparativa (2025 vs 2026)",
            "Comparativo de vendas, quantidade e clientes entre os anos 2025 e 2026.",
            icon="⚖️",
        )
    with col_btn:
        if st.button("🔄 Atualizar Dados", width="stretch"):
            threading.Thread(
                target=trigger_warm,
                kwargs={"source": "manual"},
                daemon=True,
                name="CacheBackgroundRefresh-manual",
            ).start()
            st.toast("Aquecimento solicitado. Os gráficos atualizarão em instantes.", icon="🔥")

    cache_key = get_active_cache_key()
    df_bruto = load_if_cache_ready(
        carregar_base_comparativo,
        "carregar_base_comparativo",
        cache_key,
    )
    if df_bruto is None or df_bruto.empty:
        st.info(
            "Os dados ainda não estão disponíveis no cache. "
            "Aguarde o aquecimento automático ou clique em "
            "'Atualizar Dados' para carregar esta página."
        )
        return

    # Ativa o heartbeat (barato: só compara um inteiro a cada 15s).
    _keep_cache_warm()

    # A base do comparativo já traz Equipe, Vendedor_Real e Supervisor_Real
    # definidos em cache_loaders.carregar_base_comparativo. Mantemos apenas
    # um fallback defensivo caso a coluna 'Equipe' não esteja presente.
    if 'Equipe' not in df_bruto.columns:
        df_bruto['Equipe'] = df_bruto['origem_venda'].apply(
            lambda x: 'TELEVENDAS' if x == 'Televendas' else 'EXTERNA'
        )
    if 'Vendedor_Real' not in df_bruto.columns:
        df_bruto['Vendedor_Real'] = df_bruto['Vendedor']
    if 'Supervisor_Real' not in df_bruto.columns:
        df_bruto['Supervisor_Real'] = df_bruto['SUPERVISOR']

    # --- FILTROS INTERDEPENDENTES (5 colunas iguais, MULTISELECT) ---
    cols_filtros = st.columns(5)

    # 1. Supervisor (independente)
    #    Preserva o filtro automático do login (string → lista).
    lista_supervisores = obter_lista_supervisores(df_bruto)
    _normalizar_multiselect('filtro_sup', lista_supervisores)
    with cols_filtros[0]:
        supervisor_selecionado = st.multiselect(
            "Supervisor:",
            lista_supervisores,
            key='filtro_sup',
            placeholder="(Todos)",
        )

    # 2. Vendedor (depende do Supervisor)
    lista_vendedores = obter_lista_vendedores(df_bruto, supervisor_selecionado)
    _normalizar_multiselect('filtro_vend', lista_vendedores)
    with cols_filtros[1]:
        vendedor_selecionado = st.multiselect(
            "Vendedor:",
            lista_vendedores,
            key='filtro_vend',
            placeholder="(Todos)",
        )

    # 3. Televendas (depende de Supervisor e Vendedor)
    lista_televendas = obter_lista_televendas(
        df_bruto, supervisor_selecionado, vendedor_selecionado
    )
    _normalizar_multiselect('filtro_tele', lista_televendas)
    with cols_filtros[2]:
        televendas_selecionado = st.multiselect(
            "Televendas:",
            lista_televendas,
            key='filtro_tele',
            placeholder="(Todos)",
        )

    # Preparar dataframe parcial com filtros já aplicados (supervisor, vendedor, televendas)
    df_parcial = df_bruto.copy()
    if supervisor_selecionado:
        df_parcial = df_parcial[
            df_parcial['Supervisor_Real'].str.upper().isin(
                [s.upper() for s in supervisor_selecionado]
            )
        ]
    if vendedor_selecionado:
        df_parcial = df_parcial[
            df_parcial['Vendedor_Real'].str.upper().isin(
                [v.upper() for v in vendedor_selecionado]
            )
        ]
    if televendas_selecionado:
        df_parcial = df_parcial[
            df_parcial['cod_digitador'].str.upper().isin(
                [t.upper() for t in televendas_selecionado]
            )
        ]

    # 4. Setor (depende dos três anteriores)
    lista_setores = sorted(df_parcial['Setor'].dropna().unique().tolist())
    _normalizar_multiselect('filtro_setor', lista_setores)
    with cols_filtros[3]:
        setor_selecionado = st.multiselect(
            "Setor:",
            lista_setores,
            key='filtro_setor',
            placeholder="(Todos)",
        )

    # Atualizar df_parcial com filtro de setor
    if setor_selecionado:
        df_parcial = df_parcial[
            df_parcial['Setor'].str.upper().isin(
                [s.upper() for s in setor_selecionado]
            )
        ]

    # 5. Fornecedor (depende de todos os anteriores)
    lista_fornecedores = sorted(df_parcial['Fornecedor'].dropna().unique().tolist())
    _normalizar_multiselect('filtro_fornecedor', lista_fornecedores)
    with cols_filtros[4]:
        fornecedor_selecionado = st.multiselect(
            "Fornecedor:",
            lista_fornecedores,
            key='filtro_fornecedor',
            placeholder="(Todos)",
        )

    # Aplicar todos os filtros ao dataframe final
    df = df_bruto.copy()
    if supervisor_selecionado:
        df = df[
            df['Supervisor_Real'].str.upper().isin(
                [s.upper() for s in supervisor_selecionado]
            )
        ]
    if vendedor_selecionado:
        df = df[
            df['Vendedor_Real'].str.upper().isin(
                [v.upper() for v in vendedor_selecionado]
            )
        ]
    if televendas_selecionado:
        df = df[
            df['cod_digitador'].str.upper().isin(
                [t.upper() for t in televendas_selecionado]
            )
        ]
    if setor_selecionado:
        df = df[
            df['Setor'].str.upper().isin(
                [s.upper() for s in setor_selecionado]
            )
        ]
    if fornecedor_selecionado:
        df = df[
            df['Fornecedor'].str.upper().isin(
                [f.upper() for f in fornecedor_selecionado]
            )
        ]

    st.divider()

    # --- TABELAS (mostrando o ano completo) ---
    def preparar_tabela(df_metric, is_moeda=False):
        pivot = df_metric.unstack('Ano').fillna(0)
        if 2025 not in pivot.columns:
            pivot[2025] = 0
        if 2026 not in pivot.columns:
            pivot[2026] = 0

        pivot = pivot.reindex(range(1, 13), fill_value=0)
        pivot.index = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                       'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

        pivot['Evol'] = ["↑" if v26 > v25 else ("↓" if v26 < v25 else "")
                         for v25, v26 in zip(pivot[2025], pivot[2026])]

        if is_moeda:
            pivot['2025'] = pivot[2025].apply(format_moeda)
            pivot['2026'] = pivot[2026].apply(format_moeda)
        else:
            pivot['2025'] = pivot[2025].apply(format_qtd)
            pivot['2026'] = pivot[2026].apply(format_qtd)

        return pivot[['2025', 'Evol', '2026']]

    df_pos = df.groupby(['Ano', 'Mes'])['cod_entidade'].nunique()
    df_qtd = df.groupby(['Ano', 'Mes'])['quantidade'].sum()
    df_val = df.groupby(['Ano', 'Mes'])['valor_mercadoria'].sum()
    df_vv = df.groupby(['Ano', 'Mes'])['valor_venda'].sum()

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**CLIENTES POSITIVADOS**")
        st.dataframe(
            preparar_tabela(df_pos).style.map(colorir_setas, subset=['Evol']),
            width="stretch",
            alt="Clientes positivados por mês comparando 2025 e 2026",
        )

    with c2:
        st.markdown("**QUANTIDADE (UNS)**")
        st.dataframe(
            preparar_tabela(df_qtd).style.map(colorir_setas, subset=['Evol']),
            width="stretch",
            alt="Quantidade vendida por mês comparando 2025 e 2026",
        )

    with c3:
        st.markdown("**VALOR MERCADORIA**")
        st.dataframe(
            preparar_tabela(df_val, True).style.map(colorir_setas, subset=['Evol']),
            width="stretch",
            alt="Valor de mercadoria por mês comparando 2025 e 2026",
        )

    # --- GRÁFICOS (limitados ao mês vigente) ---
    st.markdown("### 📊 Evolução Comparativa")

    mes_atual = datetime.now().month
    meses_graf = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'][:mes_atual]

    def extrair_lista_grafico(df_agrupado, ano):
        return df_agrupado.unstack('Ano').reindex(range(1, 13)).fillna(0).get(ano, pd.Series([0] * 12)).tolist()[:mes_atual]

    g_val_25, g_val_26 = extrair_lista_grafico(df_val, 2025), extrair_lista_grafico(df_val, 2026)
    g_vv_25, g_vv_26 = extrair_lista_grafico(df_vv, 2025), extrair_lista_grafico(df_vv, 2026)
    g_qtd_25, g_qtd_26 = extrair_lista_grafico(df_qtd, 2025), extrair_lista_grafico(df_qtd, 2026)

    def plotar_comparativo(x_labels, y2025, y2026, is_moeda=False, chart_key="comp"):
        value_prefix = "R$ " if is_moeda else ""
        value_suffix = "" if is_moeda else " un."
        number_format = ",.2f" if is_moeda else ",.0f"
        figure = go.Figure()
        figure.add_bar(
            name="2025",
            x=x_labels,
            y=y2025,
            marker_color="#5A8F93",
            texttemplate=f"{value_prefix}%{{y:{number_format}}}{value_suffix}",
            textposition="outside",
            hovertemplate=(
                f"%{{x}}<br>2025: {value_prefix}%{{y:{number_format}}}{value_suffix}<extra></extra>"
            ),
        )
        figure.add_bar(
            name="2026",
            x=x_labels,
            y=y2026,
            marker_color="#C14E4E",
            texttemplate=f"{value_prefix}%{{y:{number_format}}}{value_suffix}",
            textposition="outside",
            hovertemplate=(
                f"%{{x}}<br>2026: {value_prefix}%{{y:{number_format}}}{value_suffix}<extra></extra>"
            ),
        )
        figure.add_scatter(
            name="Tendência 25",
            x=x_labels,
            y=y2025,
            mode="lines",
            line={"color": "#A3C1C3", "width": 2, "shape": "spline"},
            hovertemplate=f"%{{x}}<br>Tendência 25: {value_prefix}%{{y:{number_format}}}{value_suffix}<extra></extra>",
        )
        figure.add_scatter(
            name="Tendência 26",
            x=x_labels,
            y=y2026,
            mode="lines",
            line={"color": "#E1A4A4", "width": 2, "shape": "spline"},
            hovertemplate=f"%{{x}}<br>Tendência 26: {value_prefix}%{{y:{number_format}}}{value_suffix}<extra></extra>",
        )
        figure.update_layout(
            barmode="group",
            height=400,
            margin={"t": 30, "b": 70, "l": 10, "r": 10},
            separators=",.",
            legend={"orientation": "h", "y": -0.22},
            yaxis={
                "title": "Valor (R$)" if is_moeda else "Quantidade (un.)",
                "tickformat": number_format,
            },
        )
        st.plotly_chart(
            figure,
            width="stretch",
            alt=f"Comparativo mensal entre 2025 e 2026 de {chart_key}",
        )

    t1, t2, t3 = st.tabs(["EV. VALOR MERCADORIA", "EV. VALOR VENDA (NF)", "EV. QUANTIDADE (UNS)"])
    with t1:
        plotar_comparativo(meses_graf, g_val_25, g_val_26, is_moeda=True, chart_key="comp_valor")
    with t2:
        plotar_comparativo(meses_graf, g_vv_25, g_vv_26, is_moeda=True, chart_key="comp_venda")
    with t3:
        plotar_comparativo(meses_graf, g_qtd_25, g_qtd_26, is_moeda=False, chart_key="comp_qtd")


if __name__ == "__main__":
    renderizar_pagina_comparativo()