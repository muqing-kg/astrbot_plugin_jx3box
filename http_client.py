"""异步 HTTP 客户端。"""
from __future__ import annotations

from typing import Any

import aiohttp


class HttpClient:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
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

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        await self.start()
        assert self._session is not None
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def get_bytes(self, url: str) -> bytes:
        await self.start()
        assert self._session is not None
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()
