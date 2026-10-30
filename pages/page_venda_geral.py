import streamlit as st
import pandas as pd
import threading
from streamlit_echarts import st_echarts, JsCode
from datetime import datetime, timedelta
import calendar
import io

from ui_theme import apply_dashboard_theme, page_header
from ui_formatting import format_brl, format_pt_number
from ui_charts import top_products_chart_spec

apply_dashboard_theme()

# --- RECUPERAR PERFIL E VERIFICAR O QUE DEVE SER EXIBIDO ---
user_role = st.session_state.get("user_role", "supervisor")

exibir_vendedores = user_role in ["supervisor", "gerente", "admin", "diretoria", "inteligencia"]
exibir_televendas = user_role in ["televendas", "gerente", "admin", "diretoria", "inteligencia"]

from cache_loaders import (
    carregar_base_unica,
    get_active_cache_key,
    get_active_cache_version,
    load_if_cache_ready,
    trigger_warm,
)
from queries.vendas_queries import TELEVENDAS_MAP

lazy import holidays

# =============================================================================
# DIAS ÚTEIS (MG) — base para a projeção de fechamento do mês
# =============================================================================
br_holidays = holidays.Brazil(subdiv='MG')


def is_business_day(date):
    """True se for dia útil em MG (seg–sex e não feriado)."""
    return date.weekday() < 5 and date not in br_holidays


def contar_dias_uteis(data_ini, data_fim):
    """Conta dias úteis (seg–sex, exceto feriados MG) entre data_ini e data_fim, inclusive."""
    if data_ini > data_fim:
        return 0
    total = 0
    atual = data_ini
    while atual <= data_fim:
        if is_business_day(atual):
            total += 1
        atual += timedelta(days=1)
    return total


def projetar_faturamento_por_dias_uteis(faturamento_atual, data_hoje, ano, mes):
    """
    Projeta o faturamento do mês com base no ritmo de dias úteis.
    """
    if faturamento_atual <= 0:
        return float(faturamento_atual)

    ini_mes = data_hoje.replace(day=1)
    ultimo_dia_mes = data_hoje.replace(day=calendar.monthrange(ano, mes)[1])

    ultimo_dia_util = data_hoje
    while ultimo_dia_util >= ini_mes and not is_business_day(ultimo_dia_util):
        ultimo_dia_util -= timedelta(days=1)

    dias_uteis_decorridos = contar_dias_uteis(ini_mes, ultimo_dia_util)
    dias_uteis_totais = contar_dias_uteis(ini_mes, ultimo_dia_mes)

    if dias_uteis_decorridos <= 0 or dias_uteis_totais <= 0:
        return float(faturamento_atual)

    return (faturamento_atual / dias_uteis_decorridos) * dias_uteis_totais


# =============================================================================
# HEARTBEAT — monitora a versão global do cache e reroda a página quando
# um novo snapshot é publicado pelo scheduler/warm. Enquanto o warm está em
# execução, a versão NÃO muda — os gráficos ficam estáticos com os dados do
# snapshot antigo.
# =============================================================================
@st.fragment(run_every="15s")
def _keep_cache_warm():
    version_atual = get_active_cache_version()
    chave = "_cache_version_venda_geral"
    anterior = st.session_state.get(chave)

    if anterior is None:
        st.session_state[chave] = version_atual
    elif version_atual != anterior:
        st.session_state[chave] = version_atual
        st.rerun()


# --- SUPERVISORES EXCLUÍDOS (mesma regra da query SQL original) ---
SUPERVISORES_EXCLUIDOS = {
    'LIVRE METROPOLITANO', 'LIVRE NORTE', 'VALMOR SUPERVISOR',
    'SUPERVISOR INTERNO', 'SUPERVISOR ADMINISTRATIVO',
    'SUPERVISOR ZONA DA MATA LESTE', 'GLICIA MELO'
}

# --- DERIVAÇÃO DE FILTROS A PARTIR DO DATAFRAME (sem queries por combinação) ---
def obter_lista_supervisores(df):
    if df is None or df.empty:
        return ["Todos"]
    sups = df['Supervisor_Real'].dropna().astype(str).unique().tolist()
    sups = [s for s in sups if s.strip() and s not in SUPERVISORES_EXCLUIDOS]
    return ["Todos"] + sorted(sups)

