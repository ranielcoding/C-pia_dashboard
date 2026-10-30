from datetime import date, datetime, timedelta
import calendar
import pandas as pd
import numpy as np


def formata_real(valor) -> str:
    """Formata um valor numérico para R$ com vírgula decimal."""
    if pd.isna(valor):
        valor = 0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcula_delta(atual, anterior) -> float:
    """Calcula variação percentual entre dois valores."""
    if anterior <= 0:
        return 0
    return (atual - anterior) / anterior * 100


def _contar_com_devolucao(df, coluna: str) -> int:
    """
    Conta entidades únicas na coluna, descontando as que aparecem
    SOMENTE em devoluções (sem nenhuma linha de 'venda' no período).

    - Entidade que tem ao menos 1 'venda'  →  conta +1
    - Entidade com somente devolução/devolucao parcial  →  conta -1
    """
    if "operacao" not in df.columns:
        return int(df[coluna].nunique())

    op = df["operacao"].astype(str).str.lower().str.strip()
    com_venda = set(df.loc[op == "venda", coluna].dropna().unique())
    so_devolucao = (
        set(df.loc[op.isin(["devolucao", "devolucao parcial"]), coluna].dropna().unique())
        - com_venda
    )
    return len(com_venda) - len(so_devolucao)


def extrair_kpi(df) -> dict:
    """Extrai KPIs básicos de um DataFrame de vendas."""
    if df is None or df.empty:
        return {"fat": 0, "pos": 0, "mix": 0, "notas": 0}
    return {
        "fat": float(df["valor_mercadoria"].sum()),
        "pos": _contar_com_devolucao(df, "cod_entidade"),
        "mix": _contar_com_devolucao(df, "id_produto"),
        "notas": int(df["NF"].nunique()),
    }



