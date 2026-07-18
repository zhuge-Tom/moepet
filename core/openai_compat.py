"""Small normalization helpers shared by OpenAI-compatible providers."""


def chat_completions_url(base_url: str) -> str:
    """Return a chat-completions endpoint without duplicating an explicit path."""
    endpoint = base_url.rstrip("/")
    if endpoint.endswith("/chat/completions") or endpoint.endswith("/responses"):
        return endpoint
    return f"{endpoint}/chat/completions"


def bearer_headers(api_key: str) -> dict[str, str]:
    """Only send Authorization when a provider actually requires a key."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}
