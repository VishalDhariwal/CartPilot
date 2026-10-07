import pytest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel, Field
from backend.engine.llm import generate_structured, LLMNonRecoverableError, LLMValidationError


class SampleSchema(BaseModel):
    sku: str = Field(description="SKU")
    quantity: int = Field(description="Quantity")


def test_llm_retry_with_error_feedback_success_on_retry():
    """
    Mocks OpenAI failure on attempt 1 with validation error, and success on attempt 2.
    Confirms that the error-feedback prompt is passed to attempt 2.
    """
    attempt_prompts = []

    # Mock OpenAI client
    mock_client = MagicMock()
    
    def side_effect_parse(model, messages, response_format, temperature):
        user_msg = messages[-1]["content"]
        attempt_prompts.append(user_msg)
        
        # Attempt 1 returns None or invalid
        if len(attempt_prompts) == 1:
            raise ValueError("Missing required field 'quantity'")
        
        # Attempt 2 returns valid object
        mock_res = MagicMock()
        mock_res.choices = [MagicMock(message=MagicMock(parsed=SampleSchema(sku="TEST-SKU", quantity=2)))]
        return mock_res

    mock_client.beta.chat.completions.parse.side_effect = side_effect_parse

    with patch("openai.OpenAI", return_value=mock_client), patch.dict("os.environ", {"OPENAI_API_KEY": "sk-mock-key"}):
        result = generate_structured(
            prompt="Order 2 units of TEST-SKU",
            schema=SampleSchema,
            preferred_provider="openai",
            max_retries=2
        )

        assert result.sku == "TEST-SKU"
        assert result.quantity == 2
        assert len(attempt_prompts) == 2
        # Verify that attempt 2 received error feedback
        assert "[ERROR FEEDBACK FOR RETRY #1]" in attempt_prompts[1]


def test_llm_exhausted_retries_raises_structured_error():
    """
    Mocks persistent failure across all retries and asserts clean exception handling.
    """
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.side_effect = ValueError("Invalid JSON schema syntax")

    with patch("openai.OpenAI", return_value=mock_client), patch.dict("os.environ", {"OPENAI_API_KEY": "sk-mock-key", "GEMINI_API_KEY": ""}):
        with pytest.raises((LLMNonRecoverableError, LLMValidationError)):
            generate_structured(
                prompt="Malformed query",
                schema=SampleSchema,
                preferred_provider="openai",
                max_retries=2
            )
