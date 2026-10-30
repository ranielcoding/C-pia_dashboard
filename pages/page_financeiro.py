import streamlit as st
import pandas as pd
import pyodbc
import plotly.graph_objects as go
from datetime import datetime
from ui_theme import apply_dashboard_theme, page_header
from ui_formatting import format_brl
from queries import financeiro_queries

apply_dashboard_theme()
page_header(
    "Gestão Financeira",
    "Resumo dos indicadores financeiros e detalhamento de contas.",
    icon=":material/payments:",
)

# --- CONFIGURAÇÃO ---
def get_connection():
    db = st.secrets["database"]
    return pyodbc.connect(
        f"DRIVER={{{db['driver']}}};SERVER={db['server']};"
        f"DATABASE={db['database']};Trusted_Connection={db['trusted_connection']};"
        f"TrustServerCertificate=yes;",
        timeout=60
    )

def run_query(sql_func, d_ini, d_fim):
    try:
        sql = sql_func(d_ini.strftime('%Y-%m-%d'), d_fim.strftime('%Y-%m-%d'))
        with get_connection() as conn:
            df = pd.read_sql_query(sql, conn)
            if not df.empty:
                if 'situacao_parcela' in df.columns:
                    df['situacao_parcela'] = df['situacao_parcela'].astype(str).str.strip().str.upper()
                if 'operacao' in df.columns:
                    df['operacao'] = df['operacao'].astype(str).str.strip().str.capitalize()
            return df
    except Exception as e:
        st.error(f"Erro: {e}")
        return pd.DataFrame()

def formata_real(valor):
    return format_brl(valor)

# --- LAYOUT INICIAL ---
with st.expander("📅 Filtros de Período", expanded=True):
    c1, c2 = st.columns(2)
    d_ini = c1.date_input("Início", datetime(2026, 1, 1), format="DD/MM/YYYY")
    d_fim = c2.date_input("Fim", datetime(2026, 12, 31), format="DD/MM/YYYY")

st.divider()

# --- 1. KPIS ---
df_kpi = run_query(financeiro_queries.get_kpis_financeiros, d_ini, d_fim)
if not df_kpi.empty:
    k = st.columns(5)
    labels = ["Total Pago", "Total A Pagar", "Total A Receber", "Total Recebido", "A Receber Vencido"]
    cols = ['TotalPagoCompra', 'TotalAPagar', 'TotalAReceber', 'TotalRecebidoVenda', 'TotalAReceberVencido']
    for i, label in enumerate(labels):
        valor = df_kpi[cols[i]].iloc[0] if not pd.isna(df_kpi[cols[i]].iloc[0]) else 0
        k[i].metric(label, formata_real(valor))

# --- 2. GRÁFICOS DINÂMICOS ---
st.divider()
col_g1, col_g2 = st.columns(2)

with col_g1:
    st.markdown("**📊 Valor por Operação**")
    situacao_sel = st.segmented_control(
        "Situação:",
        ["ABERTO", "PAGO"],
        default="ABERTO",
        key="rad_situacao",
    )
    df_graf = run_query(financeiro_queries.get_dados_graficos, d_ini, d_fim)
    
    if not df_graf.empty:
        df_filtered = df_graf[df_graf['situacao_parcela'] == situacao_sel]
        
        if not df_filtered.empty:
            # Agrupa por operação e soma ValorTotal
            df_op = df_filtered.groupby('operacao', as_index=False)['ValorTotal'].sum()
            categorias = df_op['operacao'].tolist()
            valores = [round(v, 2) for v in df_op['ValorTotal'].tolist()]
            
            figure = go.Figure(
                go.Bar(
                    x=categorias,
                    y=valores,
                    marker_color="#00BFFF",
                    text=[format_brl(value) for value in valores],
                    textposition="outside",
                    customdata=[format_brl(value) for value in valores],
                    hovertemplate="%{x}<br>Valor: %{customdata}<extra></extra>",
                )
            )
            figure.update_layout(
                height=350,
                margin={"t": 35, "b": 45, "l": 10, "r": 10},
                separators=",.",
                xaxis={"tickangle": 20},
                yaxis={"title": "Valor (R$)", "tickformat": ",.2f"},
            )
            st.plotly_chart(
                figure,
                width="stretch",
                alt="Valores por operação e situação, em reais",
            )
        else:
            st.info(f"Sem dados para a situação {situacao_sel}")

