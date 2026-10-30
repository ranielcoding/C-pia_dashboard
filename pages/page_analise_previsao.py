import io
import pandas as pd
# Lazy imports PEP 810 para otimização de cold-start
lazy import plotly.express as px
lazy import plotly.graph_objects as go
import streamlit as st
from streamlit_echarts import st_echarts, JsCode

from cache_loaders import (
    carregar_base_unica,
    carregar_estoque,
    carregar_setores,
    get_active_cache_key,
    get_scoped_cache_key,
    load_if_cache_ready,
)
from data_quality import prepare_dataframe
from queries.comparativo_queries import TELEVENDAS_MAP
from ui_formatting import format_brl, format_pt_number
from ui_theme import apply_dashboard_theme, page_header


SUPERVISORES_EXCLUIDOS = {
    "LIVRE METROPOLITANO",
    "LIVRE NORTE",
    "VALMOR SUPERVISOR",
    "SUPERVISOR INTERNO",
    "SUPERVISOR ADMINISTRATIVO",
    "SUPERVISOR ZONA DA MATA LESTE",
    "GLICIA MELO",
}


def _normalizar_multiselect(key, opcoes):
    valor = st.session_state.get(key)
    if valor is None:
        st.session_state[key] = []
        return
    if isinstance(valor, str):
        valor = [valor] if valor else []
    elif not isinstance(valor, list):
        try:
            valor = list(valor)
        except TypeError:
            valor = []
    # Normalização case-insensitive para garantir compatibilidade com login automático
    mapa_opcoes = {str(o).upper(): o for o in opcoes}
    st.session_state[key] = [
        mapa_opcoes[str(value).upper()]
        for value in valor
        if str(value).upper() in mapa_opcoes
    ]


def _filtrar_selecao(df, column, selections):
    if selections and column in df.columns:
        selected_values = {value.upper() for value in selections}
        return df[df[column].fillna("").astype(str).str.upper().isin(selected_values)]
    return df


