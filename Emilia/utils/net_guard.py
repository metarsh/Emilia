import ipaddress
import socket

import aiohttp
from yarl import URL


def _is_blocked_ip(address) -> bool:
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast:
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is not None and _is_blocked_ip(embedded):
            return True
        if ip.teredo is not None and any(_is_blocked_ip(part) for part in ip.teredo):
            return True
    return False


def validate_url(url: str) -> URL:
    try:
        parsed = URL(url)
        if parsed.scheme not in ("http", "https") or not parsed.host:
            raise ValueError("Only HTTP(S) URLs are allowed")
        if parsed.user is not None or parsed.password is not None:
            raise ValueError("URL credentials are not allowed")
        if not parsed.port or "%" in parsed.host:
            raise ValueError("Invalid URL host or port")
        try:
            ipaddress.ip_address(parsed.host)
        except ValueError:
            pass
        else:
            if _is_blocked_ip(parsed.host):
                raise ValueError("Nonpublic addresses are not allowed")
        return parsed
    except (TypeError, ValueError) as exc:
        raise ValueError("That URL is not allowed") from exc


def is_safe_url(url: str) -> bool:
    try:
        parsed = validate_url(url)
        addresses = socket.getaddrinfo(parsed.host, parsed.port, type=socket.SOCK_STREAM)
        return bool(addresses) and all(not _is_blocked_ip(info[4][0]) for info in addresses)
    except (ValueError, OSError):
        return False


class PublicResolver(aiohttp.abc.AbstractResolver):
    def __init__(self, resolver=None):
        self._resolver = resolver or aiohttp.resolver.ThreadedResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        results = await self._resolver.resolve(host, port, family=family)
        if not results or any(_is_blocked_ip(result["host"]) for result in results):
            raise OSError("DNS resolved to a nonpublic address")
        return results

    async def close(self):
        await self._resolver.close()


async def request_safe(method: str, url: str, *, max_redirects=3, timeout=15, **kwargs):
    from Emilia.utils.http import get_aiohttp_session

    if kwargs.pop("proxy", None) is not None:
        raise ValueError("Proxies are not allowed for public URL requests")
    kwargs.pop("allow_redirects", None)
    kwargs.pop("proxy_auth", None)
    if max_redirects < 0:
        raise ValueError("Redirect limit must be nonnegative")
    method = method.upper()
    session = await get_aiohttp_session(public_only=True)
    timeout_cfg = (
        timeout
        if isinstance(timeout, aiohttp.ClientTimeout)
        else aiohttp.ClientTimeout(total=timeout)
    )
    for hop in range(max_redirects + 1):
        parsed = validate_url(url)
        response = await session.request(
            method, parsed, allow_redirects=False, timeout=timeout_cfg, **kwargs
        )
        if response.status not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("Location")
        response.release()
        if not location:
            raise ValueError("Redirect without Location")
        if hop == max_redirects:
            raise ValueError("Too many redirects")
        next_url = validate_url(str(parsed.join(URL(location))))
        if parsed.scheme == "https" and next_url.scheme != "https":
            raise ValueError("HTTPS redirects must preserve transport security")
        # Location supplies the next query; do not replay credential parameters.
        kwargs.pop("params", None)
        if next_url.origin() != parsed.origin():
            kwargs.pop("auth", None)
            kwargs["headers"] = {
                key: value
                for key, value in (kwargs.get("headers") or {}).items()
                if key.lower()
                not in ("authorization", "cookie", "proxy-authorization", "x-api-key", "api-key")
            }
        if method not in ("GET", "HEAD"):
            raise ValueError("Redirects for mutating requests are not supported")
        url = str(next_url)


async def fetch_safe(url: str, **kwargs):
    return await request_safe("GET", url, **kwargs)
