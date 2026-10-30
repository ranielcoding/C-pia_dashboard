import numpy as np
import pandas as pd
import streamlit as st
# Práticas modernas Python 3.15.2 (PEP 810) - Lazy Imports para bibliotecas gráficas e de ML
lazy import seaborn as sns
lazy import matplotlib.pyplot as plt
lazy from sklearn.linear_model import LinearRegression


@st.cache_data(show_spinner=False)
def build_correlation_matrix(df, numeric_columns):
    subset = df.loc[:, numeric_columns].copy()
    return subset.corr(method="pearson")


def build_correlation_heatmap(df, numeric_columns, title="Matriz de correlação"):
    corr = build_correlation_matrix(df, numeric_columns)
    plt.figure(figsize=(8, 6))
    sns.heatmap(corr, annot=True, cmap="coolwarm", fmt=".2f")
    plt.title(title)
    plt.tight_layout()
    return corr


@st.cache_data(show_spinner=False)
def aggregate_by_period(df, date_col, value_col, group_col=None, freq="M"):
    result = df.copy()
    result[date_col] = pd.to_datetime(result[date_col], errors="coerce")
    result = result.dropna(subset=[date_col, value_col])

    period_freq = "M" if freq in ["M", "ME"] else freq
    period_key = "_period"
    result[period_key] = result[date_col].dt.to_period(period_freq).astype(str)

    if group_col and group_col in result.columns:
        grouped = result.groupby([group_col, period_key], as_index=False)[value_col].sum()
        grouped = grouped.rename(columns={period_key: date_col})
        return grouped.sort_values([group_col, date_col]).reset_index(drop=True)

    grouped = result.groupby(period_key, as_index=False)[value_col].sum()
    grouped = grouped.rename(columns={period_key: date_col})
    return grouped.sort_values(date_col).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def forecast_sales(df, date_col="data", value_col="valor_mercadoria", periods=30):
    series = df[[date_col, value_col]].copy()
    series[date_col] = pd.to_datetime(series[date_col], errors="coerce")
    series = series.dropna(subset=[date_col, value_col])
    series = series.groupby(date_col, as_index=False)[value_col].sum().sort_values(date_col)

    if series.empty:
        raise ValueError("DataFrame vazio para previsão.")

    series["day_index"] = np.arange(len(series))

    model = LinearRegression()
    model.fit(series[["day_index"]], series[value_col])

    future_index = np.arange(len(series), len(series) + periods)
    future_features = pd.DataFrame({"day_index": future_index})
    forecast_values = model.predict(future_features)

    forecast_dates = pd.date_range(series[date_col].max() + pd.Timedelta(days=1), periods=periods, freq="D")
    forecast = pd.DataFrame({
        date_col: forecast_dates,
        "valor_previsto": forecast_values,
    })

    return series, forecast


def forecast_sales_quantiles(
    df,
    date_col="data",
    value_col="valor_mercadoria",
    periods=30,
    holiday_dates=None,
):
    """Return daily demand forecasts with ordered P10, P50, and P90 ranges."""
    from modules.statistical_engines import forecast_sales_quantiles as forecast_engine

    return forecast_engine(
        df,
        date_col=date_col,
        value_col=value_col,
        periods=periods,
        holiday_dates=holiday_dates,
    )