def render_kpis(df_base) -> None:
    """Renderiza os KPIs de vendas com métricas de comparação mensal/ano."""
    import streamlit as st

    st.markdown("### 📈 Indicadores Consolidados")
    if df_base is None or df_base.empty:
        st.info("Sem dados para os KPIs.")
        return

    data_hoje = datetime.now().date()
    ano_atual, mes_atual = data_hoje.year, data_hoje.month

    ini_mes_atual = pd.to_datetime(data_hoje.replace(day=1))
    fim_mes_atual = pd.to_datetime(data_hoje)
    ini_mes_ant = pd.to_datetime((data_hoje.replace(day=1) - timedelta(days=1)).replace(day=1))
    ultimo_dia_mes_ant = calendar.monthrange(ini_mes_ant.year, ini_mes_ant.month)[1]
    dia_comparacao = min(data_hoje.day, ultimo_dia_mes_ant)
    fim_mes_ant_mtd = pd.to_datetime(ini_mes_ant.replace(day=dia_comparacao))

    ini_ano_atual = pd.to_datetime(data_hoje.replace(month=1, day=1))
    fim_ano_atual = pd.to_datetime(data_hoje)
    ini_mes_ano_ant = pd.to_datetime(ini_mes_atual.replace(year=ano_atual - 1))
    dia_comp_ano_ant = min(data_hoje.day, calendar.monthrange(ini_mes_ano_ant.year, ini_mes_ano_ant.month)[1])
    fim_mes_ano_ant_mtd = pd.to_datetime(ini_mes_ano_ant.replace(day=dia_comp_ano_ant))
    ini_ano_ant = pd.to_datetime(ini_ano_atual.replace(year=ano_atual - 1))
    fim_ano_ant = pd.to_datetime(data_hoje.replace(year=ano_atual - 1))

    df_kpi_atual = df_base[(df_base["data"] >= ini_mes_atual) & (df_base["data"] <= fim_mes_atual)]
    df_kpi_ant_mes = df_base[(df_base["data"] >= ini_mes_ant) & (df_base["data"] <= fim_mes_ant_mtd)]
    df_kpi_ano_ant_mes = df_base[(df_base["data"] >= ini_mes_ano_ant) & (df_base["data"] <= fim_mes_ano_ant_mtd)]
    df_ano_atual = df_base[(df_base["data"] >= ini_ano_atual) & (df_base["data"] <= fim_ano_atual)]
    df_ano_ant_ytd = df_base[(df_base["data"] >= ini_ano_ant) & (df_base["data"] <= fim_ano_ant)]

    kpi_atual = extrair_kpi(df_kpi_atual)
    kpi_ant_mes = extrair_kpi(df_kpi_ant_mes)
    kpi_ano_ant_mes = extrair_kpi(df_kpi_ano_ant_mes)

    fat_ano_atual = float(df_ano_atual["valor_mercadoria"].sum()) if not df_ano_atual.empty else 0
    fat_ano_ant_ytd = float(df_ano_ant_ytd["valor_mercadoria"].sum()) if not df_ano_ant_ytd.empty else 0

    ticket_atual = kpi_atual["fat"] / kpi_atual["pos"] if kpi_atual["pos"] > 0 else 0
    ticket_ant = kpi_ant_mes["fat"] / kpi_ant_mes["pos"] if kpi_ant_mes["pos"] > 0 else 0
    ticket_ano_ant_mes = kpi_ano_ant_mes["fat"] / kpi_ano_ant_mes["pos"] if kpi_ano_ant_mes["pos"] > 0 else 0

    dia_dia = data_hoje.day
    _, total_dias = calendar.monthrange(ano_atual, mes_atual)
    projecao = (kpi_atual["fat"] / dia_dia * total_dias) if (kpi_atual["fat"] > 0 and dia_dia > 0) else kpi_atual["fat"]

    delta_fat = calcula_delta(kpi_atual["fat"], kpi_ant_mes["fat"])
    delta_pos = calcula_delta(kpi_atual["pos"], kpi_ant_mes["pos"])
    delta_mix = calcula_delta(kpi_atual["mix"], kpi_ant_mes["mix"])
    delta_tkt = calcula_delta(ticket_atual, ticket_ant)
    delta_ytd = calcula_delta(fat_ano_atual, fat_ano_ant_ytd)
    delta_fat_ano = calcula_delta(kpi_atual["fat"], kpi_ano_ant_mes["fat"])
    delta_pos_ano = calcula_delta(kpi_atual["pos"], kpi_ano_ant_mes["pos"])
    delta_mix_ano = calcula_delta(kpi_atual["mix"], kpi_ano_ant_mes["mix"])
    delta_tkt_ano = calcula_delta(ticket_atual, ticket_ano_ant_mes)

    mes_nomes = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
    }

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric(
            f"Fat. ({mes_nomes[mes_atual]})",
            formata_real(kpi_atual["fat"]),
            f"{delta_fat:.1f}% vs {mes_nomes[(mes_atual - 2) % 12 + 1]}",
        )
        st.caption(f"Ano Ant.: {formata_real(kpi_ano_ant_mes['fat'])} ({delta_fat_ano:.1f}%)")
        if projecao < kpi_ant_mes["fat"]:
            st.caption(f"⚠️ Tendência: {formata_real(projecao)}")
        else:
            st.caption(f"✅ Projeção: {formata_real(projecao)}")
    with k2:
        st.metric(
            f"Fat. Ano ({ano_atual})",
            formata_real(fat_ano_atual),
            f"{delta_ytd:.1f}% vs {ano_atual - 1}",
        )
        st.caption(f"Ano Passado: {formata_real(fat_ano_ant_ytd)}")
    with k3:
        st.metric(
            "Positivação",
            f"{kpi_atual['pos']}",
            f"{delta_pos:.1f}% vs {mes_nomes[(mes_atual - 2) % 12 + 1]}",
        )
        st.caption(f"Mês ant: {kpi_ant_mes['pos']} | Ano ant: {kpi_ano_ant_mes['pos']} ({delta_pos_ano:.1f}%)")
    with k4:
        st.metric(
            "Mix Produtos",
            f"{kpi_atual['mix']}",
            f"{delta_mix:.1f}% vs {mes_nomes[(mes_atual - 2) % 12 + 1]}",
        )
        st.caption(f"Mês ant: {kpi_ant_mes['mix']} | Ano ant: {kpi_ano_ant_mes['mix']} ({delta_mix_ano:.1f}%)")
    with k5:
        st.metric(
            "Ticket Médio",
            formata_real(ticket_atual),
            f"{delta_tkt:.1f}% vs {mes_nomes[(mes_atual - 2) % 12 + 1]}",
        )
        st.caption(f"Mês ant: {formata_real(ticket_ant)} | Ano ant: {formata_real(ticket_ano_ant_mes)} ({delta_tkt_ano:.1f}%)")