def _obter_metadados_clientes(df):
    required = {"cod_entidade", "SUPERVISOR", "Vendedor", "Setor", "FANTASIA"}
    if df is None or df.empty or not required.issubset(df.columns):
        return pd.DataFrame(
            columns=["cod_entidade", "SUPERVISOR", "VENDEDOR", "SETOR", "FANTASIA"]
        )

    metadata = df[
        ["cod_entidade", "SUPERVISOR", "Vendedor", "Setor", "FANTASIA"]
    ].copy()
    metadata["cod_entidade"] = (
        metadata["cod_entidade"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    )
    metadata = metadata.dropna(subset=["cod_entidade"]).drop_duplicates(
        "cod_entidade",
        keep="first",
    )
    return metadata.rename(
        columns={"Vendedor": "VENDEDOR", "Setor": "SETOR"}
    )


def carregar_df_analise():
    base_cache = load_if_cache_ready(
        carregar_base_unica,
        "carregar_base_unica",
        get_active_cache_key(),
    )
    if not isinstance(base_cache, pd.DataFrame) or base_cache.empty:
        return None

    numeric = [
        column for column in ["valor_mercadoria", "quantidade"] if column in base_cache
    ]
    return prepare_dataframe(
        base_cache,
        required_columns=["data", "valor_mercadoria"],
        numeric_columns=numeric,
        date_columns=["data"],
    )


@st.cache_data(show_spinner=False, ttl=3600, refresh_mode="background")
def _prever_quantis(df, periods):
    import holidays
    from modules.statistical_engines import forecast_sales_quantiles

    years = pd.to_datetime(df["data"], errors="coerce").dropna().dt.year.unique()
    holiday_dates = holidays.country_holidays(
        "BR",
        subdiv="MG",
        years=sorted(int(year) for year in years),
    )
    return forecast_sales_quantiles(
        df,
        periods=periods,
        holiday_dates=holiday_dates.keys(),
    )


@st.cache_data(show_spinner=False, ttl=3600, refresh_mode="background")
def _segmentar_clientes(df, as_of):
    from modules.statistical_engines import segment_customers_rfm

    return segment_customers_rfm(
        df,
        customer_col="cod_entidade",
        date_col="data",
        invoice_col="NF",
        value_col="valor_mercadoria",
        product_col="id_produto",
        as_of=as_of,
    )


@st.cache_data(show_spinner=False, ttl=3600, refresh_mode="background")
def _simular_risco_lotes(lots, sales, as_of):
    from modules.statistical_engines import simulate_lot_expiry_risk

    return simulate_lot_expiry_risk(
        lots,
        sales,
        lot_id_col="Lote",
        product_col="Codigo Produto",
        lot_quantity_col="Estoque Lote",
        expiry_col="Validade",
        sales_date_col="data",
        sales_quantity_col="quantidade",
        as_of=as_of,
    )


def _vendas_sem_devolucoes(df):
    if "operacao" not in df.columns:
        return df
    return df[df["operacao"].astype(str).str.casefold() == "venda"].copy()


@st.fragment(parallel=True)
def _renderizar_previsao(df):
    horizonte = st.segmented_control(
        "Horizonte da previsão",
        options=[30, 60],
        default=30,
        format_func=lambda value: f"{value} dias",
        key="horizonte_previsao_quantile",
    )
    today = pd.Timestamp.today().normalize()
    history = df.loc[
        pd.to_datetime(df["data"], errors="coerce").dt.normalize() <= today,
        ["data", "valor_mercadoria"],
    ].copy()
    if history.empty:
        st.info("Não há histórico disponível até a data atual para estimar o fechamento do mês.")
        return

    last_observed = pd.to_datetime(history["data"], errors="coerce").max().normalize()
    month_end = today + pd.offsets.MonthEnd(0)
    close_horizon = max(int((month_end - last_observed).days), 0)
    forecast = _prever_quantis(
        history,
        max(int(horizonte or 30), close_horizon),
    )
    if forecast.empty:
        st.info("Não há dados suficientes para a previsão selecionada.")
        return

    from modules.statistical_engines import estimate_month_close

    close_estimate = estimate_month_close(history, forecast, as_of=today)
    
    # Escapa o '$' para evitar que o Streamlit interprete como LaTeX/Markdown no delta
    p10_formatado = format_brl(close_estimate['p10']).replace("$", r"\$")
    p90_formatado = format_brl(close_estimate['p90']).replace("$", r"\$")
    delta_p10_p90 = f"P10: {p10_formatado} | P90: {p90_formatado}"

    st.metric(
        "Fechamento estimado do mês (P50)",
        format_brl(close_estimate["p50"]),
        delta_p10_p90,
        # Dica: como isso é uma faixa de valores e não uma "alta/baixa", 
        # você pode querer usar delta_color="off" para tirar a setinha verde/vermelha
    )
    st.caption(
        "Estimativa baseada no faturamento histórico já realizado no mês e "
        "na projeção diária dos quantis P10, P50 e P90 até o fim do mês."
    )


    daily_sales = history.assign(
        data=pd.to_datetime(history["data"], errors="coerce").dt.normalize()
    ).groupby("data", as_index=False)["valor_mercadoria"].sum()
    daily_sales = daily_sales.tail(180)

    # Preparação das séries temporais para o ECharts
    hist_dates = [pd.to_datetime(d).strftime("%d/%m/%Y") for d in daily_sales["data"]]
    hist_vals = [round(float(v), 2) for v in daily_sales["valor_mercadoria"]]

    fore_dates = [pd.to_datetime(d).strftime("%d/%m/%Y") for d in forecast["data"]]
    fore_p10 = [round(float(v), 2) for v in forecast["p10"]]
    fore_p50 = [round(float(v), 2) for v in forecast["p50"]]
    fore_p90 = [round(float(v), 2) for v in forecast["p90"]]
    fore_diff = [round(float(p90 - p10), 2) for p10, p90 in zip(forecast["p10"], forecast["p90"])]

    # Combina datas sem duplicidade mantendo a ordenação cronológica
    all_dates = list(dict.fromkeys(hist_dates + fore_dates))
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    series_hist = [None] * len(all_dates)
    for d, val in zip(hist_dates, hist_vals):
        series_hist[date_to_idx[d]] = val

    series_p10 = [None] * len(all_dates)
    series_diff = [None] * len(all_dates)
    series_p50 = [None] * len(all_dates)
    for d, p10, diff, p50 in zip(fore_dates, fore_p10, fore_diff, fore_p50):
        idx = date_to_idx[d]
        series_p10[idx] = p10
        series_diff[idx] = diff
        series_p50[idx] = p50

    st.markdown(f"**Previsão de faturamento para {horizonte} dias**")
    options_forecast = {
        "tooltip": {
            "trigger": "axis",
            "formatter": JsCode(
                "function(params){"
                "var res = params[0].name + '<br/>';"
                "params.forEach(function(p){"
                "if (p.value !== null && p.value !== undefined && p.seriesName !== 'Base P10') {"
                "res += p.marker + ' ' + p.seriesName + ': ' + p.value.toLocaleString('pt-BR', {style:'currency', currency:'BRL'}) + '<br/>';"
                "}"
                "});"
                "return res;"
                "}"
            ),
        },
        "legend": {"data": ["Histórico", "P50 esperado", "Faixa P10–P90"], "top": "2%"},
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "top": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": all_dates, "axisLabel": {"rotate": 30}},
        "yAxis": {
            "type": "value",
            "name": "R$",
            "axisLabel": {
                "formatter": JsCode(
                    "function(value){return value.toLocaleString('pt-BR', {style:'currency', currency:'BRL'});}"
                )
            },
        },
        "series": [
            {
                "name": "Histórico",
                "type": "line",
                "data": series_hist,
                "lineStyle": {"color": "#8b8b8b", "width": 1.5},
                "itemStyle": {"color": "#8b8b8b"},
                "showSymbol": False,
            },
            {
                "name": "Base P10",
                "type": "line",
                "data": series_p10,
                "lineStyle": {"opacity": 0},
                "itemStyle": {"opacity": 0},
                "stack": "confidence-band",
                "symbol": "none",
            },
            {
                "name": "Faixa P10–P90",
                "type": "line",
                "data": series_diff,
                "lineStyle": {"opacity": 0},
                "areaStyle": {"color": "rgba(49, 87, 132, 0.25)"},
                "stack": "confidence-band",
                "symbol": "none",
            },
            {
                "name": "P50 esperado",
                "type": "line",
                "data": series_p50,
                "lineStyle": {"color": "#315784", "width": 3},
                "itemStyle": {"color": "#315784"},
                "showSymbol": False,
            },
        ],
    }
    st_echarts(options=options_forecast, height="450px", key=f"chart_previsao_{horizonte}")

    # Remove dias zerados (mantém apenas previsão > R$ 0,00)
    forecast_uteis = forecast[
        (forecast["p50"] > 0) | (forecast["p10"] > 0) | (forecast["p90"] > 0)
    ].copy()

    forecast_display = forecast_uteis.rename(
        columns={
            "data": "Data",
            "p10": "Conservador (P10)",
            "p50": "Esperado (P50)",
            "p90": "Otimista (P90)",
        }
    ).copy()
    for column in ["Conservador (P10)", "Esperado (P50)", "Otimista (P90)"]:
        forecast_display[column] = forecast_display[column].map(format_brl)
    forecast_display["Data"] = forecast_display["Data"].dt.strftime("%d/%m/%Y")
    st.dataframe(
        forecast_display,
        width="stretch",
        lazy=True,
        hide_index=True,
        alt="Valores diários previstos nos quantis P10, P50 e P90 (dias úteis)",
    )

    # Botão de download Excel
    buffer_previsao = io.BytesIO()
    with pd.ExcelWriter(buffer_previsao, engine="openpyxl") as writer:
        forecast_export = forecast_uteis.copy()
        forecast_export["data"] = forecast_export["data"].dt.strftime("%d/%m/%Y")
        forecast_export = forecast_export.rename(
            columns={
                "data": "Data",
                "p10": "Conservador (P10)",
                "p50": "Esperado (P50)",
                "p90": "Otimista (P90)",
            }
        )
        forecast_export.to_excel(writer, sheet_name="Previsao_Faturamento", index=False)

    st.download_button(
        label="📥 Baixar Previsão em Excel",
        data=buffer_previsao.getvalue(),
        file_name=f"previsao_faturamento_{horizonte}dias.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"download_previsao_{horizonte}dias",
    )


@st.fragment(parallel=True)
def _renderizar_risco_estoque(sales, as_of):
    lots = load_if_cache_ready(
        carregar_estoque,
        "carregar_estoque",
        get_scoped_cache_key("estoque"),
    )
    if lots is None or lots.empty:
        st.info(
            "Os dados de lotes ainda não estão no cache. Aguarde o aquecimento "
            "da página de estoque para consultar o risco."
        )
        return
    required = {"Lote", "Codigo Produto", "Validade", "Estoque Lote"}
    if missing := required.difference(lots.columns):
        st.error(f"A consulta de estoque não trouxe as colunas necessárias: {sorted(missing)}")
        return

    clean_sales = _vendas_sem_devolucoes(sales)
    if not {"id_produto", "data", "quantidade"}.issubset(clean_sales.columns):
        st.warning("A base de vendas não contém produto, data e quantidade para simular consumo.")
        return
    lot_columns = ["Lote", "Codigo Produto", "Validade", "Estoque Lote"]
    if "Descrição" in lots.columns:
        lot_columns.append("Descrição")
    lots_for_risk = lots[lot_columns].copy()
    lots_for_risk["Codigo Produto"] = lots_for_risk["Codigo Produto"].astype(str)
    sales_for_risk = clean_sales[["id_produto", "data", "quantidade"]].rename(
        columns={"id_produto": "Codigo Produto"}
    )
    sales_for_risk["Codigo Produto"] = sales_for_risk["Codigo Produto"].astype(str)
    risk = _simular_risco_lotes(lots_for_risk, sales_for_risk, as_of)
    if risk.empty:
        st.info("Não há lotes válidos para simular.")
        return
    if "Descrição" in lots_for_risk.columns:
        product_labels = lots_for_risk[
            ["Lote", "Descrição"]
        ].drop_duplicates("Lote")
        risk = risk.merge(
            product_labels,
            left_on="lot_id",
            right_on="Lote",
            how="left",
        ).drop(columns="Lote")
        risk = risk.rename(columns={"Descrição": "product_name"})
    else:
        risk["product_name"] = risk["product_id"].astype(str)

    risk = risk.copy()
    risk["days_to_expiry"] = (
        pd.to_datetime(risk["expiry_date"]).dt.normalize() - pd.Timestamp(as_of).normalize()
    ).dt.days.clip(lower=0)
    critical = risk[risk["probability_expiry_with_stock"] >= 0.7]
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Lotes com risco alto (≥ 70%)", format_pt_number(len(critical)))
    metric_col2.metric(
        "Unidades esperadas em sobra",
        format_pt_number(risk["expected_remaining_quantity"].sum()),
    )
    metric_col3.metric("Total de lotes avaliados", format_pt_number(len(risk)))
    if (risk["expected_loss_value"] > 0).any():
        st.metric(
            "Valor estimado em risco",
            format_brl(risk["expected_loss_value"].sum()),
        )
    risk_chart_data = risk.nlargest(30, "expected_remaining_quantity").copy()
    risk_chart_data["probability_percent"] = (
        risk_chart_data["probability_expiry_with_stock"] * 100
    )
    risk_figure = px.scatter(
        risk_chart_data,
        x="days_to_expiry",
        y="expected_remaining_quantity",
        size="probability_percent",
        color="urgency",
        hover_name="lot_id",
        hover_data={
            "product_name": True,
            "product_id": False,
            "days_to_expiry": True,
            "expected_remaining_quantity": ":,.0f",
            "probability_percent": ":.1f",
        },
        labels={
            "days_to_expiry": "Dias até o vencimento",
            "expected_remaining_quantity": "Unidades esperadas em sobra",
            "urgency": "Prioridade",
            "product_name": "Produto",
            "probability_percent": "Risco de sobra (%)",
        },
        title="Lotes prioritários: proximidade do vencimento e sobra projetada",
    )
    risk_figure.update_layout(separators=",.")
    risk_figure.update_yaxes(tickformat=",.0f")
    st.plotly_chart(
        risk_figure,
        width="stretch",
        alt="Lotes com maior sobra projetada, comparados por dias até o vencimento e risco",
    )
    risk_display = risk.sort_values(
        ["probability_expiry_with_stock", "days_to_expiry", "expected_remaining_quantity"],
        ascending=[False, True, False],
    ).rename(
        columns={
            "lot_id": "Lote",
            "product_id": "Código do produto",
            "product_name": "Produto",
            "expiry_date": "Validade",
            "days_to_expiry": "Dias até vencer",
            "probability_expiry_with_stock": "Risco de sobra",
            "expected_remaining_quantity": "Sobra esperada (un.)",
            "expected_loss_value": "Valor estimado em risco",
            "urgency": "Prioridade",
        }
    )
    risk_display["Validade"] = pd.to_datetime(risk_display["Validade"]).dt.strftime(
        "%d/%m/%Y"
    )
    risk_display["Risco de sobra"] = risk_display["Risco de sobra"].map(
        lambda value: f"{format_pt_number(value * 100, decimals=1)}%"
    )
    risk_display["Sobra esperada (un.)"] = risk_display[
        "Sobra esperada (un.)"
    ].map(format_pt_number)
    risk_display["Valor estimado em risco"] = risk_display[
        "Valor estimado em risco"
    ].map(format_brl)
    st.dataframe(
        risk_display[
            [
                "Lote",
                "Produto",
                "Código do produto",
                "Validade",
                "Dias até vencer",
                "Risco de sobra",
                "Sobra esperada (un.)",
                "Valor estimado em risco",
                "Prioridade",
            ]
        ],
        width="stretch",
        lazy=True,
        hide_index=True,
        alt="Risco Monte Carlo estimado para cada lote",
    )


@st.fragment(parallel=True)
def _renderizar_segmentacao(transactions, as_of, customer_metadata):
    if not {
        "cod_entidade",
        "data",
        "NF",
        "valor_mercadoria",
        "id_produto",
    }.issubset(transactions.columns):
        st.info("A consulta de vendas não contém as colunas necessárias para segmentar clientes.")
        return
    sales = _vendas_sem_devolucoes(transactions)
    customers = _segmentar_clientes(
        sales[
            ["cod_entidade", "data", "NF", "valor_mercadoria", "id_produto"]
        ],
        as_of,
    )
    if customers.empty:
        st.info("Não há transações de venda suficientes para calcular os perfis RFM.")
        return

    segment_summary = customers.groupby("segment", as_index=False).agg(
        clientes=("customer_id", "count"),
        faturamento=("monetary", "sum"),
        recencia_mediana=("recency_days", "median"),
        compras_medias=("frequency", "mean"),
        risco_medio=("churn_probability", "mean"),
    )
    profiles = ["Todos", *sorted(customers["segment"].dropna().unique())]
    selected_profile = st.selectbox(
        "Perfil do cliente",
        profiles,
        key="customer_segment_profile",
    )
    visible_customers = (
        customers
        if selected_profile == "Todos"
        else customers[customers["segment"] == selected_profile]
    )
    high_risk = visible_customers[visible_customers["churn_probability"] >= 0.7]
    metric_columns = st.columns(3)
    metric_columns[0].metric(
        f"Clientes em risco alto ({selected_profile.lower()})",
        format_pt_number(len(high_risk)),
    )
    metric_columns[1].metric(
        "Faturamento do perfil",
        format_brl(visible_customers["monetary"].sum()),
    )
    metric_columns[2].metric(
        "Recência mediana",
        f"{format_pt_number(visible_customers['recency_days'].median())} dias",
    )
    visible_summary = segment_summary
    if selected_profile != "Todos":
        visible_summary = visible_summary[
            visible_summary["segment"] == selected_profile
        ]
    summary_sorted = visible_summary.sort_values("faturamento", ascending=False)
    x_segments = [str(s) for s in summary_sorted["segment"]]
    y_fat = [round(float(v), 2) for v in summary_sorted["faturamento"]]
    y_cli = [int(v) for v in summary_sorted["clientes"]]

    st.markdown("**Faturamento e quantidade de clientes por perfil**")
    options_profile = {
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "formatter": JsCode(
                "function(params){"
                "var res = params[0].name + '<br/>';"
                "params.forEach(function(p){"
                "if (p.seriesName === 'Faturamento') {"
                "res += p.marker + ' ' + p.seriesName + ': ' + p.value.toLocaleString('pt-BR', {style:'currency', currency:'BRL'}) + '<br/>';"
                "} else {"
                "res += p.marker + ' ' + p.seriesName + ': ' + p.value.toLocaleString('pt-BR') + ' clientes<br/>';"
                "}"
                "});"
                "return res;"
                "}"
            ),
        },
        "legend": {"data": ["Faturamento", "Clientes"], "top": "2%"},
        "grid": {"left": "3%", "right": "5%", "bottom": "10%", "top": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": x_segments, "axisLabel": {"rotate": 20}},
        "yAxis": [
            {
                "type": "value",
                "name": "Faturamento (R$)",
                "axisLabel": {
                    "formatter": JsCode(
                        "function(value){return value.toLocaleString('pt-BR', {style:'currency', currency:'BRL'});}"
                    )
                },
            },
            {
                "type": "value",
                "name": "Clientes",
                "position": "right",
                "splitLine": {"show": False},
                "axisLabel": {
                    "formatter": JsCode("function(value){return value.toLocaleString('pt-BR');}")
                },
            },
        ],
        "series": [
            {
                "name": "Faturamento",
                "type": "bar",
                "data": y_fat,
                "itemStyle": {"color": "#315784"},
            },
            {
                "name": "Clientes",
                "type": "line",
                "yAxisIndex": 1,
                "data": y_cli,
                "lineStyle": {"color": "#E07A2D", "width": 3},
                "itemStyle": {"color": "#E07A2D"},
                "symbol": "circle",
                "symbolSize": 8,
                "label": {"show": True, "position": "top", "formatter": "{c} clientes"},
            },
        ],
    }
    st_echarts(options=options_profile, height="450px", key=f"chart_perfil_{selected_profile}")
    customer_display = visible_customers.sort_values(
        ["churn_probability", "monetary"], ascending=[False, False]
    ).rename(
        columns={
            "customer_id": "Cliente",
            "recency_days": "Dias desde a última compra",
            "frequency": "Notas fiscais (12 meses)",
            "monetary": "Faturamento líquido",
            "product_diversity": "Produtos distintos",
            "segment": "Perfil",
            "churn_probability": "Risco estimado",
            "churn_label": "Classificação",
            "churn_drivers": "Sinais de atenção",
            "risk_method": "Base do risco",
        }
    ).copy()

    customer_display["Cliente"] = (
        customer_display["Cliente"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    customer_metadata = customer_metadata.copy()
    customer_metadata["cod_entidade"] = (
        customer_metadata["cod_entidade"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    customer_display = customer_display.merge(
        customer_metadata,
        left_on="Cliente",
        right_on="cod_entidade",
        how="left",
    ).drop(columns="cod_entidade")
    customer_display["Faturamento líquido"] = customer_display[
        "Faturamento líquido"
    ].map(format_brl)
    customer_display["Risco estimado"] = customer_display["Risco estimado"].map(
        lambda value: f"{format_pt_number(value * 100, decimals=1)}%"
    )
    colunas_export = [
        "Cliente",
        "SUPERVISOR",
        "VENDEDOR",
        "SETOR",
        "FANTASIA",
        "Perfil",
        "Dias desde a última compra",
        "Notas fiscais (12 meses)",
        "Faturamento líquido",
        "Produtos distintos",
        "Risco estimado",
        "Classificação",
        "Sinais de atenção",
        "Base do risco",
    ]
    st.dataframe(
        customer_display[colunas_export],
        width="stretch",
        lazy=True,
        hide_index=True,
        alt=f"Clientes ordenados por risco e faturamento do perfil {selected_profile.lower()}",
    )

    # Botão de download Excel para a tabela de clientes
    buffer_clientes = io.BytesIO()
    with pd.ExcelWriter(buffer_clientes, engine="openpyxl") as writer:
        customer_export = customer_display[colunas_export].copy()
        customer_export.to_excel(writer, sheet_name="Clientes_Perfil", index=False)

    safe_profile = "".join(
        c if c.isalnum() or c in (" ", "_", "-") else "_" for c in selected_profile
    ).strip().replace(" ", "_")
    st.download_button(
        label="📥 Baixar Clientes em Excel",
        data=buffer_clientes.getvalue(),
        file_name=f"clientes_perfil_{safe_profile.lower()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"download_clientes_{safe_profile}",
    )


@st.fragment(parallel=True)
def _renderizar_tendencia(df, selected_start, selected_end):
    daily = df[["data", "valor_mercadoria"]].copy()
    daily["data"] = pd.to_datetime(daily["data"], errors="coerce").dt.normalize()
    daily["periodo"] = daily["data"].dt.to_period("M")
    start_date = pd.Timestamp(selected_start).normalize()
    end_date = pd.Timestamp(selected_end).normalize()
    latest_date = daily["data"].max()
    months = pd.period_range(
        start_date.to_period("M"),
        min(end_date, latest_date).to_period("M"),
        freq="M",
    )
    monthly = (
        daily.groupby("periodo")["valor_mercadoria"]
        .sum()
        .reindex(months, fill_value=0)
        .rename("realizado")
        .to_frame()
    )
    monthly["data"] = [period.start_time for period in months]
    complete_mask = [
        start_date.date() <= period.start_time.date()
        and end_date.date() >= period.end_time.date()
        and period.end_time.date() <= latest_date.date()
        for period in months
    ]
    complete_months = monthly.loc[complete_mask].copy()
    complete_months["media_movel_3m"] = complete_months["realizado"].rolling(
        3, min_periods=3
    ).mean()

    current_period = latest_date.to_period("M")
    analysis_starts_at_month = start_date.date() <= current_period.start_time.date()
    current_month_is_partial = latest_date.date() < current_period.end_time.date()
    projected_close = None

    if (
        current_period == pd.Timestamp.today().to_period("M")
        and current_month_is_partial
        and analysis_starts_at_month
        and end_date.date() >= latest_date.date()
    ):
        import holidays

        month_start = current_period.start_time.date()
        month_end = current_period.end_time.date()
        holiday_dates = holidays.country_holidays(
            "BR", subdiv="MG", years=[latest_date.year]
        )
        business_days_total = sum(
            day.weekday() < 5 and day not in holiday_dates
            for day in pd.date_range(month_start, month_end, freq="D").date
        )
        business_days_elapsed = sum(
            day.weekday() < 5 and day not in holiday_dates
            for day in pd.date_range(month_start, latest_date.date(), freq="D").date
        )
        if business_days_elapsed:
            projected_close = float(
                monthly.loc[current_period, "realizado"]
                / business_days_elapsed
                * business_days_total
            )

    x_months = [period.strftime("%b/%Y") for period in months]
    y_realizado = [round(float(v), 2) for v in monthly["realizado"]]

    # Mapeia média móvel alinhada a cada mês
    month_to_ma = {
        period.strftime("%b/%Y"): round(float(ma), 2)
        for period, ma in zip(complete_months.index, complete_months["media_movel_3m"])
        if pd.notna(ma)
    }
    y_ma = [month_to_ma.get(m, None) for m in x_months]

    # Prepara a série de projeção pontual para o mês corrente
    y_proj = [None] * len(x_months)
    if projected_close is not None:
        curr_str = current_period.strftime("%b/%Y")
        if curr_str in x_months:
            y_proj[x_months.index(curr_str)] = round(projected_close, 2)

    st.markdown("**Faturamento mensal, média móvel e estimativa do mês atual**")
    options_tendencia = {
        "tooltip": {
            "trigger": "axis",
            "formatter": JsCode(
                "function(params){"
                "var res = params[0].name + '<br/>';"
                "params.forEach(function(p){"
                "if (p.value !== null && p.value !== undefined) {"
                "res += p.marker + ' ' + p.seriesName + ': ' + p.value.toLocaleString('pt-BR', {style:'currency', currency:'BRL'}) + '<br/>';"
                "}"
                "});"
                "return res;"
                "}"
            ),
        },
        "legend": {
            "data": ["Faturamento realizado", "Média móvel (3 meses)", "Estimativa de fechamento"],
            "top": "2%",
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "10%", "top": "15%", "containLabel": True},
        "xAxis": {"type": "category", "data": x_months, "axisLabel": {"rotate": 25}},
        "yAxis": {
            "type": "value",
            "name": "Faturamento (R$)",
            "axisLabel": {
                "formatter": JsCode(
                    "function(value){return value.toLocaleString('pt-BR', {style:'currency', currency:'BRL'});}"
                )
            },
        },
        "series": [
            {
                "name": "Faturamento realizado",
                "type": "bar",
                "data": y_realizado,
                "itemStyle": {"color": "#315784"},
            },
            {
                "name": "Média móvel (3 meses)",
                "type": "line",
                "data": y_ma,
                "lineStyle": {"color": "#E07A2D", "width": 3},
                "itemStyle": {"color": "#E07A2D"},
                "symbol": "circle",
                "symbolSize": 8,
                "connectNulls": True,
            },
            {
                "name": "Estimativa de fechamento",
                "type": "scatter",
                "data": y_proj,
                "itemStyle": {"color": "#D94F4F"},
                "symbol": "diamond",
                "symbolSize": 14,
            },
        ],
    }
    st_echarts(options=options_tendencia, height="450px", key="chart_tendencia_mensal")

    if projected_close is not None:
        st.caption(
            f"Estimativa de fechamento baseada no ritmo dos dias úteis "
            f"observados até {latest_date:%d/%m/%Y}; não é faturamento realizado."
        )
    st.caption(
        "A linha laranja considera somente meses fechados; o mês em andamento "
        "aparece como parcial e não entra na média móvel."
    )


apply_dashboard_theme()
page_header(
    "Análise e previsão",
    "Previsões, segmentação de clientes, risco de validade e tendência de faturamento.",
    icon=":material/insights:",
)

df_base = carregar_df_analise()
if df_base is None or getattr(df_base, "empty", True):
    st.info("Os dados ainda não estão disponíveis no cache. Aguarde o cache ser carregado.")
    st.stop()

df_base["data"] = pd.to_datetime(df_base["data"], errors="coerce").dt.normalize()
df_base = df_base.dropna(subset=["data"]).copy()
if df_base.empty:
    st.warning("A base carregada no cache não contém datas válidas para análise.")
    st.stop()

required_filter_columns = {
    "Supervisor_Real",
    "Vendedor_Real",
    "cod_digitador",
    "Equipe",
    "Setor",
    "Fornecedor",
}
missing_filter_columns = sorted(required_filter_columns.difference(df_base.columns))
if missing_filter_columns:
    st.error(
        "A base carregada no cache não contém as colunas dos filtros: "
        f"{', '.join(missing_filter_columns)}."
    )
    st.stop()

df_sem_periodo = df_base

# Respeita o filtro de supervisor associado ao login caso seja perfil supervisor
user_role = st.session_state.get("user_role", "").lower()
default_supervisor = (
    st.session_state.get("default_supervisor_filter")
    or st.session_state.get("effective_access", {}).get("default_filters", {}).get("supervisor")
)
if user_role == "supervisor" and default_supervisor:
    if "filtro_sup" not in st.session_state or not st.session_state["filtro_sup"]:
        st.session_state["filtro_sup"] = [default_supervisor]

colunas_filtros = st.columns(6)

lista_supervisores = sorted(
    supervisor
    for supervisor in df_sem_periodo["Supervisor_Real"].dropna().astype(str).unique()
    if supervisor.strip() and supervisor.upper() not in SUPERVISORES_EXCLUIDOS
)
_normalizar_multiselect("filtro_sup", lista_supervisores)
with colunas_filtros[0]:
    supervisor_selecionado = st.multiselect(
        "Supervisor:",
        lista_supervisores,
        key="filtro_sup",
        placeholder="(Todos)",
    )

df_parcial = _filtrar_selecao(
    df_sem_periodo, "Supervisor_Real", supervisor_selecionado
)
lista_vendedores = sorted(
    df_parcial.loc[df_parcial["Equipe"] == "EXTERNA", "Vendedor_Real"]
    .dropna()
    .astype(str)
    .unique()
)
_normalizar_multiselect("filtro_vend", lista_vendedores)
with colunas_filtros[1]:
    vendedor_selecionado = st.multiselect(
        "Vendedor:",
        lista_vendedores,
        key="filtro_vend",
        placeholder="(Todos)",
    )

df_parcial = _filtrar_selecao(df_parcial, "Vendedor_Real", vendedor_selecionado)
lista_televendas = sorted(
    nome
    for nome in df_parcial.loc[
        df_parcial["Equipe"] == "TELEVENDAS", "Vendedor_Real"
    ].dropna().astype(str).unique()
    if nome in TELEVENDAS_MAP
)
_normalizar_multiselect("filtro_tele", lista_televendas)
with colunas_filtros[2]:
    televendas_selecionado = st.multiselect(
        "Televendas:",
        lista_televendas,
        key="filtro_tele",
        placeholder="(Todos)",
    )

df_parcial = _filtrar_selecao(df_parcial, "cod_digitador", televendas_selecionado)
lista_setores = sorted(
    df_parcial["Setor"].dropna().astype(str).unique()
)
_normalizar_multiselect("filtro_setor", lista_setores)
with colunas_filtros[3]:
    setor_selecionado = st.multiselect(
        "Setor:",
        lista_setores,
        key="filtro_setor",
        placeholder="(Todos)",
    )

df_parcial = _filtrar_selecao(df_parcial, "Setor", setor_selecionado)
lista_fornecedores = sorted(
    df_parcial["Fornecedor"].dropna().astype(str).unique()
)
_normalizar_multiselect("filtro_fornecedor", lista_fornecedores)
with colunas_filtros[4]:
    fornecedor_selecionado = st.multiselect(
        "Fornecedor:",
        lista_fornecedores,
        key="filtro_fornecedor",
        placeholder="(Todos)",
    )

df_filtrado = _filtrar_selecao(
    df_sem_periodo, "Supervisor_Real", supervisor_selecionado
)
df_filtrado = _filtrar_selecao(
    df_filtrado, "Vendedor_Real", vendedor_selecionado
)
df_filtrado = _filtrar_selecao(
    df_filtrado, "cod_digitador", televendas_selecionado
)
df_filtrado = _filtrar_selecao(df_filtrado, "Setor", setor_selecionado)
df_filtrado = _filtrar_selecao(df_filtrado, "Fornecedor", fornecedor_selecionado)
if df_filtrado.empty:
    st.info("Nenhum dado corresponde aos filtros selecionados.")
    st.stop()

date_min = df_base["data"].min().date()
date_max = df_base["data"].max().date()
with colunas_filtros[5]:
    periodo = st.date_input(
        "Período de análise",
        [date_min, date_max],
        min_value=date_min,
        max_value=date_max,
        key="filtro_periodo_analise",
        format="DD/MM/YYYY",
    )
selected_start = pd.Timestamp(periodo[0]).normalize()
selected_end = (
    pd.Timestamp(periodo[1]).normalize()
    if len(periodo) == 2
    else pd.Timestamp(date_max).normalize()
)
df = df_filtrado[
    (df_filtrado["data"] >= selected_start)
    & (df_filtrado["data"] < selected_end + pd.Timedelta(days=1))
].copy()
if df.empty:
    st.info("Nenhum dado corresponde ao período e aos filtros selecionados.")
    st.stop()

value_total = float(df["valor_mercadoria"].sum())
daily_totals = df.groupby("data")["valor_mercadoria"].sum()
daily_average = float(daily_totals.mean()) if not daily_totals.empty else 0.0
quantity_total = float(df["quantidade"].sum()) if "quantidade" in df.columns else 0

metric_columns = st.columns(3)
metric_columns[0].metric("Faturamento total", format_brl(value_total))
metric_columns[1].metric("Média por dia com venda", format_brl(daily_average))
metric_columns[2].metric("Quantidade total", format_pt_number(quantity_total))

# Restrição de subrelatórios por perfil de usuário
opcoes_analise = ["Previsão", "Risco de validade", "Clientes", "Tendência"]
if user_role in {"supervisor", "televendas"}:
    opcoes_analise = [opcao for opcao in opcoes_analise if opcao != "Risco de validade"]

analysis_view = st.segmented_control(
    "Análise",
    opcoes_analise,
    default="Previsão",
    key="analysis_tabs",
)
as_of_date = pd.Timestamp.today().normalize()

if analysis_view == "Previsão":
    _renderizar_previsao(df_filtrado)
elif analysis_view == "Risco de validade":
    if user_role in {"supervisor", "televendas"}:
        st.warning("Seu perfil não tem permissão para visualizar o relatório de Risco de Validade.")
    else:
        risk_start = as_of_date - pd.Timedelta(days=89)
        risk_sales = df_filtrado[
            (df_filtrado["data"] >= risk_start) & (df_filtrado["data"] <= as_of_date)
        ]
        _renderizar_risco_estoque(risk_sales, as_of_date)
elif analysis_view == "Clientes":
    setores = load_if_cache_ready(
        carregar_setores,
        "carregar_setores",
        get_scoped_cache_key("setores"),
    )
    if setores is None or setores.empty:
        st.info("Os dados de supervisão e clientes ainda não estão no cache. Aguarde a publicação do snapshot.")
    else:
        _renderizar_segmentacao(
            df,
            as_of_date,
            _obter_metadados_clientes(setores),
        )
elif analysis_view == "Tendência":
    _renderizar_tendencia(df, selected_start, selected_end)