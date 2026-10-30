import streamlit as st
import pandas as pd
import unicodedata
import io
from ui_theme import apply_dashboard_theme, page_header
from cache_loaders import (
    carregar_experience_mes,
    carregar_experience_dia,
    carregar_pedidos_do_dia,
    get_active_cache_key,
    get_cache_key_diario,
    load_if_cache_ready,
    clear_loader_cache,
)

apply_dashboard_theme()

# ---------------------------------------------------------------------------
# Constantes de origem (ajuste aqui se os valores de origem_pedido vierem
# diferentes na sua base — ex.: 'TELEVENDAS' / 'EXTERNA')
# ---------------------------------------------------------------------------
ORIGEM_TELEVENDAS = "Televendas"
ORIGEM_VENDEDOR = "Vendedor"


def formata_real(valor):
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def normalizar(texto):
    if not isinstance(texto, str):
        texto = str(texto)
    nfkd = unicodedata.normalize('NFKD', texto)
    texto_sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return texto_sem_acento.upper().strip()


def _highlight_total(row):
    """Negrito na linha TOTAL GERAL, sem fundo — compatível com dark/light."""
    if row.get('Vendedor') == 'TOTAL GERAL':
        return ['font-weight: bold'] * len(row)
    return [''] * len(row)


def _calcular_contagem_por_origem(df_ped, vendedores_validos_norm=None):
    """
    Retorna DataFrame com colunas: key_vend, Qtd_Televendas, Qtd_Vendedor
    a partir do DataFrame de pedidos (1 linha por pedido).
    """
    vazio = pd.DataFrame(columns=['key_vend', 'Qtd_Televendas', 'Qtd_Vendedor'])
    if df_ped is None or df_ped.empty:
        return vazio

    df = df_ped.copy()
    if vendedores_validos_norm is not None:
        df = df[df['fantasia_vendedor'].apply(normalizar).isin(vendedores_validos_norm)]
        if df.empty:
            return vazio

    origem_norm = df['origem_pedido'].astype(str).str.strip()
    df = df.assign(
        _is_tele=(origem_norm == ORIGEM_TELEVENDAS).astype(int),
        _is_vend=(origem_norm == ORIGEM_VENDEDOR).astype(int),
    )

    contagem = (
        df.groupby('fantasia_vendedor', as_index=False)
          .agg(Qtd_Televendas=('_is_tele', 'sum'),
               Qtd_Vendedor=('_is_vend', 'sum'))
    )
    contagem['key_vend'] = contagem['fantasia_vendedor'].apply(normalizar)
    return contagem[['key_vend', 'Qtd_Televendas', 'Qtd_Vendedor']]


