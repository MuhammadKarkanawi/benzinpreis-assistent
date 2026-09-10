import httpx
import pytest

from app.ai.client import AIClient, AIInvalidResponseError, AITimeoutError, AIUnavailableError
from app.config import Settings


def make_settings(**overrides) -> Settings:
    defaults = dict(
        ai_base_url="http://mock/v1",
        ai_model="test-model",
        ai_api_key="x",
        ai_timeout_seconds=1.0,
        ai_max_retries=0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_chat_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "Alles gut."}}]})

    client = AIClient(make_settings(), transport=httpx.MockTransport(handler))
    result = await client.chat([{"role": "user", "content": "Hallo"}])
    assert result == "Alles gut."


@pytest.mark.asyncio
async def test_chat_raises_invalid_response_on_malformed_json_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = AIClient(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AIInvalidResponseError):
        await client.chat([{"role": "user", "content": "Hallo"}])


@pytest.mark.asyncio
async def test_chat_raises_invalid_response_on_4xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    client = AIClient(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AIInvalidResponseError):
        await client.chat([{"role": "user", "content": "Hallo"}])


@pytest.mark.asyncio
async def test_chat_raises_unavailable_on_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    client = AIClient(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AIUnavailableError):
        await client.chat([{"role": "user", "content": "Hallo"}])


@pytest.mark.asyncio
async def test_chat_raises_timeout_on_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timed out", request=request)

    client = AIClient(make_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(AITimeoutError):
        await client.chat([{"role": "user", "content": "Hallo"}])


@pytest.mark.asyncio
async def test_chat_raises_unavailable_after_retries_on_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    client = AIClient(make_settings(ai_max_retries=1), transport=httpx.MockTransport(handler))
    with pytest.raises(AIUnavailableError):
        await client.chat([{"role": "user", "content": "Hallo"}])
