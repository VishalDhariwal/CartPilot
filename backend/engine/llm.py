"""
CartPilot Unified LLM Engine: Dual-Provider (OpenAI & Google Gemini)

Provides seamless multi-provider AI support:
- Primary / Secondary automatic fallback between OpenAI and Gemini.
- Supports structured Pydantic schema generation and text generation.
- Handles rate-limits, missing keys, and network timeouts gracefully.
"""

import os
import json
import re
from typing import Optional, Type, TypeVar, Any
from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))

T = TypeVar("T", bound=BaseModel)

# Preferred Gemini models in priority order
GEMINI_MODELS = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
OPENAI_MODEL = "gpt-4o-mini"


def get_available_providers() -> list[str]:
    """Returns list of configured and available AI providers."""
    providers = []
    if os.getenv("OPENAI_API_KEY"):
        providers.append("openai")
    if os.getenv("GEMINI_API_KEY"):
        providers.append("gemini")
    return providers


def _call_openai_structured(prompt: str, schema: Type[T], system_prompt: Optional[str] = None) -> T:
    """Call OpenAI with beta.chat.completions.parse for strict structured output."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=api_key)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    completion = client.beta.chat.completions.parse(
        model=OPENAI_MODEL,
        messages=messages,
        response_format=schema,
        temperature=0.2
    )
    return completion.choices[0].message.parsed


def _call_gemini_structured(prompt: str, schema: Type[T], system_prompt: Optional[str] = None) -> T:
    """Call Google Gemini with structured JSON output enforced."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"System Instructions:\n{system_prompt}\n\nUser Request:\n{prompt}"

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    instruction = (
        f"{full_prompt}\n\n"
        f"You MUST respond ONLY with valid JSON strictly conforming to this JSON schema:\n"
        f"```json\n{schema_json}\n```\n"
        f"Return ONLY raw JSON with no conversational prefix or markdown tags outside the JSON."
    )

    last_err = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=instruction,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            raw_text = response.text.strip()
            # Clean possible markdown block
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            parsed_dict = json.loads(raw_text)
            return schema.model_validate(parsed_dict)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Gemini generation failed across models {GEMINI_MODELS}: {last_err}")


def generate_structured(
    prompt: str,
    schema: Type[T],
    system_prompt: Optional[str] = None,
    preferred_provider: Optional[str] = None
) -> T:
    """
    Generate structured Pydantic object with dual OpenAI and Gemini support + automatic failover.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    # Determine order of providers to attempt
    configured_pref = os.getenv("LLM_PROVIDER", "").lower()
    pref = (preferred_provider or configured_pref).lower()

    if pref == "gemini" and gemini_key:
        providers = ["gemini", "openai"] if openai_key else ["gemini"]
    elif pref == "openai" and openai_key:
        providers = ["openai", "gemini"] if gemini_key else ["openai"]
    else:
        # Default priority: OpenAI first if available, otherwise Gemini
        if openai_key and gemini_key:
            providers = ["openai", "gemini"]
        elif openai_key:
            providers = ["openai"]
        elif gemini_key:
            providers = ["gemini"]
        else:
            raise ValueError("Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured in .env.")

    errors = []
    for provider in providers:
        try:
            if provider == "openai":
                return _call_openai_structured(prompt, schema, system_prompt)
            elif provider == "gemini":
                return _call_gemini_structured(prompt, schema, system_prompt)
        except Exception as e:
            errors.append(f"[{provider}] {str(e)}")
            print(f"⚠️ Provider '{provider}' failed: {e}. Falling back to next available provider...")

    raise RuntimeError(f"All configured LLM providers failed: {'; '.join(errors)}")


def generate_text(
    prompt: str,
    system_prompt: Optional[str] = None,
    preferred_provider: Optional[str] = None
) -> str:
    """
    Generate natural language text with dual OpenAI and Gemini support + automatic failover.
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    configured_pref = os.getenv("LLM_PROVIDER", "").lower()
    pref = (preferred_provider or configured_pref).lower()

    if pref == "gemini" and gemini_key:
        providers = ["gemini", "openai"] if openai_key else ["gemini"]
    else:
        if openai_key and gemini_key:
            providers = ["openai", "gemini"]
        elif openai_key:
            providers = ["openai"]
        elif gemini_key:
            providers = ["gemini"]
        else:
            raise ValueError("Neither OPENAI_API_KEY nor GEMINI_API_KEY is configured in .env.")

    errors = []
    for provider in providers:
        try:
            if provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                msgs = []
                if system_prompt:
                    msgs.append({"role": "system", "content": system_prompt})
                msgs.append({"role": "user", "content": prompt})
                res = client.chat.completions.create(model=OPENAI_MODEL, messages=msgs, temperature=0.3)
                return res.choices[0].message.content or ""
            elif provider == "gemini":
                from google import genai
                client = genai.Client(api_key=gemini_key)
                full = prompt
                if system_prompt:
                    full = f"{system_prompt}\n\n{prompt}"
                for m in GEMINI_MODELS:
                    try:
                        res = client.models.generate_content(model=m, contents=full)
                        return res.text or ""
                    except Exception:
                        continue
        except Exception as e:
            errors.append(f"[{provider}] {str(e)}")
            continue

    raise RuntimeError(f"All LLM text providers failed: {'; '.join(errors)}")