def renderizar_pagina_experience():
    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        page_header(
            "Acompanhamento de Pedidos",
            "Uma visão sobre valores totais dos vendedores e acompanhamento dos pedidos.",
            icon="💼",
        )
    with col_btn:
        if st.button("🔄 Atualizar Dados"):
            clear_loader_cache(carregar_experience_mes, "carregar_experience_mes")
            clear_loader_cache(carregar_experience_dia, "carregar_experience_dia")
            clear_loader_cache(carregar_pedidos_do_dia, "carregar_pedidos_do_dia")
            st.session_state["_refresh_acompanhamento"] = True
            st.rerun()

    # ------------------------------------------------------------------
    # Consumo do cache central (mantido quente pelo _cache_warm.py)
    # ------------------------------------------------------------------
    cache_key = get_active_cache_key()
    force_load = st.session_state.pop("_refresh_acompanhamento", False)
    df = load_if_cache_ready(
        carregar_experience_mes, "carregar_experience_mes", cache_key, force_load
    )
    df_dia = load_if_cache_ready(
        carregar_experience_dia, "carregar_experience_dia", cache_key, force_load
    )
    df_ped = load_if_cache_ready(
        carregar_pedidos_do_dia, "carregar_pedidos_do_dia", cache_key, force_load
    )

    if df is None or df.empty:
        st.warning(
            "Nenhum dado encontrado no cache. "
            "Aguarde o próximo ciclo de aquecimento ou clique em 'Atualizar Dados'."
        )
        return

    # ------------------------------------------------------------------
    # Controle de acesso por login
    # ------------------------------------------------------------------
    user_role = st.session_state.get("user_role", "supervisor")
    user_supervisor = (
        st.session_state.get("user_supervisor")
        or st.session_state.get("supervisor")
        or st.session_state.get("user_name")
        or st.session_state.get("username")
    )

    vendedores_sup_norm = None
    if user_role == "supervisor" and user_supervisor:
        df = df[df['SUPERVISOR'].apply(normalizar) == normalizar(user_supervisor)].copy()
        if df.empty:
            st.warning("Nenhum dado encontrado para o seu usuário.")
            return

        vendedores_sup_norm = set(df['Vendedor'].apply(normalizar).unique())

        if df_dia is not None and not df_dia.empty:
            df_dia = df_dia[df_dia['Vendedor'].apply(normalizar).isin(vendedores_sup_norm)].copy()
        if df_ped is not None and not df_ped.empty:
            df_ped = df_ped[
                df_ped['fantasia_vendedor'].apply(normalizar).isin(vendedores_sup_norm)
            ].copy()

    # ------------------------------------------------------------------
    # Filtro de fornecedor (default = Todos)
    # ------------------------------------------------------------------
    fornecedores = sorted(df['Fornecedor'].dropna().unique().tolist())
    fornecedor_opcoes = ["Todos"] + fornecedores
    fornecedor_selecionado = st.selectbox(
        "Fornecedor",
        options=fornecedor_opcoes,
        index=0,
        key="fornecedor_select",
    )

    if fornecedor_selecionado != "Todos":
        df_filtrado = df[df['Fornecedor'] == fornecedor_selecionado].copy()
        if df_dia is not None and not df_dia.empty:
            df_dia_filtrado = df_dia[df_dia['Fornecedor'] == fornecedor_selecionado].copy()
        else:
            df_dia_filtrado = pd.DataFrame()
    else:
        df_filtrado = df.copy()
        df_dia_filtrado = df_dia.copy() if df_dia is not None and not df_dia.empty else pd.DataFrame()

    # ------------------------------------------------------------------
    # Acumulado mensal por supervisor / vendedor
    # ------------------------------------------------------------------
    df_agg = (
        df_filtrado
        .groupby(['SUPERVISOR', 'Vendedor'], as_index=False)['VALOR']
        .sum()
    )

    # ------------------------------------------------------------------
    # Valores do dia por vendedor (por origem)
    # ------------------------------------------------------------------
    colunas_valor = ['Valor_Televendas', 'Valor_Vendedor', 'Valor_Total']

    if not df_dia_filtrado.empty:
        df_dia_agg = (
            df_dia_filtrado
            .groupby('Vendedor', as_index=False)[colunas_valor]
            .sum()
        )
        df_dia_agg['key_vend'] = df_dia_agg['Vendedor'].apply(normalizar)
        df_dia_agg = df_dia_agg[['key_vend'] + colunas_valor]
    else:
        df_dia_agg = pd.DataFrame(columns=['key_vend'] + colunas_valor)

    # ------------------------------------------------------------------
    # Contagem de pedidos por origem (origem correta, nível pedido)
    # ------------------------------------------------------------------
    contagem_origem = _calcular_contagem_por_origem(df_ped, vendedores_sup_norm)

    # ------------------------------------------------------------------
    # Merge final
    # ------------------------------------------------------------------
    df_agg['key_vend'] = df_agg['Vendedor'].apply(normalizar)

    df_completo = df_agg.merge(df_dia_agg, on='key_vend', how='left')
    df_completo = df_completo.merge(contagem_origem, on='key_vend', how='left')

    for c in colunas_valor + ['Qtd_Televendas', 'Qtd_Vendedor']:
        df_completo[c] = df_completo[c].fillna(0)

    df_completo = df_completo.drop(columns=['key_vend'])

    # ------------------------------------------------------------------
    # Ordena supervisores pelo total vendido no mês
    # ------------------------------------------------------------------
    supervisores_ordenados = (
        df_completo.groupby('SUPERVISOR')['VALOR']
        .sum()
        .sort_values(ascending=False)
        .index
        .tolist()
    )

    # ------------------------------------------------------------------
    # Grid 2 colunas
    # ------------------------------------------------------------------
    for i in range(0, len(supervisores_ordenados), 2):
        cols = st.columns(2)
        for j in range(2):
            idx = i + j
            if idx < len(supervisores_ordenados):
                sup = supervisores_ordenados[idx]
                df_sup = df_completo[df_completo['SUPERVISOR'] == sup]
                total_sup = df_sup['VALOR'].sum()

                with cols[j]:
                    with st.expander(
                        f"👤 {sup}  |  TOTAL: {formata_real(total_sup)}",
                        expanded=True,
                    ):
                        df_vend = df_sup[[
                            'Vendedor', 'VALOR',
                            'Qtd_Televendas', 'Valor_Televendas',
                            'Qtd_Vendedor', 'Valor_Vendedor',
                            'Valor_Total',
                        ]].copy()

                        df_vend = df_vend.sort_values('VALOR', ascending=False).reset_index(drop=True)
                        df_vend = df_vend.rename(
                            columns={
                                'VALOR': 'Valor Total (Mês)',
                                'Qtd_Televendas': 'Qtd Televendas',
                                'Valor_Televendas': 'Valor Televendas',
                                'Qtd_Vendedor': 'Qtd Vendedor',
                                'Valor_Vendedor': 'Valor Vendedor',
                                'Valor_Total': 'Valor Total (Dia)',
                            }
                        )

                        # ------- Linha de TOTAL GERAL -------
                        linha_total = pd.DataFrame([{
                            'Vendedor': 'TOTAL GERAL',
                            'Valor Total (Mês)': df_vend['Valor Total (Mês)'].sum(),
                            'Qtd Televendas':     df_vend['Qtd Televendas'].sum(),
                            'Valor Televendas':   df_vend['Valor Televendas'].sum(),
                            'Qtd Vendedor':       df_vend['Qtd Vendedor'].sum(),
                            'Valor Vendedor':     df_vend['Valor Vendedor'].sum(),
                            'Valor Total (Dia)':  df_vend['Valor Total (Dia)'].sum(),
                        }])
                        df_vend = pd.concat([df_vend, linha_total], ignore_index=True)

                        styled_df = (
                            df_vend.style
                            .format({
                                'Valor Total (Mês)': formata_real,
                                'Valor Televendas':  formata_real,
                                'Valor Vendedor':    formata_real,
                                'Valor Total (Dia)': formata_real,
                                'Qtd Televendas':    '{:.0f}',
                                'Qtd Vendedor':      '{:.0f}',
                            })
                            .apply(_highlight_total, axis=1)
                        )
                        st.dataframe(
                            styled_df,
                            hide_index=True,
                            width="stretch",
                            alt=f"Vendas e metas do supervisor {sup}, agrupadas por vendedor",
                        )

                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df_vend.to_excel(writer, sheet_name='Dados', index=False)
                        safe_sup = "".join(
                            c if c.isalnum() or c in (' ', '_', '-') else '_'
                            for c in sup
                        )
                        st.download_button(
                            label="📥 Baixar Excel",
                            data=buffer.getvalue(),
                            file_name=f"acompanhamento_{safe_sup}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"download_acompanhamento_{safe_sup}_{fornecedor_selecionado}",
                        )

    st.caption(f"Exibindo {len(df_completo)} vendedores.")


if __name__ == "__main__":
    renderizar_pagina_experience()