import httpx


class PDNSError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"PowerDNS API error {status_code}: {detail}")


class PDNSClient:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def start(self, api_url: str, api_key: str, server_id: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{api_url.rstrip('/')}/api/v1/servers/{server_id}/",
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )

    async def reconfigure(self, api_url: str, api_key: str, server_id: str) -> None:
        if self._client:
            await self._client.aclose()
        await self.start(api_url, api_key, server_id)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PDNS client not started")
        return self._client

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = await self.client.request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise PDNSError(502, str(exc)) from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                detail = resp.text
            raise PDNSError(resp.status_code, detail)
        return resp

    # --- Server info ---

    async def get_server_info(self) -> dict:
        resp = await self._request("GET", "")
        return resp.json()

    async def get_statistics(self) -> list[dict]:
        resp = await self._request("GET", "/statistics")
        return resp.json()

    # --- Zones ---

    async def list_zones(self, dnssec: bool | None = None) -> list[dict]:
        params = {}
        if dnssec is not None:
            params["dnssec"] = str(dnssec).lower()
        resp = await self._request("GET", "/zones", params=params)
        return resp.json()

    async def get_zone(self, zone_id: str, rrsets: bool = True) -> dict:
        params = {}
        if not rrsets:
            params["rrsets"] = "false"
        resp = await self._request("GET", f"/zones/{zone_id}", params=params)
        return resp.json()

    async def create_zone(
        self,
        name: str,
        kind: str = "Native",
        nameservers: list[str] | None = None,
        masters: list[str] | None = None,
        rrsets: list[dict] | None = None,
        soa_edit_api: str = "DEFAULT",
        dnssec: bool = False,
        nsec3param: str | None = None,
        account: str = "",
    ) -> dict:
        data: dict = {
            "name": name if name.endswith(".") else name + ".",
            "kind": kind,
            "soa_edit_api": soa_edit_api,
            "account": account,
        }
        if nameservers:
            data["nameservers"] = [ns if ns.endswith(".") else ns + "." for ns in nameservers]
        if masters:
            data["masters"] = masters
        if rrsets:
            data["rrsets"] = rrsets
        if dnssec:
            data["dnssec"] = True
        if nsec3param:
            data["nsec3param"] = nsec3param
        resp = await self._request("POST", "/zones", json=data)
        return resp.json()

    async def delete_zone(self, zone_id: str) -> None:
        await self._request("DELETE", f"/zones/{zone_id}")

    async def update_zone(self, zone_id: str, data: dict) -> None:
        await self._request("PUT", f"/zones/{zone_id}", json=data)

    async def patch_rrsets(self, zone_id: str, rrsets: list[dict]) -> None:
        await self._request("PATCH", f"/zones/{zone_id}", json={"rrsets": rrsets})

    async def export_zone(self, zone_id: str) -> str:
        resp = await self._request("GET", f"/zones/{zone_id}/export")
        try:
            data = resp.json()
            if isinstance(data, dict) and "zone" in data:
                return data["zone"]
        except Exception:
            pass
        return resp.text

    async def rectify_zone(self, zone_id: str) -> None:
        await self._request("PUT", f"/zones/{zone_id}/rectify")

    async def notify_zone(self, zone_id: str) -> None:
        await self._request("PUT", f"/zones/{zone_id}/notify")

    async def axfr_retrieve(self, zone_id: str) -> None:
        await self._request("PUT", f"/zones/{zone_id}/axfr-retrieve")

    # --- DNSSEC / Cryptokeys ---

    async def list_cryptokeys(self, zone_id: str) -> list[dict]:
        resp = await self._request("GET", f"/zones/{zone_id}/cryptokeys")
        return resp.json()

    async def get_cryptokey(self, zone_id: str, key_id: int) -> dict:
        resp = await self._request("GET", f"/zones/{zone_id}/cryptokeys/{key_id}")
        return resp.json()

    async def create_cryptokey(self, zone_id: str, data: dict) -> dict:
        resp = await self._request("POST", f"/zones/{zone_id}/cryptokeys", json=data)
        return resp.json()

    async def toggle_cryptokey(self, zone_id: str, key_id: int, active: bool) -> None:
        await self._request("PUT", f"/zones/{zone_id}/cryptokeys/{key_id}", json={"active": active})

    async def delete_cryptokey(self, zone_id: str, key_id: int) -> None:
        await self._request("DELETE", f"/zones/{zone_id}/cryptokeys/{key_id}")

    # --- Metadata ---

    async def list_metadata(self, zone_id: str) -> list[dict]:
        resp = await self._request("GET", f"/zones/{zone_id}/metadata")
        return resp.json()

    async def get_metadata(self, zone_id: str, kind: str) -> dict:
        resp = await self._request("GET", f"/zones/{zone_id}/metadata/{kind}")
        return resp.json()

    async def set_metadata(self, zone_id: str, kind: str, value: list[str]) -> None:
        await self._request("PUT", f"/zones/{zone_id}/metadata/{kind}", json={"metadata": value})

    async def delete_metadata(self, zone_id: str, kind: str) -> None:
        await self._request("DELETE", f"/zones/{zone_id}/metadata/{kind}")

    # --- Search ---

    async def search(self, q: str, max_results: int = 100, object_type: str = "all") -> list[dict]:
        resp = await self._request(
            "GET", "/search-data", params={"q": q, "max": max_results, "object_type": object_type}
        )
        return resp.json()

    # --- TSIG Keys ---

    async def list_tsig_keys(self) -> list[dict]:
        resp = await self._request("GET", "/tsigkeys")
        return resp.json()

    async def create_tsig_key(self, name: str, algorithm: str, key: str = "") -> dict:
        data = {"name": name, "algorithm": algorithm}
        if key:
            data["key"] = key
        resp = await self._request("POST", "/tsigkeys", json=data)
        return resp.json()

    async def delete_tsig_key(self, key_id: str) -> None:
        await self._request("DELETE", f"/tsigkeys/{key_id}")


pdns = PDNSClient()
