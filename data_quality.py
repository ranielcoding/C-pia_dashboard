lazy import pandas as pd


def summarize_data_quality(df, required_columns=None):
    if df is None:
        return {
            "status": "warning",
            "rows": 0,
            "missing_columns": [],
            "missing_values": {},
            "message": "A base chegou nula ao processamento.",
        }

    required_columns = required_columns or []
    missing_columns = [column for column in required_columns if column not in df.columns]
    missing_values = {
        column: int(df[column].isna().sum())
        for column in df.columns
        if column in df.columns and df.empty is False and df[column].isna().sum() > 0
    }

    if df.empty:
        status = "warning"
        message = "A base está vazia após o processamento."
    elif missing_columns:
        status = "warning"
        message = "Há colunas obrigatórias ausentes na base."
    else:
        status = "healthy"
        message = "Dados consistentes e prontos para uso."

    return {
        "status": status,
        "rows": int(len(df)),
        "missing_columns": missing_columns,
        "missing_values": missing_values,
        "message": message,
    }


def validate_required_columns(df, required_columns):
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {missing}")
    return df


def clean_numeric_columns(df, columns, fill_value=0):
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(fill_value)
    return result


def normalize_date_columns(df, columns):
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_datetime(result[column], errors="coerce")
    return result


def prepare_dataframe(df, required_columns=None, numeric_columns=None, date_columns=None):
    result = df.copy()

    if required_columns:
        result = validate_required_columns(result, required_columns)

    if date_columns:
        result = normalize_date_columns(result, date_columns)

    if numeric_columns:
        result = clean_numeric_columns(result, numeric_columns)

    return result
