"""
CartPilot Unified Resilient LLM Engine: Dual-Provider (OpenAI & Google Gemini)

Provides resilient multi-provider AI execution:
- Automatic schema validation & error-feedback retry loop (up to 2 retries per provider).
- Primary / Secondary automatic failover between OpenAI and Gemini.
- Graceful degradation on persistent network or provider outages.
"""

import os
import json
import re
from typing import Optional, Type, TypeVar, Any
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))

T = TypeVar("T", bound=BaseModel)

# Preferred Gemini models in priority order (fastest stable models first)
GEMINI_MODELS = ["gemini-3-flash-preview", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]
OPENAI_MODEL = "gpt-4o-mini"
MAX_STRUCTURED_RETRIES = 1
LLM_CALL_TIMEOUT_SECONDS = 8

_gemini_client = None

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client

def _run_with_timeout(fn, timeout_seconds=LLM_CALL_TIMEOUT_SECONDS):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        return future.result(timeout=timeout_seconds)



class LLMValidationError(Exception):
    """Raised when structured LLM output fails schema validation."""
    pass


class LLMNonRecoverableError(Exception):
    """Raised when all providers and retries have failed to produce valid output."""
    pass


def get_available_providers() -> list[str]:
    """Returns list of configured and available AI providers."""
    providers = []
    if os.getenv("OPENAI_API_KEY"):
        providers.append("openai")
    if os.getenv("GEMINI_API_KEY"):
        providers.append("gemini")
    return providers


def _call_openai_structured(
    prompt: str,
    schema: Type[T],
    system_prompt: Optional[str] = None,
    max_retries: int = MAX_STRUCTURED_RETRIES
) -> T:
    """Call OpenAI with beta.chat.completions.parse and automatic error-feedback retry loop."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=api_key)
    current_prompt = prompt
    last_err = None

    for attempt in range(max_retries + 1):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": current_prompt})

            completion = client.beta.chat.completions.parse(
                model=OPENAI_MODEL,
                messages=messages,
                response_format=schema,
                temperature=0.2
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise LLMValidationError("OpenAI returned null parsed response.")
            return parsed
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                print(f"⚠️ OpenAI structured attempt #{attempt+1} failed: {e}. Retrying with error feedback...")
                current_prompt = (
                    f"{prompt}\n\n"
                    f"[ERROR FEEDBACK FOR RETRY #{attempt+1}]: Your previous response failed schema validation: {str(e)}. "
                    f"Please correct the output and return strictly valid JSON matching the schema."
                )
            else:
                raise LLMValidationError(f"OpenAI structured parsing failed after {max_retries+1} attempts: {last_err}") from last_err


def _call_gemini_structured(
    prompt: str,
    schema: Type[T],
    system_prompt: Optional[str] = None,
    max_retries: int = MAX_STRUCTURED_RETRIES
) -> T:
    """Call Google Gemini with structured JSON output enforced and error-feedback retry loop."""
    from google.genai import types

    client = get_gemini_client()
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    current_prompt = prompt
    last_err = None

    for attempt in range(max_retries + 1):
        full_prompt = current_prompt
        if system_prompt:
            full_prompt = f"System Instructions:\n{system_prompt}\n\nUser Request:\n{current_prompt}"

        instruction = (
            f"{full_prompt}\n\n"
            f"You MUST respond ONLY with valid JSON strictly conforming to this JSON schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Return ONLY raw JSON with no conversational prefix or markdown tags outside the JSON."
        )

        for model_name in GEMINI_MODELS:
            try:
                def _do_call(target_model=model_name):
                    return client.models.generate_content(
                        model=target_model,
                        contents=instruction,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    )
                response = _run_with_timeout(_do_call, timeout_seconds=LLM_CALL_TIMEOUT_SECONDS)
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

        if attempt < max_retries:
            print(f"⚠️ Gemini structured attempt #{attempt+1} failed: {last_err}. Retrying with error feedback...")
            current_prompt = (
                f"{prompt}\n\n"
                f"[ERROR FEEDBACK FOR RETRY #{attempt+1}]: Your previous response failed schema validation: {str(last_err)}. "
                f"Ensure all required fields are present and data types strictly conform to the schema."
            )

    raise LLMValidationError(f"Gemini generation failed across models {GEMINI_MODELS} after {max_retries+1} attempts: {last_err}")


def generate_structured(
    prompt: str,
    schema: Type[T],
    system_prompt: Optional[str] = None,
    preferred_provider: Optional[str] = None,
    max_retries: int = MAX_STRUCTURED_RETRIES
) -> T:
    """
    Generate structured Pydantic object with dual OpenAI and Gemini support + automatic failover and feedback retries.
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
                return _call_openai_structured(prompt, schema, system_prompt, max_retries=max_retries)
            elif provider == "gemini":
                return _call_gemini_structured(prompt, schema, system_prompt, max_retries=max_retries)
        except Exception as e:
            errors.append(f"[{provider}] {str(e)}")
            print(f"⚠️ Provider '{provider}' failed after retries: {e}. Falling back to next available provider...")

    raise LLMNonRecoverableError(f"All configured LLM providers failed: {'; '.join(errors)}")


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
                client = get_gemini_client()
                full = prompt
                if system_prompt:
                    full = f"{system_prompt}\n\n{prompt}"
                for m in GEMINI_MODELS:
                    try:
                        def _do_text_call(target_model=m):
                            return client.models.generate_content(model=target_model, contents=full)
                        res = _run_with_timeout(_do_text_call, timeout_seconds=LLM_CALL_TIMEOUT_SECONDS)
                        if res and res.text:
                            return res.text.strip()
                    except Exception:
                        continue
        except Exception as e:
            errors.append(f"[{provider}] {str(e)}")
            continue

    raise LLMNonRecoverableError(f"All LLM text providers failed: {'; '.join(errors)}")
