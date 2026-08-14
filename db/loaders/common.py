"""Small HTTP and Ethereum JSON-RPC helpers used by graph loaders."""

import json
from urllib import request


USER_AGENT = "defi-verification-thesis/1.0"


def fetch_text(url: str, timeout: int = 30) -> str:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str, timeout: int = 30):
    return json.loads(fetch_text(url, timeout=timeout))


def normalize_address(value: str) -> str:
    value = value.strip()
    if len(value) != 42 or not value.startswith("0x"):
        raise ValueError(f"Invalid Ethereum address: {value}")
    int(value[2:], 16)
    return value.lower()


class RpcClient:
    def __init__(self, url: str, timeout: int = 30):
        if not url:
            raise ValueError("SEPOLIA_RPC is required")
        self.url = url
        self.timeout = timeout
        self._request_id = 0

    def call(self, method: str, params=None):
        self._request_id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or [],
        }).encode("utf-8")
        req = request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        if "error" in body:
            raise RuntimeError(f"RPC {method} failed: {body['error']}")
        return body["result"]

    def chain_id(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def latest_block(self) -> int:
        return int(self.call("eth_blockNumber"), 16)

    def code_at(self, address: str, block: int | str = "latest") -> str:
        tag = hex(block) if isinstance(block, int) else block
        return self.call("eth_getCode", [address, tag])

    def logs(self, address: str, from_block: int, to_block: int, topics=None):
        query = {
            "address": address,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        if topics:
            query["topics"] = topics
        return self.call("eth_getLogs", [query])

    def eth_call(self, to: str, data: str) -> str:
        return self.call("eth_call", [{"to": to, "data": data}, "latest"])


def decode_abi_string(raw: str) -> str | None:
    """Decode string or bytes32 return data used by ERC-20 symbol()."""
    if not raw or raw == "0x":
        return None
    data = bytes.fromhex(raw[2:])
    try:
        if len(data) >= 64:
            offset = int.from_bytes(data[:32], "big")
            length = int.from_bytes(data[offset:offset + 32], "big")
            return data[offset + 32:offset + 32 + length].decode("utf-8")
        return data[:32].rstrip(b"\x00").decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None
