"""
Shared HTTP helper: one place for timeouts, retries and error messages,
so every adapter reports failures the same way instead of raising.
"""

import asyncio

import httpx

USER_AGENT = "geo-mcp/1.0 (github.com/fjollei/geo-mcp)"
DEFAULT_TIMEOUT = httpx.Timeout(10, connect=5)
RETRY_STATUS = {429, 502, 503, 504}


class ServiceError(Exception):
    """An upstream API failed; str() is a message fit for the end user."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code

    def to_dict(self) -> dict:
        return {"error": str(self), "status_code": self.status_code}


async def request_json(
    method: str,
    url: str,
    *,
    service: str,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    retry: bool = False,
    **kwargs,
):
    """
    Send a request and return the decoded JSON body.
    With retry=True, a 429/502/503/504 answer is retried once after 2s.
    Raises ServiceError on HTTP errors, timeouts and network failures.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **kwargs.pop("headers", {})}
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        try:
            r = await client.request(method, url, **kwargs)
            if retry and r.status_code in RETRY_STATUS:
                await asyncio.sleep(2)
                r = await client.request(method, url, **kwargs)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            raise ServiceError(
                f"{service} request failed with HTTP {exc.response.status_code}",
                status_code=502,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ServiceError(
                f"{service} did not respond within {timeout.read:.0f}s. "
                "The service is probably busy; try again later.",
                status_code=504,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError(f"{service} request failed: {type(exc).__name__}: {exc}") from exc