def obter_lista_vendedores(df, supervisor="Todos"):
    if df is None or df.empty:
        return ["Todos"]
    df_f = df
    if supervisor != "Todos":
        df_f = df_f[df_f['Supervisor_Real'].str.upper() == supervisor.upper()]
    df_ext = df_f[df_f['Equipe'] == 'EXTERNA']
    vendedores = df_ext['Vendedor'].dropna().astype(str).unique().tolist()
    vendedores = [v for v in vendedores if v.strip()]
    return ["Todos"] + sorted(vendedores)

def obter_lista_televendas(df, supervisor="Todos", vendedor="Todos"):
    if df is None or df.empty:
        return ["Todos"]
    df_f = df
    if supervisor != "Todos":
        df_f = df_f[df_f['Supervisor_Real'].str.upper() == supervisor.upper()]
    if vendedor != "Todos":
        df_f = df_f[df_f['Vendedor'].str.upper() == vendedor.upper()]
    df_tele = df_f[df_f['Equipe'] == 'TELEVENDAS']
    nomes_validos = set(TELEVENDAS_MAP.keys())
    televendas = df_tele['Vendedor_Real'].dropna().astype(str).unique().tolist()
    televendas = [t for t in televendas if t in nomes_validos]
    return ["Todos"] + sorted(televendas)

# --- B. FUNÇÕES DE FORMATAÇÃO E CÁLCULO ---
def formata_real(valor):
    return format_brl(valor)


def calcula_delta(atual, anterior):
    return ((atual - anterior) / anterior * 100) if anterior > 0 else 0

# Carregamento da base — sempre lê o snapshot ATIVO. Enquanto o scheduler
# aquece a próxima versão em background, este ponteiro aponta para os dados
# antigos e os gráficos permanecem estáticos.
cache_key = get_active_cache_key()
df_matriz_bruta = load_if_cache_ready(
    carregar_base_unica,
    "carregar_base_unica",
    cache_key,
)

# Ativa o heartbeat. Ele apenas compara a versão global e dispara um rerun
# completo quando o warm publica um novo snapshot.
_keep_cache_warm()

# --- C. LAYOUT E FILTROS ---
col_titulo, col_btn = st.columns([3, 1])
with col_titulo:
    page_header(
        "Acompanhamento de Vendas",
        "Visão operacional do faturamento, vendedores e desempenho por origem.",
        icon=":material/bar_chart:",
    )
with col_btn:
    btn_refresh = st.button("🔄 Atualizar Dados (Refresh)", width="stretch")

if btn_refresh:
    # Dispara um warm em thread separada: aquece uma chave NOVA e, ao final,
    # publica atomicamente. Nenhuma tela pisca — o fragment detecta a troca
    # de versão e reroda a página com os dados novos.
    threading.Thread(
        target=trigger_warm,
        kwargs={"source": "manual"},
        daemon=True,
        name="CacheBackgroundRefresh-manual",
    ).start()
    st.toast("Aquecimento solicitado. Os gráficos atualizarão em instantes.", icon="🔥")

if df_matriz_bruta is None:
    st.info(
        "Os dados ainda não estão disponíveis no cache. "
        "Aguarde o aquecimento automático ou clique em "
        "'Atualizar Dados (Refresh)' para carregar esta página."
    )
    st.stop()

espacos = []
if exibir_vendedores:
    espacos.extend([1.5, 1.5])
if exibir_televendas:
    espacos.append(1.5)
espacos.append(1.8)

cols_filtros = st.columns(espacos)
col_idx = 0

supervisor_selecionado = "Todos"
vendedor_selecionado = "Todos"
televendas_selecionado = "Todos"

