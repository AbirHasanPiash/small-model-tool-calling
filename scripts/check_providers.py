# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "httpx>=0.28,<1",
#     "langfuse>=5.1,<6",
#     "openai>=3.42,<4",
# ]
# ///
"""Check that each free API key works, and that Langfuse records the calls.

Run it with `make keys`, which loads .env first. The same command by hand:
    uv run --env-file .env scripts/check_providers.py
    uv run --env-file .env scripts/check_providers.py --list   # models each key can use

The block at the top is inline script metadata: uv reads it and runs this file
in its own small environment, so the project's dependencies stay untouched.

Providers whose key is empty are skipped. The exit code is 0 only when every
provider that has a key answered.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx
import openai

PROMPT = "Reply with exactly one word: ok"

HINTS = {
    401: "the key is wrong or was revoked; create a new one and paste it again",
    402: "payment required: this model or account has no free quota left",
    403: "access denied; check the key's permissions, or turn off any VPN",
    404: "model not found; run with --list, then set the model in .env",
    429: "rate limit reached; wait a minute (or until the daily reset) and retry",
}


@dataclass(frozen=True)
class Provider:
    name: str
    env: str  # environment variable that holds this provider's key
    url: str  # OpenAI-compatible base URL
    model_env: str  # environment variable that can override the model
    model: str  # model used when model_env is not set


PROVIDERS = (
    Provider(
        "Gemini",
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    ),
    Provider(
        "Anthropic",
        "ANTHROPIC_API_KEY",
        "https://api.anthropic.com/v1/",
        "ANTHROPIC_MODEL",
        "claude-haiku-5-5",
    ),
    Provider(
        "Groq",
        "GROQ_API_KEY",
        "https://api.groq.com/openai/v1",
        "GROQ_MODEL",
        "openai/gpt-oss-20b",
    ),
    Provider(
        "OpenRouter",
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_MODEL",
        "openrouter/free",
    ),
    Provider(
        "Mistral",
        "MISTRAL_API_KEY",
        "https://api.mistral.ai/v1",
        "MISTRAL_MODEL",
        "mistral-small-latest",
    ),
)


def client_class(traced: bool) -> Any:
    """The OpenAI client class; Langfuse's drop-in version when tracing is on."""
    if traced:
        from langfuse.openai import OpenAI  # same API, and every call is sent to Langfuse

        return OpenAI
    return openai.OpenAI


def extra_headers(provider: Provider, key: str) -> dict[str, str]:
    if provider.name == "Anthropic":
        return {"anthropic-version": "2023-06-01", "x-api-key": key}
    return {}


def check_chat(provider: Provider, key: str, traced: bool) -> str:
    client = client_class(traced)(
        api_key=key,
        base_url=provider.url,
        default_headers=extra_headers(provider, key),
        timeout=60,
        max_retries=1,
    )
    model = os.getenv(provider.model_env) or provider.model
    extra = {"name": f"week0 check: {provider.name}"} if traced else {}
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        **extra,
    )
    seconds = time.perf_counter() - start
    reply = (response.choices[0].message.content or "").strip()
    usage = response.usage
    tokens = f"{usage.prompt_tokens} in, {usage.completion_tokens} out" if usage else "no usage"
    return f"{response.model or model} replied {reply[:30]!r} in {seconds:.1f} s ({tokens} tokens)"


def list_models(provider: Provider, key: str) -> list[str]:
    client = openai.OpenAI(
        api_key=key,
        base_url=provider.url,
        default_headers=extra_headers(provider, key),
        timeout=60,
        max_retries=1,
    )
    ids = sorted(model.id for model in client.models.list())
    if provider.name == "OpenRouter":  # 400+ models; keep only the free ones
        ids = [model_id for model_id in ids if model_id.endswith(":free")]
    return ids


def check_hugging_face(key: str) -> str:
    """Free accounts get no inference credits, so check the token itself instead."""
    response = httpx.get(
        "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    response.raise_for_status()
    user = response.json()
    role = user.get("auth", {}).get("accessToken", {}).get("role", "unknown")
    return f"token works for user {user.get('name')} (role: {role})"


def check_langfuse() -> str:
    from langfuse import get_client

    get_client().auth_check()  # raises if the keys or the region URL are wrong
    base = (
        os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"
    )
    return f"keys accepted by {base}"


def explain(error: Exception) -> str:
    if isinstance(error, openai.APIStatusError | httpx.HTTPStatusError):
        status = (
            error.status_code
            if isinstance(error, openai.APIStatusError)
            else error.response.status_code
        )
        return f"HTTP {status}: {HINTS.get(status, str(error)[:160])}"
    if isinstance(error, openai.APIConnectionError | httpx.TransportError):
        return "could not connect; check your internet connection"
    return f"{type(error).__name__}: {str(error)[:160]}"


def report(label: str, ok: bool | None, message: str) -> None:
    mark = {True: "[ ok ]", False: "[FAIL]", None: "[skip]"}[ok]
    print(f"  {mark} {label:<13} {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list the models each key can use")
    args = parser.parse_args()

    traced = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
    failures = 0

    if args.list:
        for provider in PROVIDERS:
            key = os.getenv(provider.env)
            if not key:
                continue
            try:
                print(f"\n{provider.name}:")
                for model_id in list_models(provider, key):
                    print(f"  {model_id}")
            except Exception as error:
                failures += 1
                print(f"  could not list models: {explain(error)}")
        return 1 if failures else 0

    print(f"Checking keys. Langfuse tracing is {'on' if traced else 'off (no Langfuse keys)'}.\n")
    if traced:
        try:
            report("Langfuse", True, check_langfuse())
        except Exception as error:
            failures += 1
            report("Langfuse", False, explain(error))

    for provider in PROVIDERS:
        key = os.getenv(provider.env)
        if not key:
            report(provider.name, None, f"{provider.env} is empty in .env")
            continue
        try:
            report(provider.name, True, check_chat(provider, key, traced))
        except Exception as error:
            failures += 1
            report(provider.name, False, explain(error))

    hf_key = os.getenv("HF_TOKEN")
    if not hf_key:
        report("Hugging Face", None, "HF_TOKEN is empty in .env")
    else:
        try:
            report("Hugging Face", True, check_hugging_face(hf_key))
        except Exception as error:
            failures += 1
            report("Hugging Face", False, explain(error))

    if traced:
        from langfuse import get_client

        get_client().flush()  # send buffered traces before the script exits
        print("\nTraces sent. In Langfuse, open your project and then Tracing.")

    print(f"\n{'All configured providers answered.' if not failures else f'{failures} failed.'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
