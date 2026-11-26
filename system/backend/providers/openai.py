"""One-request OpenAI Responses API target adapter (official HTTPS endpoint).

The supplied model is an API routing identifier, NOT verified fingerprint truth.
The user's key is held only in the request-scoped provider and never returned.
No custom endpoint, proxy URL, or redirection is accepted from a caller.
"""
from __future__ import annotations

from typing import Any

import httpx

API_URL = 'https://api.openai.com/v1/responses'


class ProviderRequestError(RuntimeError):
    """Sanitized error without provider exception bodies, headers or credentials."""

    def __init__(self, code: str, *, status_code: int, message: str):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


class OpenAIResponsesProvider:
    """Stateless target queries using the official Responses REST API.

    The caller supplies the same instance for the initial prompt and any
    additional Harness probes. Retries are intentionally disabled (1 request
    per send_prompt) and max_output_tokens limits output cost per request.
    httpx redirects are disabled so credentials never follow a redirect.
    """

    def __init__(self, api_key: str, target_model: str, *,
                 client: httpx.Client | None = None, timeout_seconds: float = 25.0,
                 max_output_tokens: int = 512):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('An API key is required')
        if not isinstance(target_model, str) or not target_model.strip():
            raise ValueError('A target model routing ID is required')
        if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 120:
            raise ValueError('Invalid provider timeout')
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 4096:
            raise ValueError('Invalid max_output_tokens')
        self.target_model = target_model
        self.max_output_tokens = max_output_tokens
        self._api_key = api_key
        self._owns_client = client is None
        # trust_env=False prevents implicit proxy settings from forwarding keys.
        self._client = client if client is not None else httpx.Client(
            timeout=timeout_seconds, follow_redirects=False, trust_env=False,
        )

    def __repr__(self) -> str:
        return f'OpenAIResponsesProvider(target_model={self.target_model!r}, api_key=<redacted>)'

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def send_prompt(self, prompt_text: str) -> str:
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            raise ValueError('A nonempty prompt is required')
        try:
            response = self._client.post(
                API_URL,
                headers={
                    'Authorization': f'Bearer {self._api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': self.target_model,
                    'input': prompt_text,
                    'max_output_tokens': self.max_output_tokens,
                    'store': False,
                },
            )
        except httpx.TimeoutException:
            raise ProviderRequestError(
                'provider_timeout', status_code=504,
                message='The target AI provider request timed out',
            ) from None
        except httpx.RequestError:
            raise ProviderRequestError(
                'provider_connection_failed', status_code=502,
                message='Could not connect to the target AI provider',
            ) from None
        if response.status_code in (401, 403):
            raise ProviderRequestError(
                'provider_credentials_rejected', status_code=502,
                message='The target AI provider rejected the supplied credentials or permissions',
            )
        if response.status_code == 429:
            raise ProviderRequestError(
                'provider_rate_limited', status_code=429,
                message='The target AI provider rate-limited this request',
            )
        if response.status_code in (408, 504):
            raise ProviderRequestError(
                'provider_timeout', status_code=504,
                message='The target AI provider request timed out',
            )
        if response.status_code in (400, 404, 422):
            raise ProviderRequestError(
                'provider_invalid_request', status_code=502,
                message='The provider rejected the model routing ID or prompt request',
            )
        if not 200 <= response.status_code < 300:
            raise ProviderRequestError(
                'provider_failed', status_code=502,
                message='The target AI provider failed to complete the request',
            )
        try:
            data: Any = response.json()
        except (ValueError, TypeError):
            data = None
        if not isinstance(data, dict) or data.get('status') != 'completed':
            # Incomplete / cancelled / malformed results cannot be considered
            # a valid response; never fabricate response text.
            raise ProviderRequestError(
                'provider_incomplete_response', status_code=502,
                message='The target AI provider did not complete a usable response',
            )
        parts: list[str] = []
        for item in data.get('output', []):
            if isinstance(item, dict) and item.get('type') == 'message':
                for content in item.get('content', []):
                    if (isinstance(content, dict) and content.get('type') == 'output_text'
                            and isinstance(content.get('text'), str)):
                        parts.append(content['text'])
        text = '\n'.join(parts).strip()
        if not text:
            raise ProviderRequestError(
                'provider_empty_response', status_code=502,
                message='The target AI provider returned no usable text',
            )
        return text
