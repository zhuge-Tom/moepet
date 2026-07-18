"""Pure readiness rules shared by settings dashboards and service pages."""


def has_secret(config, section: str) -> bool:
    return bool(config.get_secret(section) or config.get(section, "api_key", default=""))


def llm_ready(config) -> bool:
    return bool(
        config.get("llm", "base_url", default="")
        and has_secret(config, "llm")
        and config.get("llm", "model", default="")
    )


def tts_ready(config) -> bool:
    if not config.get("tts", "enabled", default=False):
        return False
    if config.get("tts", "provider", default="local") == "local":
        return bool(config.get("tts", "model_path", default=""))
    return bool(
        config.get("tts", "base_url", default="")
        and has_secret(config, "tts")
        and config.get("tts", "model", default="")
        and config.get("tts", "voice", default="")
    )


def asr_ready(config) -> bool:
    if not config.get("asr", "enabled", default=False):
        return False
    if config.get("asr", "provider", default="local") == "local":
        return bool(config.get("asr", "model_path", default=""))
    return bool(
        config.get("asr", "base_url", default="")
        and has_secret(config, "asr")
        and config.get("asr", "model", default="")
    )


def vision_ready(config) -> bool:
    return vision_connection_ready(
        config.get("vision", "base_url", default=""),
        config.get("vision", "model", default=""),
        config.get("vision", "allow_cloud", default=False),
        config.get("vision", "enabled", default=False),
    )


def vision_connection_ready(base_url: str, model: str, allow_cloud: bool,
                            enabled: bool = True) -> bool:
    """Require explicit consent before a non-local vision endpoint is usable."""
    endpoint = base_url.lower()
    local = any(host in endpoint for host in ("localhost", "127.0.0.1", "[::1]"))
    return bool(enabled and base_url and model and (local or allow_cloud))


def observation_ready(config) -> bool:
    return bool(config.get("screen_capture", "auto_observe", default=False) and vision_ready(config))
