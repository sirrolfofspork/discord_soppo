import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError


def _fake_client(*, result=None, side_effect=None):
    create = AsyncMock()
    if side_effect is not None:
        create.side_effect = side_effect
    else:
        create.return_value = result
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )


def _response(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _request():
    return httpx.Request("POST", "http://openai-compatible.test/v1/chat/completions")


class OpenAIClientLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_chat_validates_messages_before_constructing_client(self):
        from openai_client import OpenAIClientError, openai_chat

        with patch("openai_client.AsyncOpenAI") as mock_constructor:
            with self.assertRaises(OpenAIClientError):
                await openai_chat(api_key="key", model="model", messages=[{"role": "bad", "content": "x"}])

        mock_constructor.assert_not_called()

    async def test_openai_chat_closes_client_on_success(self):
        from openai_client import openai_chat

        client = _fake_client(result=_response("  hello  "))
        with patch("openai_client.AsyncOpenAI", return_value=client):
            result = await openai_chat(
                api_key="key",
                model="model",
                messages=[{"role": "user", "content": "hi"}],
            )

        self.assertEqual(result, "hello")
        client.close.assert_awaited_once()

    async def test_openai_chat_closes_client_on_rate_limit(self):
        from openai_client import OpenAIClientError, openai_chat

        request = _request()
        error = RateLimitError(
            "rate limited",
            response=httpx.Response(429, request=request),
            body=None,
        )
        await self._assert_closes_client_on_wrapped_error(error, OpenAIClientError)

    async def test_openai_chat_closes_client_on_api_error(self):
        from openai_client import OpenAIClientError

        error = APIError("api failed", _request(), body=None)
        await self._assert_closes_client_on_wrapped_error(error, OpenAIClientError)

    async def test_openai_chat_closes_client_on_connection_failure(self):
        from openai_client import OpenAIClientError

        error = APIConnectionError(message="connection failed", request=_request())
        await self._assert_closes_client_on_wrapped_error(error, OpenAIClientError)

    async def test_openai_chat_closes_client_on_timeout(self):
        from openai_client import OpenAIClientError

        error = APITimeoutError(request=_request())
        await self._assert_closes_client_on_wrapped_error(error, OpenAIClientError)

    async def test_openai_chat_closes_client_on_cancelled_error(self):
        client = await self._assert_closes_client_on_unwrapped_error(
            asyncio.CancelledError(),
            asyncio.CancelledError,
        )
        client.close.assert_awaited_once()

    async def test_openai_chat_closes_client_on_missing_choices(self):
        from openai_client import OpenAIClientError, openai_chat

        client = _fake_client(result=SimpleNamespace(choices=[]))
        with patch("openai_client.AsyncOpenAI", return_value=client):
            with self.assertRaisesRegex(OpenAIClientError, "no choices"):
                await openai_chat(
                    api_key="key",
                    model="model",
                    messages=[{"role": "user", "content": "hi"}],
                )

        client.close.assert_awaited_once()

    async def test_openai_chat_closes_client_on_empty_content(self):
        from openai_client import OpenAIClientError, openai_chat

        client = _fake_client(result=_response("   "))
        with patch("openai_client.AsyncOpenAI", return_value=client):
            with self.assertRaisesRegex(OpenAIClientError, "empty content"):
                await openai_chat(
                    api_key="key",
                    model="model",
                    messages=[{"role": "user", "content": "hi"}],
                )

        client.close.assert_awaited_once()

    async def _assert_closes_client_on_wrapped_error(self, error, expected_exception):
        client = await self._assert_closes_client_on_unwrapped_error(error, expected_exception)
        client.close.assert_awaited_once()

    async def _assert_closes_client_on_unwrapped_error(self, error, expected_exception):
        from openai_client import openai_chat

        client = _fake_client(side_effect=error)
        with patch("openai_client.AsyncOpenAI", return_value=client):
            with self.assertRaises(expected_exception):
                await openai_chat(
                    api_key="key",
                    model="model",
                    messages=[{"role": "user", "content": "hi"}],
                )
        return client


if __name__ == "__main__":
    unittest.main()
