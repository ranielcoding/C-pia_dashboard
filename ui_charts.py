def top_products_chart_spec(products, values, display_values, metric):
    metric_label = "Valor" if metric == "Valor" else "Quantidade"
    tooltip_metric = "R$ {c}" if metric == "Valor" else "{c}"
    return {
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow"},
            "formatter": f"{{b}}<br/>{metric_label}: {tooltip_metric}",
        },
        "grid": {"left": 125, "right": 40, "top": 15, "bottom": 20},
        "xAxis": {"type": "value", "show": False},
        "yAxis": {
            "type": "category",
            "data": products,
            "axisLabel": {"fontSize": 10, "width": 115, "overflow": "truncate"},
        },
        "series": [
            {
                "name": metric_label,
                "type": "bar",
                "data": [
                    {
                        "value": value,
                        "label": {"show": True, "formatter": display_value},
                    }
                    for value, display_value in zip(values, display_values)
                ],
                "itemStyle": {"color": "#00BFFF"},
                "label": {"show": True, "position": "right"},
            }
        ],
    }
