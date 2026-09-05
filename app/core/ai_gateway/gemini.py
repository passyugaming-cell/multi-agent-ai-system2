import asyncio
import json
import logging
from decimal import Decimal
from typing import Any
from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import settings
from app.core.ai_gateway.base import AIProvider
from app.core.ai_gateway.schemas import AIRequest, AIResponse
from app.core.ai_gateway.usage import calculate_estimated_cost
from app.core.ai_gateway.exceptions import (
    AIAuthenticationError,
    AIInvalidRequestError,
    AIMalformedResponseError,
    AIProviderUnavailableError,
    AIRateLimitError,
    AITimeoutError,
)

logger = logging.getLogger("ai_gateway.gemini")


class GeminiProvider(AIProvider):
    """Google Gemini AI Provider using Google GenAI SDK."""

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL or "gemini-3.1-flash-lite"
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        if not self._client:
            if not self.api_key:
                raise AIAuthenticationError("GEMINI_API_KEY is not configured.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate(self, request: AIRequest, request_id: str) -> AIResponse:
        client = self._get_client()

        config_args: dict[str, Any] = {
            "system_instruction": request.system_instruction,
        }
        if request.temperature is not None:
            config_args["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            config_args["max_output_tokens"] = request.max_output_tokens

        if request.response_schema is not None:
            config_args["response_mime_type"] = "application/json"
            config_args["response_schema"] = request.response_schema

        config = types.GenerateContentConfig(**config_args)

        prompt_content = f"Context: {json.dumps(request.context)}\nUser Message: {request.user_message}"

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt_content,
                    config=config,
                ),
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise AITimeoutError(f"Gemini API request timed out after {settings.AI_TIMEOUT_SECONDS}s")
        except APIError as e:
            code = getattr(e, "code", None)
            msg = str(e)
            if code == 401 or "API key" in msg:
                raise AIAuthenticationError(f"Gemini authentication failed: {msg}")
            elif code == 429 or "RESOURCE_EXHAUSTED" in msg:
                raise AIRateLimitError(f"Gemini rate limit / quota exceeded: {msg}")
            elif code == 400 or "INVALID_ARGUMENT" in msg:
                raise AIInvalidRequestError(f"Invalid request to Gemini API: {msg}")
            else:
                raise AIProviderUnavailableError(f"Gemini API error: {msg}")
        except Exception as e:
            raise AIProviderUnavailableError(f"Unexpected error communicating with Gemini API: {e}")

        text = response.text or ""
        input_tokens = None
        output_tokens = None
        total_tokens = None
        usage_status = "UNKNOWN"

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            input_tokens = getattr(meta, "prompt_token_count", None)
            output_tokens = getattr(meta, "candidates_token_count", None)
            total_tokens = getattr(meta, "total_token_count", None)
            if total_tokens is not None:
                usage_status = "EXACT"

        cost = calculate_estimated_cost(input_tokens, output_tokens)

        structured_output = None
        if request.response_schema is not None and text:
            try:
                parsed_json = json.loads(text)
                structured_output = request.response_schema.model_validate(parsed_json)
            except Exception as e:
                logger.warning(f"Failed to parse structured response from Gemini: {e}")
                raise AIMalformedResponseError(f"Malformed structured response from Gemini: {e}")

        finish_reason = None
        if response.candidates and len(response.candidates) > 0:
            finish_reason = str(response.candidates[0].finish_reason)

        return AIResponse(
            text=text,
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=cost,
            finish_reason=finish_reason,
            request_id=request_id,
            structured_output=structured_output,
            usage_status=usage_status,
        )
