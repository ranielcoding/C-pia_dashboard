import json
import os

import yaml
from yaml.loader import SafeLoader


def load_app_config():
    config_path = os.getenv("DASHBOARD_CONFIG_PATH", "config.yaml")
    config = {}

    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as file:
            config = yaml.load(file, Loader=SafeLoader) or {}

    credentials_from_env = os.getenv("DASHBOARD_CREDENTIALS_JSON")
    if credentials_from_env:
        try:
            credentials_json = json.loads(credentials_from_env)
        except json.JSONDecodeError as exc:
            raise ValueError(f"DASHBOARD_CREDENTIALS_JSON inválido: {exc}") from exc

        config.setdefault("credentials", {})
        config["credentials"].setdefault("usernames", {})
        config["credentials"]["usernames"].update(
            credentials_json.get("credentials", {}).get("usernames", {})
        )

    config.setdefault("cookie", {})
    config["cookie"]["name"] = os.getenv(
        "DASHBOARD_COOKIE_NAME",
        config["cookie"].get("name", "cookie_relatorios_vendas"),
    )
    config["cookie"]["key"] = os.getenv(
        "DASHBOARD_COOKIE_KEY",
        config["cookie"].get("key", ""),
    )
    config["cookie"]["expiry_days"] = int(
        os.getenv("DASHBOARD_COOKIE_EXPIRY_DAYS", config["cookie"].get("expiry_days", 1))
    )

    return config
