"""Application settings loaded from .env (see .env.example)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_or_create_secret() -> str:
    """Return SECRET_KEY from env, or generate + persist one (never committed)."""
    existing = os.getenv("SECRET_KEY", "").strip()
    if existing:
        return existing
    key_file = os.getenv("SECRET_KEY_FILE", ".secret_key")
    if os.path.exists(key_file):
        with open(key_file, encoding="utf-8") as f:
            saved = f.read().strip()
            if saved:
                return saved
    generated = secrets.token_hex(32)
    try:
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(generated)
    except OSError:
        pass
    return generated


def _get_or_create_mobile_token() -> str:
    token_file = os.getenv("MOBILE_TOKEN_FILE", "mobile_token.txt")
    if os.path.exists(token_file):
        with open(token_file, encoding="utf-8") as f:
            saved = f.read().strip()
            if saved:
                return saved
    import uuid

    token = str(uuid.uuid4())
    try:
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(token)
    except OSError:
        pass
    return token


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("PORT", 20042))
    # Back-compat: original app.py honoured SERVER_PORT; keep accepting it.
    password: str = field(default_factory=lambda: os.getenv("PASSWORD", "passw"))
    secret_key: str = field(default_factory=_get_or_create_secret)
    mobile_token: str = field(default_factory=_get_or_create_mobile_token)
    upload_dir: str = field(default_factory=lambda: os.getenv("UPLOAD_DIR", "airdrop_files"))
    tmp_dir: str = field(default_factory=lambda: os.getenv("TMP_DIR", "airdrop_tmp"))
    public_dir: str = field(default_factory=lambda: os.getenv("PUBLIC_DIR", "public_uploads"))
    max_file_size: int = field(
        default_factory=lambda: _int("MAX_FILE_SIZE_GB", 5) * 1024**3
    )
    max_multi_folder_total: int = field(
        default_factory=lambda: _int("MAX_MULTI_FOLDER_TOTAL_GB", 1) * 1024**3
    )
    rate_limit_window: int = field(
        default_factory=lambda: _int("RATE_LIMIT_WINDOW_SECONDS", 3600)
    )
    rate_limit_max_uploads: int = field(
        default_factory=lambda: _int("RATE_LIMIT_MAX_UPLOADS", 30)
    )
    # Bandwidth policy (sliding windows; see storage.bw_status):
    # soft per-IP bytes/window and folder touches/window trigger throttling.
    # Speed starts at THROTTLE_MAX_MBPS past the soft cap and drops
    # BW_TIER_MBPS every BW_TIER_GB down to THROTTLE_MIN_MBPS.
    # Logged-in (private) sessions are exempt from throttling.
    bw_window_seconds: int = field(default_factory=lambda: _int("BW_WINDOW_SECONDS", 600))
    bw_ip_soft_bytes: int = field(
        default_factory=lambda: _int("BW_IP_SOFT_MB", 100) * 1024**2
    )
    bw_folder_hard_bytes: int = field(
        default_factory=lambda: _int("BW_FOLDER_HARD_GB", 5) * 1024**3
    )
    bw_folders_per_window: int = field(
        default_factory=lambda: _int("BW_FOLDERS_PER_WINDOW", _int("BW_FOLDERS_PER_MIN", 10))
    )
    bw_tier_gb: int = field(default_factory=lambda: _int("BW_TIER_GB", 1))
    bw_tier_mbps: int = field(default_factory=lambda: _int("BW_TIER_MBPS", 10))
    throttle_max_mbps: int = field(default_factory=lambda: _int("THROTTLE_MAX_MBPS", 90))
    throttle_min_mbps: int = field(default_factory=lambda: _int("THROTTLE_MIN_MBPS", 40))

    def throttle_bps(self, mbps: int) -> float:
        return mbps * 1_000_000 / 8

    def __post_init__(self) -> None:
        # SERVER_PORT overrides PORT when set (legacy env name).
        if os.getenv("SERVER_PORT"):
            try:
                self.port = int(os.getenv("SERVER_PORT", str(self.port)))
            except ValueError:
                pass
        for d in (self.upload_dir, self.tmp_dir, self.public_dir):
            os.makedirs(d, exist_ok=True)


settings = Settings()
