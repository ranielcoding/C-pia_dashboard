import io

import streamlit as st
import pandas as pd
from ui_theme import apply_dashboard_theme, page_header
from cache_loaders import (
    carregar_pedidos_do_dia,
    carregar_detalhamento_pedidos_do_dia,
    get_active_cache_key,
    get_cache_key_diario,
    load_if_cache_ready,
    clear_loader_cache,
)

apply_dashboard_theme()


def formata_real(valor):
    if pd.isna(valor):
        valor = 0
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def aplicar_filtro_supervisor_pedidos(df, effective_access):
    role = str((effective_access or {}).get("role", "")).lower()
    supervisor = (effective_access or {}).get("default_filters", {}).get("supervisor")
    if role != "supervisor" or not supervisor:
        return df

    supervisor_column = next(
        (column for column in df.columns if column.upper() == "SUPERVISOR"),
        None,
    )
    if supervisor_column is None:
        raise ValueError(
            "A consulta de pedidos precisa retornar a coluna SUPERVISOR "
            "para aplicar o escopo do supervisor."
        )
    return df[
        df[supervisor_column].fillna("").astype(str).str.upper()
        == str(supervisor).upper()
    ].copy()


# ---------------------------------------------------------------------------
# Modal de detalhamento do pedido (tela cheia)
# ---------------------------------------------------------------------------
@st.dialog(
    "Detalhamento do Pedido",
    width="large",
    position="right",
    icon=":material/receipt_long:",
)
def mostrar_detalhamento_pedido(codigo_pedido, df_detalhes):
    if df_detalhes is None or df_detalhes.empty:
        st.warning("Detalhamento indisponível no momento.")
        return

    df_ped = df_detalhes[
        df_detalhes["codigo_pedido"].astype(str) == str(codigo_pedido)
    ].copy()

    if df_ped.empty:
        st.info(f"Nenhum item encontrado para o pedido {codigo_pedido}.")
        return

    col_titulo, col_export = st.columns([3, 1])

    with col_titulo:
        st.markdown(f"### Pedido: `{codigo_pedido}`")

    colunas = [
        "codigo_produto",
        "produto",
        "situacao_item",
        "motivo_falta",
        "quantidade_pedida",
        "quantidade_atendida",
        "quantidade_cortada",
        "valor_mercadoria_item",
        "valor_titulo_item",
        "percentual_desconto_unitario",
    ]
    colunas = [c for c in colunas if c in df_ped.columns]
    df_show = df_ped[colunas].rename(columns={
        "codigo_produto": "Cód. Produto",
        "produto": "Produto",
        "situacao_item": "Situação",
        "motivo_falta": "Motivo Falta",
        "quantidade_pedida": "Qtd. Pedida",
        "quantidade_atendida": "Qtd. Atendida",
        "quantidade_cortada": "Qtd. Cortada",
        "valor_mercadoria_item": "Vlr. Mercadoria",
        "valor_titulo_item": "Vlr. Título",
        "percentual_desconto_unitario": "% Desc. Unit.",
    })

    # ----- Excel: mantém valores numéricos originais -----
    with col_export:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_show.to_excel(
                writer, index=False, sheet_name=f"Pedido_{codigo_pedido}"[:31]
            )

        st.download_button(
            label="📥 Baixar Excel",
            data=buffer.getvalue(),
            file_name=f"detalhamento_pedido_{codigo_pedido}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key=f"download_detalhe_{codigo_pedido}",
        )

    # ----- Cópia só para exibição (Opção 2: apply + TextColumn) -----
    df_display = df_show.copy()

    for col in ["Vlr. Mercadoria", "Vlr. Título"]:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(formata_real)

    if "% Desc. Unit." in df_display.columns:
        df_display["% Desc. Unit."] = df_display["% Desc. Unit."].apply(
            lambda v: "-" if pd.isna(v) else f"{v:.2f}%"
        )

    st.dataframe(
        df_display,
        hide_index=True,
        width="stretch",
        lazy=True,
        alt=f"Itens do pedido {codigo_pedido}, com quantidades, valores e situação",
        column_config={
            "Vlr. Mercadoria": st.column_config.TextColumn("Vlr. Mercadoria"),
            "Vlr. Título":     st.column_config.TextColumn("Vlr. Título"),
            "% Desc. Unit.":   st.column_config.TextColumn("% Desc. Unit."),
        },
    )
    st.caption(f"Exibindo {len(df_show)} item(ns) do pedido {codigo_pedido}.")


