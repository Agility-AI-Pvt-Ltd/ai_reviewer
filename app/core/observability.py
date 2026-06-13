import os
from collections.abc import Callable
from typing import Any

try:
    from langsmith import traceable as traceable
    from langsmith.run_helpers import get_current_run_tree
    from langsmith.wrappers import wrap_openai
except ImportError:  # pragma: no cover - langsmith is a runtime dependency.
    get_current_run_tree = None
    wrap_openai = None

    def traceable(*args: Any, **_: Any) -> Callable:
        if args and callable(args[0]):
            return args[0]

        def decorator(func: Callable) -> Callable:
            return func

        return decorator


def _clean_env_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip('"').strip("'")
    return text or None


def configure_langsmith(settings: Any) -> None:
    """Bridge values loaded from .env into the env vars LangSmith reads."""
    tracing = bool(getattr(settings, "langsmith_tracing", False))
    tracing_value = "true" if tracing else "false"

    os.environ.setdefault("LANGSMITH_TRACING", tracing_value)
    os.environ.setdefault("LANGSMITH_TRACING_V2", tracing_value)
    os.environ.setdefault("LANGCHAIN_TRACING_V2", tracing_value)

    env_mappings = {
        "LANGSMITH_ENDPOINT": getattr(settings, "langsmith_endpoint", None),
        "LANGSMITH_API_KEY": getattr(settings, "langsmith_api_key", None),
        "LANGSMITH_PROJECT": getattr(settings, "langsmith_project", None),
    }
    for key, value in env_mappings.items():
        if cleaned := _clean_env_value(value):
            os.environ.setdefault(key, cleaned)


def add_trace_metadata(metadata: dict[str, Any]) -> None:
    if get_current_run_tree is None:
        return
    run_tree = get_current_run_tree()
    if run_tree is not None:
        run_tree.add_metadata(metadata)


def wrap_openai_client(client: Any) -> Any:
    if wrap_openai is None:
        return client
    return wrap_openai(client)
