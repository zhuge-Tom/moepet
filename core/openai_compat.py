"""Small normalization helpers shared by OpenAI-compatible providers."""

from urllib.parse import urlsplit, urlunsplit


def is_local_endpoint(base_url: str) -> bool:
    """Whether an endpoint stays on the user's machine or private loopback."""
    host = (urlsplit(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def chat_completions_url(base_url: str) -> str:
    """Return a chat-completions endpoint without duplicating an explicit path."""
    endpoint = base_url.rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    if endpoint.endswith("/responses"):
        # Moepet sends Chat Completions payloads, not Responses API payloads.
        return endpoint.removesuffix("/responses") + "/chat/completions"
    return f"{endpoint}/chat/completions"


def bearer_headers(api_key: str) -> dict[str, str]:
    """Only send Authorization when a provider actually requires a key."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def model_discovery_urls(base_url: str) -> tuple[str, ...]:
    """Return OpenAI and Ollama model-list endpoints for one provider URL."""
    endpoint = base_url.rstrip("/")
    for suffix in ("/chat/completions", "/responses", "/audio/speech", "/audio/transcriptions"):
        if endpoint.endswith(suffix):
            endpoint = endpoint.removesuffix(suffix)
            break
    openai_url = f"{endpoint}/models"
    parts = urlsplit(endpoint)
    root = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    ollama_url = f"{root}/api/tags" if root else ""
    return tuple(url for url in (openai_url, ollama_url) if url)