def renderizar_pagina_pedidos():
    # ------------------------------------------------------------------
    # Cabeçalho + botão Atualizar
    # ------------------------------------------------------------------
    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        page_header(
            "Acompanhamento de Pedidos",
            "Listagem em tempo real dos pedidos digitados no dia. " \
            "*Pedidos faturados somam impostos e encargos no total, enquanto pedidos pendentes não incluem esses valores.*",
            icon=":material/assignment:",
        )
    with col_btn:
        if st.button("🔄 Atualizar Dados"):
            clear_loader_cache(carregar_pedidos_do_dia, "carregar_pedidos_do_dia")
            clear_loader_cache(
                carregar_detalhamento_pedidos_do_dia,
                "carregar_detalhamento_pedidos_do_dia",
            )
            st.session_state["_refresh_pedidos"] = True
            st.rerun()

    # ------------------------------------------------------------------
    # Cache central (mantido quente pelo _cache_warm.py)
    # ------------------------------------------------------------------
    cache_key = get_active_cache_key()
    force_load = st.session_state.pop("_refresh_pedidos", False)

    df = load_if_cache_ready(
        carregar_pedidos_do_dia,
        "carregar_pedidos_do_dia",
        cache_key,
        force_load,
    )

    df_detalhes = load_if_cache_ready(
        carregar_detalhamento_pedidos_do_dia,
        "carregar_detalhamento_pedidos_do_dia",
        cache_key,
        force_load,
    )

    if df is None or df.empty:
        st.warning(
            "Nenhum pedido encontrado no cache. "
            "Aguarde o próximo ciclo de aquecimento ou clique em 'Atualizar Dados'."
        )
        return

    try:
        df = aplicar_filtro_supervisor_pedidos(
            df, st.session_state.get("effective_access")
        )
    except ValueError as error:
        st.error(str(error))
        return
    if df.empty:
        st.info("Nenhum pedido encontrado para o supervisor associado ao seu login.")
        return

    # ------------------------------------------------------------------
    # Filtros
    # ------------------------------------------------------------------
    col1, col2, col3 = st.columns(3)

    with col1:
        vendedores = sorted(df['fantasia_vendedor'].dropna().astype(str).unique().tolist())
        vendedor_sel = st.selectbox(
            "Vendedor",
            options=["Todos"] + vendedores,
            index=0,
            key="filtro_vendedor_ped",
        )

    with col2:
        situacoes = sorted(df['situacao'].dropna().astype(str).unique().tolist())
        situacao_sel = st.selectbox(
            "Situação",
            options=["Todos"] + situacoes,
            index=0,
            key="filtro_situacao_ped",
        )

    with col3:
        operacoes = sorted(df['operacao'].dropna().astype(str).unique().tolist())
        operacao_sel = st.selectbox(
            "Operação",
            options=["Todos"] + operacoes,
            index=0,
            key="filtro_operacao_ped",
        )

    # Aplica filtros
    df_filtrado = df.copy()
    if vendedor_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado['fantasia_vendedor'].astype(str) == vendedor_sel]
    if situacao_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado['situacao'].astype(str) == situacao_sel]
    if operacao_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado['operacao'].astype(str) == operacao_sel]

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------
    total_pedidos = len(df_filtrado)
    total_pedido_col = pd.to_numeric(df_filtrado['total_pedido'], errors='coerce').fillna(0)
    valor_total = float(total_pedido_col.sum())

    k1, k2, _ = st.columns([1, 1, 2])
    with k1:
        st.metric(
            "Nº Total de Pedidos",
            f"{total_pedidos}",
            icon=":material/receipt_long:",
        )
    with k2:
        st.metric(
            "Valor Total de Pedidos",
            formata_real(valor_total),
            icon=":material/payments:",
        )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Listagem
    # ------------------------------------------------------------------
    if df_filtrado.empty:
        st.info("Nenhum pedido encontrado com os filtros selecionados.")
        return

    colunas_exibir = [
        'codigo_pedido',
        'fantasia_vendedor',
        'codigo_cliente',
        'fantasia_cliente',
        'origem_pedido',
        'total_pedido',
        'operacao',
        'situacao',
        'pendencia',
        'codigo_condicao',
        'SUPERVISOR',
    ]

    # Garante que todas as colunas existem, evitando KeyError
    colunas_exibir = [c for c in colunas_exibir if c in df_filtrado.columns]
    df_show = df_filtrado[colunas_exibir].copy()

    rename_map = {
        'codigo_pedido': 'Cód. Pedido',
        'fantasia_vendedor': 'Vendedor',
        'codigo_cliente': 'Cód. Cliente',
        'fantasia_cliente': 'Cliente',
        'origem_pedido': 'Origem',
        'total_pedido': 'Total Pedido',
        'operacao': 'Operação',
        'situacao': 'Situação',
        'pendencia': 'Pendência',
        'codigo_condicao': 'Cód. Condição',
        'SUPERVISOR': 'Supervisor',
    }
    df_show = df_show.rename(columns=rename_map)

    # Ordena por maior valor para leitura rápida
    if 'Total Pedido' in df_show.columns:
        df_show = df_show.sort_values('Total Pedido', ascending=False).reset_index(drop=True)

    st.caption(
        "💡 Clique em qualquer linha da tabela para abrir o detalhamento do pedido."
    )

    df_show["Total Pedido"] = df_show["Total Pedido"].apply(formata_real)

    event = st.dataframe(
        df_show,
        column_config={
            "Total Pedido": st.column_config.TextColumn("Total Pedido"),
        },
            hide_index=True,
            width="stretch",
            alt="Pedidos filtrados e ordenados por valor; selecione uma linha para ver os itens",
            on_select="rerun",
            selection_mode="single-row",
            key="pedidos_table",
        )

    st.caption(f"Exibindo {len(df_show)} pedidos.")

    # ------------------------------------------------------------------
    # Trata a seleção de linha — abre o modal de detalhamento
    # ------------------------------------------------------------------
    linhas_selecionadas = (
        event.selection.get("rows", []) if hasattr(event, "selection") else []
    )

    if linhas_selecionadas:
        idx = linhas_selecionadas[0]
        if 0 <= idx < len(df_show):
            codigo_pedido = str(df_show.iloc[idx]["Cód. Pedido"])
            ultimo_aberto = st.session_state.get("_pedido_detalhe_aberto")
            if ultimo_aberto != codigo_pedido:
                st.session_state["_pedido_detalhe_aberto"] = codigo_pedido
                mostrar_detalhamento_pedido(codigo_pedido, df_detalhes)


if __name__ == "__main__":
    renderizar_pagina_pedidos()