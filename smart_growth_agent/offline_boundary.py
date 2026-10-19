"""Process-wide HTTP transport guard for the explicit offline launcher."""

import httpx

_installed = False


def install():
    global _installed
    if _installed:
        return
    sync = httpx.HTTPTransport.handle_request
    asynchronous = httpx.AsyncHTTPTransport.handle_async_request

    def allowed(request):
        if request.url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise RuntimeError("offline_external_http_forbidden")

    def handle(self, request):
        allowed(request)
        return sync(self, request)

    async def handle_async(self, request):
        allowed(request)
        return await asynchronous(self, request)

    httpx.HTTPTransport.handle_request = handle
    httpx.AsyncHTTPTransport.handle_async_request = handle_async
    # Also reject provider transports addressed through a loopback proxy. This is
    # before budget reservation and covers managed routes and connection tests.
    from smart_growth_agent.llm.openai_compatible import OpenAICompatibleGateway

    async def reject_provider(*args, **kwargs):
        raise RuntimeError("offline_model_transport_forbidden")

    OpenAICompatibleGateway._request_and_parse = reject_provider
    _installed = True
