"""Standalone SOCKS5 ProxyConnector for aiohttp using python_socks.

Embedded directly to guarantee compatibility with Home Assistant Python 3.14+
and modern aiohttp, independent of external aiohttp-socks package versions.
"""

from __future__ import annotations

import asyncio
import socket
from ssl import SSLContext
from typing import Any

from aiohttp import ClientConnectorError, TCPConnector
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.client_proto import ResponseHandler

import python_socks
from python_socks import ProxyType, parse_proxy_url
from python_socks.async_.asyncio.v2 import Proxy


class ProxyTimeoutError(Exception):
    pass


class ProxyConnectionError(Exception):
    pass


class ProxyError(Exception):
    def __init__(self, message: str, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class NoResolver(AbstractResolver):
    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        return [
            {
                "hostname": host,
                "host": host,
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0,
            }
        ]

    async def close(self) -> None:
        pass


class _ResponseHandler(ResponseHandler):
    """Keep reference to StreamWriter for Python >= 3.11."""

    def __init__(
        self, loop: asyncio.AbstractEventLoop, writer: asyncio.StreamWriter
    ) -> None:
        super().__init__(loop)
        self._writer = writer


class _BaseProxyConnector(TCPConnector):
    async def _wrap_create_connection(
        self,
        *args: Any,
        addr_infos: list[Any],
        req: Any,
        timeout: Any,
        client_error: type[Exception] = ClientConnectorError,
        **kwargs: Any,
    ) -> tuple[asyncio.Transport, ResponseHandler]:
        try:
            host: str = addr_infos[0][4][0]
            port: int = addr_infos[0][4][1]
        except IndexError as e:
            raise ValueError("Invalid arg: `addr_infos`") from e

        ssl: SSLContext | None = kwargs.get("ssl")
        try:
            return await self._connect_via_proxy(
                host=host,
                port=port,
                ssl=ssl,
                timeout=timeout.sock_connect,
            )
        except python_socks.ProxyConnectionError as e:
            raise ProxyConnectionError(str(e)) from e
        except python_socks.ProxyTimeoutError as e:
            raise ProxyTimeoutError(str(e)) from e
        except python_socks.ProxyError as e:
            raise ProxyError(str(e), error_code=e.error_code) from e

    async def _connect_via_proxy(
        self,
        host: str,
        port: int,
        ssl: SSLContext | None = None,
        timeout: float | None = None,
    ) -> tuple[asyncio.Transport, ResponseHandler]:
        raise NotImplementedError


class ProxyConnector(_BaseProxyConnector):
    def __init__(
        self,
        host: str,
        port: int,
        proxy_type: ProxyType = ProxyType.SOCKS5,
        username: str | None = None,
        password: str | None = None,
        rdns: bool | None = None,
        proxy_ssl: SSLContext | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs["resolver"] = NoResolver()
        super().__init__(**kwargs)

        self._proxy_type = proxy_type
        self._proxy_host = host
        self._proxy_port = port
        self._proxy_username = username
        self._proxy_password = password
        self._rdns = rdns
        self._proxy_ssl = proxy_ssl

    async def _connect_via_proxy(
        self,
        host: str,
        port: int,
        ssl: SSLContext | None = None,
        timeout: float | None = None,
    ) -> tuple[asyncio.Transport, ResponseHandler]:
        proxy = Proxy(
            proxy_type=self._proxy_type,
            host=self._proxy_host,
            port=self._proxy_port,
            username=self._proxy_username,
            password=self._proxy_password,
            rdns=self._rdns,
            proxy_ssl=self._proxy_ssl,
        )

        stream = await proxy.connect(
            dest_host=host,
            dest_port=port,
            dest_ssl=ssl,
            timeout=timeout,
        )

        transport = stream.writer.transport
        protocol: ResponseHandler = _ResponseHandler(
            loop=self._loop,
            writer=stream.writer,
        )

        transport.set_protocol(protocol)
        protocol.connection_made(transport)

        return transport, protocol

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> ProxyConnector:
        proxy_type, host, port, username, password = parse_proxy_url(url)
        return cls(
            proxy_type=proxy_type,
            host=host,
            port=port,
            username=username,
            password=password,
            **kwargs,
        )
