from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "default_config.json"
USER_CONFIG_PATH = CONFIG_DIR / "user_config.json"


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_default_config() -> Dict[str, Any]:
    return _read_json(DEFAULT_CONFIG_PATH)


def load_user_config() -> Dict[str, Any]:
    if USER_CONFIG_PATH.exists():
        return _read_json(USER_CONFIG_PATH)
    return load_default_config()


def save_user_config(config: Dict[str, Any]) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with USER_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return USER_CONFIG_PATH


def load_config_from_bytes(raw: bytes) -> Dict[str, Any]:
    return json.loads(raw.decode("utf-8"))


def config_to_bytes(config: Dict[str, Any]) -> bytes:
    return json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")


def deep_update(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_update(out[key], value)
        else:
            out[key] = value
    return out
