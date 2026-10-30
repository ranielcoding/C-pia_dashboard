from __future__ import annotations


# Emprego de frozendict nativo do Python 3.15.2 (PEP 814) para regras imutáveis de acesso
KNOWN_SUPERVISOR_MAPPINGS = frozendict({
    "Carlos-Supervisor": "CARLINHO",
    "Iussef-Supervisor": "IUSSEF",
    "VITOR": "VITOR",
})


def _read_user(credentials, username):
    usernames = credentials.get("credentials", {}).get("usernames", {})
    if username in usernames:
        return usernames[username]

    # Some configs store users directly under top-level keys.
    if isinstance(credentials, dict) and username in credentials:
        return credentials[username]

    raise ValueError(f"Unknown user: {username}")


def _normalized_supervisor_value(username, user_data):
    explicit_mapping = user_data.get("supervisor") or user_data.get("team") or user_data.get("default_supervisor")
    if explicit_mapping:
        return str(explicit_mapping).upper()

    if username in KNOWN_SUPERVISOR_MAPPINGS:
        return KNOWN_SUPERVISOR_MAPPINGS[username]

    name = str(user_data.get("name", username)).strip()
    if not name:
        raise ValueError(f"Missing supervisor mapping for: {username}")

    upper_name = name.upper()
    if upper_name == "CARLOS":
        return "CARLINHO"
    if upper_name == "IUSSEF":
        return "IUSSEF"
    if upper_name == "VITOR":
        return "VITOR"

    raise ValueError(f"Missing supervisor mapping for: {username}")


def resolve_effective_access(credentials, username):
    if not isinstance(credentials, dict) or not isinstance(username, str):
        raise ValueError("Invalid access credentials or username")

    user = _read_user(credentials, username)
    role = str(user.get("role", "")).strip()
    if not role:
        raise ValueError(f"User has no role configured: {username}")

    role_key = role.lower()
    if role_key == "supervisor":
        default_supervisor = _normalized_supervisor_value(username, user)
        return {
            "username": username,
            "role": role,
            "name": user.get("name"),
            "default_filters": {"supervisor": default_supervisor},
            "is_allowed": True,
        }

    if role_key in {"admin", "diretoria", "gerente", "inteligencia", "televendas", "parametrizacao"}:
        return {
            "username": username,
            "role": role,
            "name": user.get("name"),
            "default_filters": {},
            "is_allowed": True,
        }

    raise ValueError(f"User role is not allowed: {role}")
