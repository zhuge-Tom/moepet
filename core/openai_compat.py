"""Small normalization helpers shared by OpenAI-compatible providers."""


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
