"""异步 HTTP 客户端。"""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class HttpClient:
    def __init__(self, timeout: int = 20, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": "AstrBot-JX3BOX-Plugin/1.0",
                    "Accept": "application/json,image/*,*/*",
                },
            )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _request(self, method: str, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        await self.start()
        assert self._session is not None
        last_err: Exception | None = None
        attempts = self.retries + 1
        for i in range(attempts):
            try:
                resp = await self._session.request(method, url, **kwargs)
                if resp.status >= 500 and i < attempts - 1:
                    resp.release()
                    last_err = aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=resp.status,
                        message=f"server error {resp.status}",
                        headers=resp.headers,
                    )
                    await asyncio.sleep(0.35 * (i + 1))
                    continue
                resp.raise_for_status()
                return resp
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                if i >= attempts - 1:
                    break
                await asyncio.sleep(0.35 * (i + 1))
        assert last_err is not None
        raise last_err

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._request("GET", url, params=params)
        async with resp:
            return await resp.json(content_type=None)

    async def get_bytes(self, url: str) -> bytes:
        resp = await self._request("GET", url)
        async with resp:
            return await resp.read()
