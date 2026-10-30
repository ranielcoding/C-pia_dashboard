"""Offline statistical engines operating on caller-supplied pandas data.

These functions intentionally have no database, Streamlit, or query-layer
dependencies. Callers own data loading, caching, and UI integration.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
# Lazy imports PEP 810 para runtime Python 3.15.2
lazy from scipy.sparse import csr_matrix
lazy from scipy.signal import savgol_filter
lazy from scipy.stats import chi2_contingency, f_oneway
lazy from sklearn.cluster import KMeans
lazy from sklearn.linear_model import LogisticRegression, QuantileRegressor
lazy from sklearn.metrics import silhouette_score
lazy from sklearn.preprocessing import RobustScaler


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Colunas ausentes: {', '.join(missing)}")


def _resolve_column(frame: pd.DataFrame, preferred: str, aliases=()) -> str:
    """Resolve a preferred column name with case-insensitive known aliases."""
    candidates = [preferred, *aliases]
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    by_casefold = {str(column).casefold(): column for column in frame.columns}
    for candidate in candidates:
        resolved = by_casefold.get(str(candidate).casefold())
        if resolved is not None:
            return resolved
    return preferred


def _empty_forecast(date_col: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            date_col: pd.Series(dtype="datetime64[ns]"),
            "p10": pd.Series(dtype="float64"),
            "p50": pd.Series(dtype="float64"),
            "p90": pd.Series(dtype="float64"),
        }
    )


def _calendar_features(
    dates: pd.Series, trend: np.ndarray, holidays: set[pd.Timestamp]
) -> np.ndarray:
    dates = pd.DatetimeIndex(dates)
    weekday = dates.day_of_week.to_numpy()
    month = dates.month.to_numpy()
    return np.column_stack(
        [
            trend,
            np.sin(2 * np.pi * weekday / 7),
            np.cos(2 * np.pi * weekday / 7),
            np.sin(2 * np.pi * (month - 1) / 12),
            np.cos(2 * np.pi * (month - 1) / 12),
            (weekday < 5).astype(float),
            dates.is_month_end.astype(float),
            np.array([date.normalize() in holidays for date in dates], dtype=float),
        ]
    )


def forecast_sales_quantiles(
    sales: pd.DataFrame,
    date_col: str = "data",
    value_col: str = "valor_mercadoria",
    periods: int = 30,
    holiday_dates=None,
) -> pd.DataFrame:
    """Forecast daily demand with calendar features and P10/P50/P90 quantiles.

    The observed series is made daily (missing dates are treated as zero).
    A robust weekly decomposition supplies a seasonal component and a smooth
    trend to three independent quantile regressors. Holidays are supplied by
    the caller as dates, allowing jurisdiction-specific calendars without
    hidden network or database lookups.
    """
    if periods < 1:
        raise ValueError("periods deve ser maior que zero.")
    if sales is None or sales.empty:
        raise ValueError("DataFrame vazio para previsão.")
    _require_columns(sales, [date_col, value_col])

    observed = sales[[date_col, value_col]].copy()
    observed[date_col] = pd.to_datetime(observed[date_col], errors="coerce").dt.normalize()
    observed[value_col] = pd.to_numeric(observed[value_col], errors="coerce")
    observed = observed.dropna(subset=[date_col, value_col])
    observed = observed[np.isfinite(observed[value_col])]
    if observed.empty:
        raise ValueError("DataFrame vazio para previsão.")

    daily = observed.groupby(date_col)[value_col].sum().sort_index()
    calendar = pd.date_range(daily.index.min().normalize(), daily.index.max().normalize(), freq="D")
    values = daily.reindex(calendar, fill_value=0.0).to_numpy(dtype=float)
    n = len(values)
    if n == 1:
        trend = values.copy()
        seasonal = np.zeros(1, dtype=float)
    else:
        # Robust STL-style weekly decomposition: centered median trend, then
        # median weekday effects. This avoids an optional statsmodels runtime.
        window = min(15, n if n % 2 else n - 1)
        if window < 3:
            trend = pd.Series(values).rolling(3, center=True, min_periods=1).median().to_numpy()
        else:
            # Savitzky-Golay low-pass trend extraction from scipy.signal.
            # At least three points are needed; interpolation handles edges.
            trend = savgol_filter(
                values,
                window_length=window,
                polyorder=min(2, window - 1),
                mode="interp",
            )
        remainder = values - trend
        weekday_ids = calendar.day_of_week.to_numpy()
        weekday_effects = np.array(
            [
                np.median(remainder[weekday_ids == day])
                if np.any(weekday_ids == day)
                else 0.0
                for day in range(7)
            ]
        )
        weekday_effects -= weekday_effects.mean()
        seasonal = weekday_effects[weekday_ids]
        trend = trend + remainder - seasonal

    dates = pd.Series(calendar)
    holiday_dates = [] if holiday_dates is None else holiday_dates
    holidays = {
        pd.Timestamp(date).normalize()
        for date in holiday_dates
        if not pd.isna(pd.Timestamp(date))
    }
    historical_trend = np.arange(n, dtype=float)
    x_train = _calendar_features(dates, historical_trend, holidays)
    # Keep the seasonal component explicit in the model alongside calendar
    # flags; the target retains the original demand scale.
    x_train = np.column_stack([x_train, seasonal])
    y_train = values

    future_dates = pd.date_range(calendar[-1] + pd.Timedelta(days=1), periods=periods, freq="D")
    future_trend = np.arange(n, n + periods, dtype=float)
    future_weekday = future_dates.day_of_week.to_numpy()
    future_seasonal = np.array(
        [
            np.median(
                (values - trend)[calendar.day_of_week.to_numpy() == weekday]
            )
            if np.any(calendar.day_of_week.to_numpy() == weekday)
            else seasonal.mean()
            for weekday in future_weekday
        ]
    )
    x_future = _calendar_features(pd.Series(future_dates), future_trend, holidays)
    x_future = np.column_stack([x_future, future_seasonal])

    predictions = []
    if n < 3 or np.allclose(y_train, y_train[0]):
        predictions = [np.full(periods, max(float(y_train[0]), 0.0)) for _ in (0.1, 0.5, 0.9)]
    else:
        for quantile in (0.1, 0.5, 0.9):
            model = QuantileRegressor(quantile=quantile, alpha=0.01, solver="highs")
            model.fit(x_train, y_train)
            predictions.append(model.predict(x_future))

    quantiles = np.maximum(np.column_stack(predictions), 0.0)
    # Quantile models can cross in finite samples. Sorting enforces the
    # probability-order contract at every forecast horizon.
    quantiles.sort(axis=1)
    return pd.DataFrame(
        {
            date_col: future_dates,
            "p10": quantiles[:, 0],
            "p50": quantiles[:, 1],
            "p90": quantiles[:, 2],
        }
    )


def estimate_month_close(
    sales: pd.DataFrame,
    forecast: pd.DataFrame,
    as_of=None,
    date_col: str = "data",
    value_col: str = "valor_mercadoria",
) -> dict[str, float]:
    """Combine current-month sales with future daily forecast quantiles."""
    _require_columns(sales, [date_col, value_col])
    _require_columns(forecast, [date_col, "p10", "p50", "p90"])

    today = pd.Timestamp.today().normalize() if as_of is None else pd.Timestamp(as_of).normalize()
    month_start = today.replace(day=1)
    month_end = today + pd.offsets.MonthEnd(0)

    observed = sales[[date_col, value_col]].copy()
    observed[date_col] = pd.to_datetime(observed[date_col], errors="coerce").dt.normalize()
    observed[value_col] = pd.to_numeric(observed[value_col], errors="coerce")
    observed = observed.dropna(subset=[date_col, value_col])
    observed = observed[observed[date_col] <= today]
    actual_month = observed[
        (observed[date_col] >= month_start) & (observed[date_col] <= today)
    ]
    actual_total = float(actual_month[value_col].sum())
    last_observed_date = observed[date_col].max()

    projected = forecast[[date_col, "p10", "p50", "p90"]].copy()
    projected[date_col] = pd.to_datetime(projected[date_col], errors="coerce").dt.normalize()
    projected = projected.dropna(subset=[date_col])
    projected = projected[
        (projected[date_col] > last_observed_date)
        & (projected[date_col] <= month_end)
    ]

    return {
        quantile: actual_total + float(projected[quantile].sum())
        for quantile in ["p10", "p50", "p90"]
    }


LOT_RISK_COLUMNS = [
    "lot_id",
    "product_id",
    "expiry_date",
    "probability_expiry_with_stock",
    "expected_remaining_quantity",
    "expected_loss_value",
    "urgency",
]


def simulate_lot_expiry_risk(
    lots: pd.DataFrame,
    daily_sales: pd.DataFrame,
    lot_id_col: str = "lot_id",
    product_col: str = "product_id",
    lot_quantity_col: str = "quantity",
    expiry_col: str = "expiry_date",
    unit_cost_col: str = "unit_cost",
    sales_date_col: str = "date",
    sales_quantity_col: str = "quantity",
    simulations: int = 10_000,
    history_days: int = 90,
    random_state: int = 0,
    as_of=None,
) -> pd.DataFrame:
    """Estimate lot expiry risk by simulating Poisson daily product demand."""
    if simulations < 1 or history_days < 1:
        raise ValueError("simulations e history_days devem ser maiores que zero.")
    if lots is None or lots.empty:
        return pd.DataFrame(columns=LOT_RISK_COLUMNS)
    lot_id_col = _resolve_column(lots, lot_id_col, ("Lote", "lot"))
    product_col = _resolve_column(
        lots, product_col, ("Codigo Produto", "codigo_produto", "id_produto")
    )
    lot_quantity_col = _resolve_column(
        lots, lot_quantity_col, ("Estoque Lote", "estoque_por_lote")
    )
    expiry_col = _resolve_column(lots, expiry_col, ("Validade", "validade"))
    _require_columns(lots, [lot_id_col, product_col, lot_quantity_col, expiry_col])

    work = lots.copy()
    work[expiry_col] = pd.to_datetime(work[expiry_col], errors="coerce")
    work[lot_quantity_col] = pd.to_numeric(work[lot_quantity_col], errors="coerce")
    if unit_cost_col not in work:
        work[unit_cost_col] = 0.0
    work[unit_cost_col] = pd.to_numeric(work[unit_cost_col], errors="coerce").fillna(0.0)
    work = work.dropna(subset=[product_col, lot_quantity_col, expiry_col])
    work = work[work[lot_quantity_col] >= 0]
    if work.empty:
        return pd.DataFrame(columns=LOT_RISK_COLUMNS)

    sales = pd.DataFrame(columns=[product_col, sales_date_col, sales_quantity_col])
    if daily_sales is not None and not daily_sales.empty:
        sales_product_col = _resolve_column(
            daily_sales,
            product_col,
            ("Codigo Produto", "codigo_produto", "id_produto", "product_id"),
        )
        sales_date_col = _resolve_column(
            daily_sales, sales_date_col, ("data", "data_venda", "date")
        )
        sales_quantity_col = _resolve_column(
            daily_sales,
            sales_quantity_col,
            ("quantidade", "quantity_sold", "QtdProcessada_Total"),
        )
        _require_columns(
            daily_sales, [sales_product_col, sales_date_col, sales_quantity_col]
        )
        sales = daily_sales[
            [sales_product_col, sales_date_col, sales_quantity_col]
        ].copy()
        sales = sales.rename(columns={sales_product_col: product_col})
        sales[sales_date_col] = pd.to_datetime(sales[sales_date_col], errors="coerce")
        sales[sales_quantity_col] = pd.to_numeric(sales[sales_quantity_col], errors="coerce")
        sales = sales.dropna(subset=[product_col, sales_date_col, sales_quantity_col])
        sales = sales[sales[sales_quantity_col] >= 0]

    if as_of is None:
        as_of = sales[sales_date_col].max() if not sales.empty else pd.Timestamp.today().normalize()
    as_of = pd.Timestamp(as_of).normalize()
    start = as_of - pd.Timedelta(days=history_days - 1)
    sales = sales[(sales[sales_date_col] >= start) & (sales[sales_date_col] <= as_of)]
    means = {}
    for product, group in sales.groupby(product_col):
        by_day = group.assign(_day=group[sales_date_col].dt.normalize()).groupby("_day")[
            sales_quantity_col
        ].sum()
        means[product] = float(by_day.sum() / history_days)

    rng = np.random.default_rng(random_state)
    paths: dict[tuple[object, int, float], np.ndarray] = {}
    output = []
    for row in work.itertuples(index=False, name=None):
        record = dict(zip(work.columns, row))
        product = record[product_col]
        quantity = float(record[lot_quantity_col])
        cost = float(record[unit_cost_col])
        expiry = pd.Timestamp(record[expiry_col]).normalize()
        days = max(int((expiry - as_of).days), 0)
        mean_demand = max(means.get(product, 0.0), 0.0)
        key = (product, days, mean_demand)
        if days == 0 or quantity == 0:
            remaining = np.full(simulations, quantity, dtype=float)
        else:
            if key not in paths:
                consumption = rng.poisson(mean_demand, size=(simulations, days)).sum(axis=1)
                paths[key] = consumption
            remaining = np.maximum(quantity - paths[key], 0.0)
        probability = float(np.mean(remaining > 0))
        expected_remaining = float(remaining.mean())
        if probability >= 0.75:
            urgency = "Crítico"
        elif probability >= 0.30:
            urgency = "Atenção"
        else:
            urgency = "Seguro"
        output.append(
            {
                "lot_id": record[lot_id_col],
                "product_id": product,
                "expiry_date": expiry,
                "probability_expiry_with_stock": probability,
                "expected_remaining_quantity": expected_remaining,
                "expected_loss_value": expected_remaining * cost,
                "urgency": urgency,
            }
        )
    return pd.DataFrame(output, columns=LOT_RISK_COLUMNS)


RFM_COLUMNS = [
    "customer_id",
    "recency_days",
    "frequency",
    "monetary",
    "product_diversity",
    "cluster",
    "segment",
    "churn_probability",
    "churn_label",
    "churn_drivers",
    "risk_method",
]


def _snapshot_feature_rows(
    transactions: pd.DataFrame,
    customer_col: str,
    date_col: str,
    invoice_col: str,
    value_col: str,
    product_col: str | None,
    cutoff: pd.Timestamp,
):
    """Build leakage-safe historical snapshots with a fully observed 30-day label."""
    features, labels = [], []
    for _, customer in transactions.groupby(customer_col):
        customer = customer.sort_values(date_col)
        dates = pd.DatetimeIndex(customer[date_col].dropna().unique()).normalize().unique()
        if dates.empty:
            continue
        last_snapshot = cutoff - pd.Timedelta(days=30)
        if dates[0] > last_snapshot:
            continue
        snapshots = list(pd.date_range(dates[0], last_snapshot, freq="30D"))
        latest_observed_snapshot = dates[dates <= last_snapshot]
        if len(latest_observed_snapshot):
            snapshots.append(latest_observed_snapshot[-1])

        transaction_dates = customer[date_col].to_numpy(dtype="datetime64[ns]")
        for snapshot in sorted(set(snapshots)):
            snapshot = pd.Timestamp(snapshot)
            right = int(np.searchsorted(transaction_dates, snapshot.to_datetime64(), side="right"))
            future_right = int(
                np.searchsorted(
                    transaction_dates,
                    (snapshot + pd.Timedelta(days=30)).to_datetime64(),
                    side="right",
                )
            )
            window_left = int(
                np.searchsorted(
                    transaction_dates,
                    (snapshot - pd.Timedelta(days=89)).to_datetime64(),
                    side="left",
                )
            )
            prior = customer.iloc[:right]
            future = customer.iloc[right:future_right]
            window = customer.iloc[window_left:right]
            if prior.empty:
                continue
            features.append(
                [
                    float((snapshot - prior[date_col].max().normalize()).days),
                    float(window[invoice_col].nunique()),
                    float(np.log1p(max(window[value_col].sum(), 0.0))),
                    float(window[product_col].nunique()) if product_col else 0.0,
                ]
            )
            labels.append(int(future.empty))
    return np.asarray(features, dtype=float), np.asarray(labels, dtype=int)


def segment_customers_rfm(
    transactions: pd.DataFrame,
    customer_col: str = "customer_id",
    date_col: str = "date",
    invoice_col: str = "invoice_id",
    value_col: str = "net_value",
    product_col: str | None = "product_id",
    as_of=None,
    max_clusters: int = 5,
    random_state: int = 0,
) -> pd.DataFrame:
    """Aggregate customer RFM/mix, segment customers, and estimate 30-day churn.

    Churn labels are learned from historical transaction snapshots when enough
    data contains both outcomes. Sparse histories fall back to a bounded
    recency-vs-customer-cadence score rather than failing or inventing labels.
    """
    if transactions is None or transactions.empty:
        return pd.DataFrame(columns=RFM_COLUMNS)
    required = [customer_col, date_col, invoice_col, value_col]
    if product_col:
        required.append(product_col)
    _require_columns(transactions, required)
    data = transactions[required].copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=[customer_col, date_col, value_col, invoice_col])
    if data.empty:
        return pd.DataFrame(columns=RFM_COLUMNS)
    data[date_col] = data[date_col].dt.normalize()
    if as_of is None:
        as_of = data[date_col].max()
    as_of = pd.Timestamp(as_of).normalize()

    records = []
    customer_groups = list(data.groupby(customer_col, sort=False))
    for customer_id, group in customer_groups:
        last_date = group[date_col].max()
        records.append(
            {
                "customer_id": customer_id,
                "recency_days": max(int((as_of - last_date).days), 0),
                "frequency": int(group[invoice_col].nunique()),
                "monetary": float(group[value_col].sum()),
                "product_diversity": int(group[product_col].nunique()) if product_col else 0,
            }
        )
    result = pd.DataFrame(records)

    numeric_columns = ["recency_days", "frequency", "monetary", "product_diversity"]
    cluster_count = min(max(int(max_clusters), 1), len(result))
    result["cluster"] = 0
    if len(result) >= 3 and cluster_count >= 2:
        scaled = RobustScaler().fit_transform(result[numeric_columns])
        best_k, best_score = 2, -math.inf
        for candidate in range(2, min(cluster_count, len(result) - 1) + 1):
            try:
                labels = KMeans(
                    n_clusters=candidate, random_state=random_state, n_init=10
                ).fit_predict(scaled)
                if 1 < len(np.unique(labels)) < len(result):
                    score = silhouette_score(
                        scaled,
                        labels,
                        sample_size=min(5_000, len(result)),
                        random_state=random_state,
                    )
                    if score > best_score:
                        best_k, best_score = candidate, score
            except (ValueError, FloatingPointError):
                continue
        if best_score > -math.inf:
            result["cluster"] = KMeans(
                n_clusters=best_k, random_state=random_state, n_init=10
            ).fit_predict(scaled)

    profiles = result.groupby("cluster")[numeric_columns].mean()
    cluster_order = profiles.sort_values(
        ["recency_days", "frequency", "monetary"],
        ascending=[True, False, False],
    ).index.tolist()
    if len(cluster_order) == 1:
        names = {cluster_order[0]: "Fiéis"}
    else:
        names = {}
        for rank, cluster in enumerate(cluster_order):
            profile = profiles.loc[cluster]
            if rank == 0:
                name = "Campeões"
            elif rank == len(cluster_order) - 1:
                name = "Em Risco de Perda"
            elif profile["frequency"] >= profiles["frequency"].median():
                name = "Fiéis"
            else:
                name = "Oportunidades de Mix"
            names[cluster] = name
    result["segment"] = result["cluster"].map(names)

    x_history, y_history = _snapshot_feature_rows(
        data, customer_col, date_col, invoice_col, value_col, product_col, as_of
    )
    churn_model = None
    if len(y_history) >= 6 and len(np.unique(y_history)) == 2:
        churn_model = LogisticRegression(random_state=random_state, max_iter=500)
        churn_model.fit(x_history, y_history)

    risk_method = (
        "Modelo treinado (histórico)"
        if churn_model is not None
        else "Estimativa por recência e frequência"
    )
    probabilities = []
    for record, (customer_id, customer) in zip(records, customer_groups):
        if customer_id != record["customer_id"]:
            raise RuntimeError("A ordenação dos grupos de clientes foi alterada.")
        last_date = customer[date_col].max()
        rolling = customer[customer[date_col] >= as_of - pd.Timedelta(days=89)]
        latest_features = np.asarray(
            [
                [
                    record["recency_days"],
                    float(rolling[invoice_col].nunique()),
                    float(np.log1p(max(rolling[value_col].sum(), 0.0))),
                    float(rolling[product_col].nunique()) if product_col else 0.0,
                ]
            ],
            dtype=float,
        )
        if churn_model is not None:
            probability = float(churn_model.predict_proba(latest_features)[0, 1])
        else:
            gaps = customer[date_col].sort_values().diff().dt.days.dropna()
            cadence = max(float(gaps.median()) if not gaps.empty else 30.0, 30.0)
            spread = max(float(gaps.std()) if len(gaps) > 1 else cadence / 2, 7.0)
            z = (record["recency_days"] - cadence) / spread
            probability = float(1.0 / (1.0 + math.exp(-max(min(z, 30.0), -30.0))))
        probabilities.append(min(max(probability, 0.0), 1.0))
    result["churn_probability"] = probabilities
    result["churn_label"] = np.where(
        result["churn_probability"] >= 0.5, "Alto risco", "Baixo risco"
    )
    result["churn_drivers"] = result.apply(
        lambda row: ", ".join(
            [
                driver
                for driver, condition in (
                    ("recência elevada", row["recency_days"] >= 30),
                    ("frequência baixa", row["frequency"] <= result["frequency"].median()),
                    ("baixo valor", row["monetary"] <= result["monetary"].median()),
                    (
                        "mix limitado",
                        row["product_diversity"] <= result["product_diversity"].median(),
                    ),
                )
                if condition
            ]
        )
        or "sem alerta dominante",
        axis=1,
    )
    result["risk_method"] = risk_method
    return result[RFM_COLUMNS]


ASSOCIATION_COLUMNS = [
    "product",
    "recommended_product",
    "support",
    "confidence",
    "lift",
    "joint_transactions",
]


def market_basket_associations(
    transactions: pd.DataFrame,
    transaction_col: str = "transaction_id",
    product_col: str = "product_id",
    min_support: float = 0.01,
    min_lift: float = 1.2,
) -> pd.DataFrame:
    """Return directed sparse co-occurrence rules with support/confidence/lift."""
    if not 0 <= min_support <= 1:
        raise ValueError("min_support deve estar entre 0 e 1.")
    if transactions is None or transactions.empty:
        return pd.DataFrame(columns=ASSOCIATION_COLUMNS)
    _require_columns(transactions, [transaction_col, product_col])
    data = transactions[[transaction_col, product_col]].dropna().drop_duplicates()
    if data.empty:
        return pd.DataFrame(columns=ASSOCIATION_COLUMNS)

    transaction_ids = pd.Index(data[transaction_col].unique())
    total = len(transaction_ids)
    minimum_joint = max(1, math.ceil(min_support * total))
    item_counts = data.groupby(product_col)[transaction_col].nunique()
    retained_products = item_counts[item_counts >= minimum_joint].index
    data = data[data[product_col].isin(retained_products)]
    products = sorted(data[product_col].unique(), key=str)
    if len(products) < 2:
        return pd.DataFrame(columns=ASSOCIATION_COLUMNS)
    transaction_index = {value: index for index, value in enumerate(transaction_ids)}
    product_index = {value: index for index, value in enumerate(products)}
    rows = data[transaction_col].map(transaction_index).to_numpy()
    cols = data[product_col].map(product_index).to_numpy()
    matrix = csr_matrix(
        (np.ones(len(data), dtype=np.int8), (rows, cols)),
        shape=(len(transaction_ids), len(products)),
        dtype=np.int32,
    )
    cooccurrence = (matrix.T @ matrix).tocoo()
    counts = np.asarray(matrix.sum(axis=0)).ravel()
    rules = []
    for left, right, joint_count in zip(
        cooccurrence.row, cooccurrence.col, cooccurrence.data
    ):
        if left >= right:
            continue
        joint = int(joint_count)
        support = joint / total
        if support < min_support or joint == 0:
            continue
        for source, target in ((left, right), (right, left)):
            confidence = joint / int(counts[source])
            lift = confidence / (int(counts[target]) / total)
            if lift > min_lift:
                rules.append(
                    {
                        "product": products[source],
                        "recommended_product": products[target],
                        "support": support,
                        "confidence": confidence,
                        "lift": lift,
                        "joint_transactions": joint,
                    }
                )
    if not rules:
        return pd.DataFrame(columns=ASSOCIATION_COLUMNS)
    return (
        pd.DataFrame(rules, columns=ASSOCIATION_COLUMNS)
        .sort_values(["product", "lift", "confidence"], ascending=[True, False, False])
        .reset_index(drop=True)
    )


def recommend_products(
    associations: pd.DataFrame, product, top_n: int = 3
) -> pd.DataFrame:
    """Return up to ``top_n`` strongest association recommendations."""
    if top_n < 0:
        raise ValueError("top_n não pode ser negativo.")
    if associations is None or associations.empty or top_n == 0:
        return pd.DataFrame(columns=ASSOCIATION_COLUMNS)
    _require_columns(associations, ASSOCIATION_COLUMNS)
    return (
        associations.loc[associations["product"] == product]
        .sort_values(["confidence", "lift", "support"], ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


CUT_TEST_COLUMNS = ["test", "statistic", "p_value", "significant", "interpretation"]


def diagnose_order_cuts(
    cuts: pd.DataFrame,
    ordered_col: str = "quantity_ordered",
    cut_col: str = "quantity_cut",
    reason_col: str = "reason",
    supplier_col: str = "supplier",
    sector_col: str = "sales_sector",
    alpha: float = 0.05,
    hour_col: str = "hora_digitacao",
) -> dict:
    """Analyze cut rates, including the Portuguese order-loader column names.

    Recognized loader fields include ``quantidade_pedida``,
    ``quantidade_cortada``, ``motivo_falta``, ``Fornecedor``, ``Setor``, and
    ``hora_digitacao``. Explicit column arguments remain supported.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha deve estar entre 0 e 1.")
    empty_records = pd.DataFrame()
    empty_causes = pd.DataFrame(
        columns=["reason_category", "orders", "mean_cut_rate", "total_cut_quantity"]
    )
    empty_tests = pd.DataFrame(columns=CUT_TEST_COLUMNS)
    if cuts is None or cuts.empty:
        if cuts is not None:
            empty_records = cuts.copy()
            empty_records["cut_rate"] = pd.Series(dtype="float64")
            empty_records["reason_category"] = pd.Series(dtype="object")
        return {"records": empty_records, "tests": empty_tests, "causes": empty_causes}
    ordered_col = _resolve_column(
        cuts, ordered_col, ("quantidade_pedida", "quantity_ordered")
    )
    cut_col = _resolve_column(
        cuts, cut_col, ("quantidade_cortada", "quantity_cut")
    )
    reason_col = _resolve_column(cuts, reason_col, ("motivo_falta", "reason"))
    supplier_col = _resolve_column(cuts, supplier_col, ("Fornecedor", "fornecedor"))
    sector_col = _resolve_column(cuts, sector_col, ("Setor", "setor"))
    hour_col = _resolve_column(cuts, hour_col, ("hora_digitacao", "order_hour"))
    _require_columns(cuts, [ordered_col, cut_col])

    records = cuts.copy()
    records[ordered_col] = pd.to_numeric(records[ordered_col], errors="coerce")
    records[cut_col] = pd.to_numeric(records[cut_col], errors="coerce")
    records = records.dropna(subset=[ordered_col, cut_col])
    records = records[records[ordered_col] > 0].copy()
    records["cut_rate"] = records[cut_col] / records[ordered_col]
    if reason_col not in records:
        records[reason_col] = "Não informado"
    records["reason_category"] = (
        records[reason_col].fillna("Não informado").astype(str).str.strip()
    )
    records.loc[records["reason_category"] == "", "reason_category"] = "Não informado"
    if records.empty:
        return {"records": records, "tests": empty_tests, "causes": empty_causes}
    causes = (
        records.groupby("reason_category", as_index=False)
        .agg(
            orders=(cut_col, "size"),
            mean_cut_rate=("cut_rate", "mean"),
            total_cut_quantity=(cut_col, "sum"),
        )
        .sort_values(["total_cut_quantity", "orders"], ascending=False)
        .reset_index(drop=True)
    )

    tests = []
    if supplier_col in records and records["reason_category"].nunique() >= 2:
        table = pd.crosstab(records["reason_category"], records[supplier_col].fillna("Não informado"))
        table = table.loc[table.sum(axis=1) > 0, table.sum(axis=0) > 0]
        if table.shape[0] >= 2 and table.shape[1] >= 2:
            try:
                statistic, p_value, _, _ = chi2_contingency(table)
                tests.append(
                    {
                        "test": "Qui-quadrado motivo × fornecedor",
                        "statistic": float(statistic),
                        "p_value": float(p_value),
                        "significant": bool(p_value < alpha),
                        "interpretation": (
                            "Há associação estatística entre motivo de corte e fornecedor."
                            if p_value < alpha
                            else "Não há evidência estatística de associação entre motivo e fornecedor."
                        ),
                    }
                )
            except ValueError:
                pass

    for dimension, test_name, significant_text, neutral_text in (
        (
            sector_col,
            "ANOVA taxa de corte por setor",
            "A taxa de corte difere significativamente entre setores.",
            "Não há evidência estatística de diferença entre setores.",
        ),
        (
            hour_col,
            "ANOVA taxa de corte por hora de digitação",
            "A taxa de corte difere significativamente por hora de digitação.",
            "Não há evidência estatística de diferença por hora de digitação.",
        ),
    ):
        if dimension not in records:
            continue
        groups = [
            values["cut_rate"].to_numpy(dtype=float)
            for _, values in records.dropna(subset=[dimension]).groupby(dimension)
            if len(values) >= 2
        ]
        if len(groups) >= 2:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                statistic, p_value = f_oneway(*groups)
            if np.isfinite(statistic) and np.isfinite(p_value):
                tests.append(
                    {
                        "test": test_name,
                        "statistic": float(statistic),
                        "p_value": float(p_value),
                        "significant": bool(p_value < alpha),
                        "interpretation": (
                            significant_text if p_value < alpha else neutral_text
                        ),
                    }
                )
    return {
        "records": records.reset_index(drop=True),
        "tests": pd.DataFrame(tests, columns=CUT_TEST_COLUMNS),
        "causes": causes,
    }