if exibir_vendedores:
    lista_supervisores = obter_lista_supervisores(df_matriz_bruta)
    with cols_filtros[col_idx]:
        supervisor_selecionado = st.selectbox(
            "Supervisor",
            lista_supervisores,
            key="filtro_sup",
        )
    col_idx += 1

    lista_vendedores = obter_lista_vendedores(df_matriz_bruta, supervisor_selecionado)
    if vendedor_selecionado not in lista_vendedores:
        vendedor_selecionado = "Todos"
    with cols_filtros[col_idx]:
        vendedor_selecionado = st.selectbox(
            "Vendedor",
            lista_vendedores,
            key="filtro_vend",
        )
    col_idx += 1

if exibir_televendas:
    lista_televendas = obter_lista_televendas(df_matriz_bruta, supervisor_selecionado, vendedor_selecionado)
    if televendas_selecionado not in lista_televendas:
        televendas_selecionado = "Todos"
    with cols_filtros[col_idx]:
        televendas_selecionado = st.selectbox(
            "Televendas",
            lista_televendas,
            key="filtro_tele",
        )
    col_idx += 1

with cols_filtros[col_idx]:
    ini_mes_padrao = datetime.now().date().replace(day=1)
    periodo_graf = st.date_input(
        "Período Gráficos",
        [ini_mes_padrao, datetime.now().date()],
        key="filtro_graf",
        format="DD/MM/YYYY",
    )

d_g_ini = periodo_graf[0] if len(periodo_graf) > 0 else ini_mes_padrao
d_g_fim = periodo_graf[1] if len(periodo_graf) > 1 else datetime.now().date()

# --- E. FUNÇÕES DE FILTRO PANDAS ---
def filtrar_equipe(df_raw, sup, vend, is_tele_flag):
    if df_raw is None or df_raw.empty:
        return df_raw

    equipe_str = 'TELEVENDAS' if is_tele_flag else 'EXTERNA'
    df = df_raw[df_raw['Equipe'] == equipe_str].copy()

    if sup != 'Todos':
        df = df[df['Supervisor_Real'].str.upper() == sup.upper()]

    if vend != 'Todos':
        df = df[df['Vendedor_Real'].str.upper() == vend.upper()]

    return df

def obter_base_graficos_origem(df_raw, sup, vend, tele):
    if df_raw is None or df_raw.empty:
        return df_raw

    df = df_raw.copy()
    if sup != "Todos":
        df = df[df['Supervisor_Real'].str.upper() == sup.upper()]

    if vend != "Todos":
        df = df[df['Vendedor'].str.upper() == vend.upper()]

    if tele != "Todos":
        vendedores_assoc = df[df['cod_digitador'].str.upper() == tele.upper()]['Vendedor'].unique()
        mask_a_propria_tele = df['cod_digitador'].str.upper() == tele.upper()
        mask_vendedores_da_tele = df['Vendedor'].isin(vendedores_assoc) & (df['Equipe'] == 'EXTERNA')
        df = df[mask_a_propria_tele | mask_vendedores_da_tele]

    return df

def extrair_kpi(df):
    if df is not None and not df.empty:
        return {
            "fat": float(df['valor_mercadoria'].sum()),
            "pos": int(df['cod_entidade'].nunique()),
            "mix": int(df['id_produto'].nunique()),
            "notas": int(df['NF'].nunique())
        }
    return {"fat": 0, "pos": 0, "mix": 0, "notas": 0}