with col_g2:
    st.markdown("**🏆 Top 10 por Tipo**")
    op_sel = st.segmented_control(
        "Ver Ranking de:",
        ["Venda", "Compra"],
        default="Venda",
        key="rad_ranking",
    )
    df_rank = run_query(financeiro_queries.get_ranking_geral, d_ini, d_fim)
    
    if not df_rank.empty:
        df_rank_filt = df_rank[df_rank['operacao'] == op_sel].nlargest(10, 'ValorTotal')
        
        if not df_rank_filt.empty:
            # Ordena do menor para o maior para barra horizontal
            df_rank_filt = df_rank_filt.sort_values('ValorTotal', ascending=True)
            clientes = df_rank_filt['Cliente'].tolist()
            valores_rank = [round(v, 2) for v in df_rank_filt['ValorTotal'].tolist()]
            
            color = '#00CC96' if op_sel == "Venda" else '#EF553B'
            formatted_values = [format_brl(value) for value in valores_rank]
            figure = go.Figure(
                go.Bar(
                    x=valores_rank,
                    y=clientes,
                    orientation="h",
                    marker_color=color,
                    text=formatted_values,
                    textposition="outside",
                    customdata=formatted_values,
                    hovertemplate="%{y}<br>Valor: %{customdata}<extra></extra>",
                )
            )
            figure.update_layout(
                height=350,
                margin={"t": 10, "b": 10, "l": 10, "r": 35},
                separators=",.",
                xaxis={"visible": False},
                yaxis={"tickfont": {"size": 10}},
            )
            st.plotly_chart(
                figure,
                width="stretch",
                alt=f"Ranking dos dez maiores valores por tipo de operação: {op_sel}",
            )
        else:
            st.info(f"Sem registros de {op_sel} em aberto.")

# --- 3. DETALHAMENTO COM PAGINAÇÃO POR SETAS ---
st.divider()
st.subheader("🔍 Detalhamento de Títulos em Aberto")

df_detalhe = run_query(financeiro_queries.get_detalhe_contas, d_ini, d_fim)

if not df_detalhe.empty:
    df_aberto = df_detalhe[df_detalhe['situacao_parcela'] == 'ABERTO'].sort_values('vencimento_parcela')
    
    tab_venda, tab_compra = st.tabs([
        ":material/payments: Vendas a Receber",
        ":material/shopping_cart: Compras a Pagar",
    ])
    
    def render_tabela_paginada(df_input, key_prefix):
        if df_input.empty:
            st.warning("Nenhum registro encontrado para esta categoria.")
            return

        items_per_page = 15
        total_pages = (len(df_input) // items_per_page) + (1 if len(df_input) % items_per_page > 0 else 0)
        page_number = st.pagination(
            total_pages,
            default=1,
            key=f"pagination_{key_prefix}",
        )
        start_idx = (page_number - 1) * items_per_page
        df_slice = df_input.iloc[start_idx : start_idx + items_per_page]
        
        st.dataframe(
            df_slice.style.format({'valor_parcela': formata_real}), 
            width="stretch", 
            hide_index=True,
            alt=f"Títulos financeiros de {key_prefix}, página {page_number} de {total_pages}",
        )

    with tab_venda:
        render_tabela_paginada(df_aberto[df_aberto['operacao'] == 'Venda'], "venda")
    
    with tab_compra:
        render_tabela_paginada(df_aberto[df_aberto['operacao'] == 'Compra'], "compra")

# --- 4. RELATÓRIO DE RANKING FINAL (COM CORES) ---
st.divider()
st.markdown("### 📈 Ranking Consolidado: Operação e Situação")

df_comp = run_query(financeiro_queries.get_dados_graficos, d_ini, d_fim)

if not df_comp.empty:
    df_exibir = df_comp.sort_values(by="ValorTotal", ascending=False).copy()
    
    def colorir_operacao(row):
        op = str(row['operacao']).upper()
        if op == 'VENDA':
            return ['color: #28a745; font-weight: bold'] * len(row)
        elif op in ['COMPRA', 'DEVOLUCAO DE COMPRAS']:
            return ['color: #ff4b4b; font-weight: bold'] * len(row)
        return [''] * len(row)

    df_styled = (
        df_exibir.style
        .apply(colorir_operacao, axis=1)
        .format({'ValorTotal': formata_real})
    )

    st.dataframe(
        df_styled, 
        width="stretch", 
        hide_index=True,
        alt="Ranking consolidado por operação e situação, ordenado por valor",
        column_config={
            "operacao": "Operação",
            "situacao_parcela": "Situação",
            "ValorTotal": "Volume Financeiro"
        }
    )