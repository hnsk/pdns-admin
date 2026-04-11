from pydantic import BaseModel


class Record(BaseModel):
    content: str
    disabled: bool = False


class RRSet(BaseModel):
    name: str
    type: str
    ttl: int
    records: list[Record]
    changetype: str = "REPLACE"
    comments: list[dict] | None = None


class ZoneCreate(BaseModel):
    name: str
    kind: str = "Native"
    nameservers: list[str] = []
    masters: list[str] = []
    template_id: int | None = None
    soa_mname: str | None = None
    soa_rname: str | None = None
    soa_refresh: int | None = None
    soa_retry: int | None = None
    soa_expire: int | None = None
    soa_ttl: int | None = None


class ZoneUpdate(BaseModel):
    kind: str | None = None
    masters: list[str] | None = None
    account: str | None = None
    soa_edit: str | None = None
    soa_edit_api: str | None = None


class CryptoKeyCreate(BaseModel):
    keytype: str = "ksk"
    active: bool = True
    algorithm: str = "ECDSAP256SHA256"
    bits: int = 0
    published: bool = True
