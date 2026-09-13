"""
LLM provider wiring for the Safe Arrival Agent.

We use the OpenAI Agents SDK (Agent / Runner / function_tool / guardrails)
exactly as designed, but point it at Google Gemini instead of OpenAI.

Gemini exposes an OpenAI-compatible Chat Completions endpoint:
    https://generativelanguage.googleapis.com/v1beta/openai/

The Agents SDK lets you supply any `AsyncOpenAI`-compatible client to
`OpenAIChatCompletionsModel`, so no LangChain/LiteLLM/etc. is required --
just the official `openai` client pointed at a different base_url, with a
Gemini API key instead of an OpenAI one.

Reference: https://ai.google.dev/gemini-api/docs/openai
"""
from agents import Model, OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# The Agents SDK's built-in tracing exporter authenticates to OpenAI's
# platform using an OpenAI API key. Since we're not using OpenAI at all,
# tracing must be disabled to avoid it trying (and failing) to export traces.
set_tracing_disabled(True)

_gemini_client: AsyncOpenAI | None = None


def get_gemini_client() -> AsyncOpenAI:
    """Return a singleton AsyncOpenAI client pointed at Gemini's OpenAI-compatible API."""
    global _gemini_client
    if _gemini_client is None:
        if not settings.GEMINI_API_KEY:
            logger.warning(
                "GEMINI_API_KEY is not set. The Safe Arrival Agent will fail when invoked."
            )
        _gemini_client = AsyncOpenAI(
            api_key=settings.GEMINI_API_KEY or "missing-gemini-api-key",
            base_url=settings.GEMINI_BASE_URL,
        )
    return _gemini_client


def get_gemini_model() -> Model:
    """Return an Agents-SDK Model backed by Gemini, for use as an Agent's `model=`."""
    return OpenAIChatCompletionsModel(
        model=settings.GEMINI_MODEL,
        openai_client=get_gemini_client(),
    )