# --- F. RENDERIZAÇÃO MODULAR ---
def render_kpis(df_base, titulo_secao):
    st.markdown(f"#### {titulo_secao}")
    if df_base is None or df_base.empty:
        st.info("Sem dados base para calcular os KPIs.")
        return

    data_hoje = datetime.now().date()
    ano_atual, mes_atual = data_hoje.year, data_hoje.month

    ini_mes_atual = pd.to_datetime(data_hoje.replace(day=1))
    fim_mes_atual_exclusivo = pd.to_datetime(data_hoje + timedelta(days=1))

    ini_mes_ant = pd.to_datetime((data_hoje.replace(day=1) - timedelta(days=1)).replace(day=1))
    ultimo_dia_mes_ant = calendar.monthrange(ini_mes_ant.year, ini_mes_ant.month)[1]
    dia_comparacao = min(data_hoje.day, ultimo_dia_mes_ant)
    fim_mes_ant_mtd = pd.to_datetime(ini_mes_ant.replace(day=dia_comparacao))
    fim_mes_ant_mtd_exclusivo = fim_mes_ant_mtd + pd.Timedelta(days=1)

    ini_ano_atual = pd.to_datetime(data_hoje.replace(month=1, day=1))
    fim_ano_atual_exclusivo = pd.to_datetime(data_hoje + timedelta(days=1))

    ini_mes_ano_ant = pd.to_datetime(ini_mes_atual.replace(year=ano_atual - 1))
    dia_comp_ano_ant = min(data_hoje.day, calendar.monthrange(ini_mes_ano_ant.year, ini_mes_ano_ant.month)[1])
    fim_mes_ano_ant_mtd = pd.to_datetime(ini_mes_ano_ant.replace(day=dia_comp_ano_ant))
    fim_mes_ano_ant_mtd_exclusivo = fim_mes_ano_ant_mtd + pd.Timedelta(days=1)

    ini_ano_ant = pd.to_datetime(ini_ano_atual.replace(year=ano_atual - 1))
    fim_ano_ant = pd.to_datetime(data_hoje.replace(year=ano_atual - 1))
    fim_ano_ant_exclusivo = fim_ano_ant + pd.Timedelta(days=1)

    df_kpi_atual = df_base[(df_base['data'] >= ini_mes_atual) & (df_base['data'] < fim_mes_atual_exclusivo)]
    df_kpi_ant_mes = df_base[(df_base['data'] >= ini_mes_ant) & (df_base['data'] < fim_mes_ant_mtd_exclusivo)]
    df_kpi_ano_ant_mes = df_base[(df_base['data'] >= ini_mes_ano_ant) & (df_base['data'] < fim_mes_ano_ant_mtd_exclusivo)]
    df_ano_atual = df_base[(df_base['data'] >= ini_ano_atual) & (df_base['data'] < fim_ano_atual_exclusivo)]
    df_ano_ant_ytd = df_base[(df_base['data'] >= ini_ano_ant) & (df_base['data'] < fim_ano_ant_exclusivo)]

    kpi_atual = extrair_kpi(df_kpi_atual)
    kpi_ant_mes = extrair_kpi(df_kpi_ant_mes)
    kpi_ano_ant_mes = extrair_kpi(df_kpi_ano_ant_mes)

    fat_ano_atual = float(df_ano_atual['valor_mercadoria'].sum()) if not df_ano_atual.empty else 0
    fat_ano_ant_ytd = float(df_ano_ant_ytd['valor_mercadoria'].sum()) if not df_ano_ant_ytd.empty else 0

    ticket_atual = kpi_atual['fat'] / kpi_atual['pos'] if kpi_atual['pos'] > 0 else 0
    ticket_ant = kpi_ant_mes['fat'] / kpi_ant_mes['pos'] if kpi_ant_mes['pos'] > 0 else 0
    ticket_ano_ant_mes = kpi_ano_ant_mes['fat'] / kpi_ano_ant_mes['pos'] if kpi_ano_ant_mes['pos'] > 0 else 0

    projecao = projetar_faturamento_por_dias_uteis(
        kpi_atual['fat'], data_hoje, ano_atual, mes_atual
    )

    delta_fat = calcula_delta(kpi_atual['fat'], kpi_ant_mes['fat'])
    delta_pos = calcula_delta(kpi_atual['pos'], kpi_ant_mes['pos'])
    delta_mix = calcula_delta(kpi_atual['mix'], kpi_ant_mes['mix'])
    delta_tkt = calcula_delta(ticket_atual, ticket_ant)
    delta_ytd = calcula_delta(fat_ano_atual, fat_ano_ant_ytd)
    delta_fat_ano = calcula_delta(kpi_atual['fat'], kpi_ano_ant_mes['fat'])
    delta_pos_ano = calcula_delta(kpi_atual['pos'], kpi_ano_ant_mes['pos'])
    delta_mix_ano = calcula_delta(kpi_atual['mix'], kpi_ano_ant_mes['mix'])
    delta_tkt_ano = calcula_delta(ticket_atual, ticket_ano_ant_mes)

    mes_nomes = {1:'Jan', 2:'Fev', 3:'Mar', 4:'Abr', 5:'Mai', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Set', 10:'Out', 11:'Nov', 12:'Dez'}

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric(
            f"Fat. ({mes_nomes[mes_atual]})",
            formata_real(kpi_atual['fat']),
            f"{delta_fat:.1f}% vs {mes_nomes[(mes_atual-2)%12+1]}",
            icon=":material/payments:",
        )
        st.caption(f"**Ano Ant.** (até dia {dia_comparacao}): {formata_real(kpi_ano_ant_mes['fat'])} ({delta_fat_ano:.1f}%)")
        if projecao < kpi_ant_mes['fat']:
            st.caption(f"⚠️ Tendência: {formata_real(projecao)}")
        else:
            st.caption(f"✅ Projeção: {formata_real(projecao)}")
    with k2:
        st.metric(
            f"Fat. Ano ({ano_atual})",
            formata_real(fat_ano_atual),
            f"{delta_ytd:.1f}% vs {ano_atual-1}",
            icon=":material/trending_up:",
        )
        st.caption(f"**Ano Passado:** {formata_real(fat_ano_ant_ytd)}")
    with k3:
        st.metric(
            "Positivação",
            f"{kpi_atual['pos']}",
            f"{delta_pos:.1f}% vs {mes_nomes[(mes_atual-2)%12+1]}",
            icon=":material/groups:",
        )
        st.caption(f"Mês ant: {kpi_ant_mes['pos']}")
        st.caption(f"**Ano Ant:** {kpi_ano_ant_mes['pos']} ({delta_pos_ano:.1f}%)")
    with k4:
        st.metric(
            "Mix Produtos",
            f"{kpi_atual['mix']}",
            f"{delta_mix:.1f}% vs {mes_nomes[(mes_atual-2)%12+1]}",
            icon=":material/category:",
        )
        st.caption(f"Mês ant: {kpi_ant_mes['mix']}")
        st.caption(f"**Ano Ant:** {kpi_ano_ant_mes['mix']} ({delta_mix_ano:.1f}%)")
    with k5:
        st.metric(
            "Ticket Médio",
            formata_real(ticket_atual),
            f"{delta_tkt:.1f}% vs {mes_nomes[(mes_atual-2)%12+1]}",
            icon=":material/receipt:",
        )
        st.caption(f"Mês ant: {formata_real(ticket_ant)}")
        st.caption(f"**Ano Ant:** {formata_real(ticket_ano_ant_mes)} ({delta_tkt_ano:.1f}%)")


@st.fragment
def render_top_products(df_top, sufixo_key, titulo_secao):
    c_t, c_r = st.columns([1, 1])
    with c_t:
        st.markdown("**Top 10 Produtos (15 Dias)**")
    with c_r:
        metrica = st.segmented_control(
            "Métrica:",
            ["Valor", "Qtd"],
            default="Valor",
            label_visibility="collapsed",
            key=f"radio_top_10_{sufixo_key}",
        )

    if df_top.empty:
        st.info("Sem vendas recentes.")
        return

    df_top_agg = df_top.groupby("Produto", as_index=False).agg(
        ValorTotal=("valor_mercadoria", "sum"),
        QuantidadeTotal=("quantidade", "sum"),
    )
    col_alvo = "ValorTotal" if metrica == "Valor" else "QuantidadeTotal"
    df_plot = df_top_agg.nlargest(10, col_alvo).sort_values(col_alvo, ascending=True)
    produtos = df_plot["Produto"].astype(str).tolist()
    valores = [
        round(float(value), 2) if metrica == "Valor" else int(value)
        for value in df_plot[col_alvo].tolist()
    ]
    display_values = (
        [format_brl(value) for value in valores]
        if metrica == "Valor"
        else [format_pt_number(value) for value in valores]
    )
    st.echarts_chart(
        spec=top_products_chart_spec(produtos, valores, display_values, metrica),
        height=300,
        alt=f"Dez produtos com maior {metrica.lower()} nos últimos quinze dias: {titulo_secao}",
    )


def render_graficos(df_base, d_ini, d_fim, sufixo_key, titulo_secao, df_global=None):
    if titulo_secao:
        st.markdown(f"#### {titulo_secao}")

    if df_base is None or df_base.empty:
        st.info("Sem dados.")
        return

    mask_datas = (df_base['data'].dt.date >= d_ini) & (df_base['data'].dt.date <= d_fim)
    df_graf = df_base[mask_datas]

    data_hoje = datetime.now().date()
    mask_top15 = (df_base['data'].dt.date >= (data_hoje - timedelta(days=15))) & (df_base['data'].dt.date <= data_hoje)
    df_top = df_base[mask_top15]

    c1, c2, c3 = st.columns([1, 1.5, 1.5])

    # ---------- GRÁFICO DE ORIGEM (Pizza/Donut) ----------
    with c1:
        st.markdown("**Origem**")
        df_pie_source = df_global if df_global is not None else df_base
        mask_pie = (df_pie_source['data'].dt.date >= d_ini) & (df_pie_source['data'].dt.date <= d_fim)
        df_pie = df_pie_source[mask_pie]

        if not df_pie.empty:
            df_ori_agg = df_pie.groupby('origem_venda', as_index=False)['valor_mercadoria'].sum()
            df_ori_agg = df_ori_agg.rename(columns={'valor_mercadoria': 'ValorTotal', 'origem_venda': 'origem_titulo'})

            data_pie = [
                {"name": row["origem_titulo"], "value": round(row["ValorTotal"], 2)}
                for _, row in df_ori_agg.iterrows()
            ]
            colors = {
                "Televendas": "#ff00ff",
                "Vendedor": "#0095ff",
                "Internet": "#ff0000",
                "BBS": "#00ff0d",
            }
            color_list = [colors.get(item["name"], "#ccc") for item in data_pie]
            options_pie = {
                "tooltip": {
                    "trigger": "item",
                    "formatter": JsCode(
                        "function(params){"
                        "return params.name + ': ' + params.value.toLocaleString('pt-BR', "
                        "{style:'currency', currency:'BRL'}) + ' (' + params.percent + '%)';"
                        "}"
                    ),
                },
                "legend": {"orient": "horizontal", "bottom": 0, "left": "center"},
                "series": [
                    {
                        "type": "pie",
                        "radius": ["40%", "70%"],
                        "avoidLabelOverlap": False,
                        "itemStyle": {
                            "borderRadius": 8,
                            "borderColor": "#fff",
                            "borderWidth": 2,
                        },
                        "label": {"show": True, "formatter": "{b}\n{d}%"},
                        "emphasis": {"scale": True},
                        "data": data_pie,
                        "color": color_list,
                    }
                ],
            }
            st_echarts(
                options=options_pie,
                height="300px",
                key=f"pie_origem_{sufixo_key}",
            )
        else:
            st.info("Sem dados.")

    # ---------- GRÁFICO DE VENDA DIÁRIA (Barras + Linha) ----------
    with c2:
        st.markdown("**Venda Diária**")
        if not df_graf.empty:
            df_graf_temp = df_graf.copy()
            df_graf_temp['Data_Dia'] = df_graf_temp['data'].dt.date
            df_dia_agg = df_graf_temp.groupby('Data_Dia', as_index=False)['valor_mercadoria'].sum()
            df_dia_agg = df_dia_agg.rename(columns={'valor_mercadoria': 'ValorTotal'})
            df_dia_agg = df_dia_agg.sort_values('Data_Dia')
            df_dia_agg['Data_Dia_Str'] = pd.to_datetime(df_dia_agg['Data_Dia']).dt.strftime('%d/%m')

            x_vals = df_dia_agg["Data_Dia_Str"].tolist()
            y_vals = [round(float(value), 2) for value in df_dia_agg["ValorTotal"].tolist()]
            media = round(float(df_dia_agg["ValorTotal"].mean()), 2)
            options_daily = {
                "tooltip": {
                    "trigger": "axis",
                    "formatter": JsCode(
                        "function(params){"
                        "var res = params[0].name + '<br/>';"
                        "params.forEach(function(p){"
                        "res += p.seriesName + ': ' + p.value.toLocaleString('pt-BR', "
                        "{style:'currency', currency:'BRL'}) + '<br/>';"
                        "});"
                        "return res;"
                        "}"
                    ),
                },
                "grid": {
                    "left": "3%",
                    "right": "4%",
                    "bottom": "10%",
                    "top": "10%",
                    "containLabel": True,
                },
                "xAxis": {
                    "type": "category",
                    "data": x_vals,
                    "axisLabel": {"rotate": 30},
                },
                "yAxis": {
                    "type": "value",
                    "name": "R$",
                    "axisLabel": {
                        "formatter": JsCode(
                            "function(value){return value.toLocaleString('pt-BR', "
                            "{style:'currency', currency:'BRL'});}"
                        )
                    },
                },
                "series": [
                    {
                        "name": "Venda",
                        "type": "bar",
                        "data": y_vals,
                        "itemStyle": {"color": "#00BFFF", "opacity": 0.7},
                        "markLine": {
                            "data": [{"yAxis": media, "name": "Média"}],
                            "lineStyle": {"color": "red", "type": "dashed"},
                            "label": {
                                "formatter": JsCode(
                                    "function(params){return 'Média: ' + "
                                    "params.value.toLocaleString('pt-BR', "
                                    "{style:'currency', currency:'BRL'});}"
                                ),
                                "color": "red",
                            },
                        },
                    },
                    {
                        "name": "Tendência",
                        "type": "line",
                        "data": y_vals,
                        "smooth": True,
                        "lineStyle": {"color": "orange", "width": 2},
                        "symbol": "circle",
                        "symbolSize": 6,
                        "itemStyle": {"color": "orange"},
                        "showSymbol": True,
                    },
                ],
            }
            st_echarts(
                options=options_daily,
                height="300px",
                key=f"bar_diaria_{sufixo_key}",
            )
        else:
            st.info("Sem dados.")

    # ---------- TOP 10 PRODUTOS (Barra horizontal) ----------
    with c3:
        render_top_products(df_top, sufixo_key, titulo_secao)

def render_tabela(df_base, d_ini, d_fim, is_tele_flag, titulo):
    st.subheader(titulo)
    if df_base is None or df_base.empty:
        st.info("Nenhum dado para o período selecionado.")
        return

    mask_datas = (df_base['data'].dt.date >= d_ini) & (df_base['data'].dt.date <= d_fim)
    df_tab = df_base[mask_datas].copy()

    if not is_tele_flag:
        df_tab = df_tab[df_tab['origem_venda'] == 'Vendedor']

    if not df_tab.empty:
        df_tab['Data'] = df_tab['data'].dt.date

        df_tab_agg = df_tab.groupby(['Supervisor_Real', 'Vendedor_Real', 'Data'], as_index=False)['valor_mercadoria'].sum()
        df_tab_agg = df_tab_agg.rename(columns={'valor_mercadoria': 'ValorTotal', 'Supervisor_Real': 'SUPERVISOR', 'Vendedor_Real': 'Vendedor'})

        df_tab_agg['Data'] = pd.to_datetime(df_tab_agg['Data'])
        df_tab_agg['Dia'] = df_tab_agg['Data'].dt.strftime('%d/%m')

        if is_tele_flag:
            pivot = df_tab_agg.pivot_table(index='Vendedor', columns='Dia', values='ValorTotal', aggfunc='sum', fill_value=0)
            colunas_dias = [c for c in pivot.columns if c != 'Total']
            pivot['Total'] = pivot[colunas_dias].sum(axis=1)
            pivot.loc['TOTAL GERAL'] = pivot.sum(numeric_only=True)
            pivot = pivot.sort_values('Total', ascending=False)

            if 'TOTAL GERAL' in pivot.index:
                linha_total_geral = pivot.loc['TOTAL GERAL']
                pivot = pivot.drop('TOTAL GERAL')
                pivot.loc['TOTAL GERAL'] = linha_total_geral

            st.dataframe(
                pivot.style.format(formata_real),
                width="stretch",
                alt=f"Vendas diárias por vendedor de televendas, período {d_ini} a {d_fim}",
            )

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                pivot_export = pivot.copy()
                pivot_export.to_excel(writer, sheet_name='Dados', index=True)
            st.download_button(
                label="📥 Baixar Excel (Televendas)",
                data=buffer.getvalue(),
                file_name="detalhamento_televendas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_tele_{d_ini}_{d_fim}"
            )

        else:
            supervisores_list = df_tab_agg.groupby('SUPERVISOR')['ValorTotal'].sum().sort_values(ascending=False).index
            for sup in supervisores_list:
                df_sup = df_tab_agg[df_tab_agg['SUPERVISOR'] == sup]
                total_sup = df_sup['ValorTotal'].sum()
                safe_sup = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in sup)
                with st.expander(f"👤 {sup}  |  TOTAL: {formata_real(total_sup)}"):
                    pivot = df_sup.pivot_table(index='Vendedor', columns='Dia', values='ValorTotal', aggfunc='sum', fill_value=0)
                    pivot['Total'] = pivot.sum(axis=1)
                    pivot = pivot.sort_values('Total', ascending=False)
                    colunas_dias_sup = [c for c in pivot.columns if c != 'Total']
                    linha_total_sup = pivot[colunas_dias_sup].sum()
                    linha_total_sup['Total'] = linha_total_sup.sum()
                    pivot.loc['TOTAL GERAL'] = linha_total_sup
                    st.dataframe(
                        pivot.style.format(formata_real),
                        width="stretch",
                        alt=f"Vendas diárias por vendedor da equipe {sup}, período {d_ini} a {d_fim}",
                    )

                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        pivot_export = pivot.copy()
                        pivot_export.to_excel(writer, sheet_name='Dados', index=True)
                    st.download_button(
                        label="📥 Baixar Excel",
                        data=buffer.getvalue(),
                        file_name=f"detalhamento_{safe_sup}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_sup_{safe_sup}_{d_ini}_{d_fim}"
                    )
    else:
        st.info("Nenhum dado retornado para a tabela detalhada.")

