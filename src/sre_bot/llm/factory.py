"""LLM factory for dynamic provider selection based on configuration."""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from sre_copilot.config import LLMProvider, get_settings


class LLMConfigError(Exception):
    """Raised when LLM configuration is invalid or incomplete."""

    pass


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """
    Factory that returns the configured LLM instance.

    The LLM provider is selected based on the LLM_PROVIDER environment variable.
    Supports OpenAI and Anthropic providers.

    Returns:
        BaseChatModel: Configured LangChain chat model instance.

    Raises:
        LLMConfigError: If required API key is not configured.
        LLMConfigError: If unknown provider is specified.

    Example:
        >>> llm = get_llm()
        >>> response = await llm.ainvoke("Hello, world!")
    """
    settings = get_settings()

    match settings.llm_provider:
        case LLMProvider.OPENAI:
            return _create_openai_llm()

        case LLMProvider.ANTHROPIC:
            return _create_anthropic_llm()

        case _:
            raise LLMConfigError(
                f"Unknown LLM provider: {settings.llm_provider}. "
                f"Supported providers: {[p.value for p in LLMProvider]}"
            )


def _create_openai_llm() -> BaseChatModel:
    """Create OpenAI chat model instance."""
    # Lazy import to avoid loading unnecessary dependencies
    from langchain_openai import ChatOpenAI

    settings = get_settings()

    if not settings.openai_api_key:
        raise LLMConfigError(
            "OPENAI_API_KEY environment variable is not set. "
            "Please set it to use OpenAI as LLM provider."
        )

    return ChatOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
    )


def _create_anthropic_llm() -> BaseChatModel:
    """Create Anthropic chat model instance."""
    # Lazy import to avoid loading unnecessary dependencies
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()

    if not settings.anthropic_api_key:
        raise LLMConfigError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Please set it to use Anthropic as LLM provider."
        )

    return ChatAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.anthropic_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout_seconds,
    )


def clear_llm_cache() -> None:
    """
    Clear the LLM cache.

    Useful for testing or when settings change at runtime.
    """
    get_llm.cache_clear()


def get_llm_info() -> dict[str, str]:
    """
    Get information about the currently configured LLM.

    Returns:
        dict with provider and model information.
    """
    settings = get_settings()

    return {
        "provider": settings.llm_provider.value,
        "model": (
            settings.openai_model
            if settings.llm_provider == LLMProvider.OPENAI
            else settings.anthropic_model
        ),
        "temperature": str(settings.llm_temperature),
        "max_tokens": str(settings.llm_max_tokens),
    }
