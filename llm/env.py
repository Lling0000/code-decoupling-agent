from __future__ import annotations

import os
from functools import lru_cache

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


@lru_cache(maxsize=64)
def resolve_env(name: str) -> tuple[str | None, str | None]:
    process_value = os.getenv(name)
    if process_value:
        return process_value, "process"

    if winreg is None:
        return None, None

    user_value = _read_windows_env(winreg.HKEY_CURRENT_USER, r"Environment", name)
    if user_value:
        return user_value, "user"

    machine_value = _read_windows_env(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        name,
    )
    if machine_value:
        return machine_value, "machine"

    return None, None


def env_value(name: str, default: str | None = None) -> str | None:
    value, _ = resolve_env(name)
    return value if value is not None else default


def env_value_with_aliases(
    primary_name: str,
    aliases: list[str] | tuple[str, ...],
    default: str | None = None,
) -> tuple[str | None, str | None]:
    primary_value, primary_source = resolve_env(primary_name)
    if primary_value is not None:
        return primary_value, primary_name

    for alias in aliases:
        alias_value, alias_source = resolve_env(alias)
        if alias_value is not None:
            return alias_value, alias

    return default, None


def env_flag(name: str, default: bool = False) -> bool:
    value = env_value(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def clear_env_cache() -> None:
    resolve_env.cache_clear()


def _read_windows_env(root: object, path: str, name: str) -> str | None:
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None