# --- G. GATILHOS DA INTERFACE PRINCIPAL ---
df_vendedores = None
df_televendas = None
if exibir_vendedores:
    df_vendedores = filtrar_equipe(df_matriz_bruta, supervisor_selecionado, vendedor_selecionado, is_tele_flag=False)
if exibir_televendas:
    df_televendas = filtrar_equipe(df_matriz_bruta, "Todos", televendas_selecionado, is_tele_flag=True)

df_global_vend = obter_base_graficos_origem(df_matriz_bruta, supervisor_selecionado, vendedor_selecionado, televendas_selecionado)
df_global_tele = obter_base_graficos_origem(df_matriz_bruta, supervisor_selecionado, vendedor_selecionado, televendas_selecionado)

if exibir_vendedores:
    render_kpis(df_vendedores, "📈 Vendas - Equipe Externa")
    st.markdown("---")

if exibir_televendas:
    render_kpis(df_televendas, "🎧 Vendas - Equipe Televendas")
    st.markdown("---")

if exibir_vendedores or exibir_televendas:
    st.markdown("### 📊 Visão Gráfica")

if exibir_vendedores:
    render_graficos(df_vendedores, d_g_ini, d_g_fim, "vend", "Equipe Externa", df_global=df_global_vend)
    if exibir_televendas: st.markdown("<br>", unsafe_allow_html=True)

if exibir_televendas:
    render_graficos(df_televendas, d_g_ini, d_g_fim, "tele", "Equipe Televendas", df_global=df_global_tele)

st.markdown("---")

if exibir_vendedores:
    render_tabela(df_vendedores, d_g_ini, d_g_fim, False, "📂 Detalhamento Diário (Supervisor / Vendedor)")

if exibir_televendas:
    render_tabela(df_televendas, d_g_ini, d_g_fim, True, "🎧 Detalhamento Diário (Televendas)")