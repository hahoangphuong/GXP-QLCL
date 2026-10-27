# QĐKT storage immutable-version capability inventory

This is a read-only technical capability inventory, independent of the legal renderer contract.

| Adapter | Existing read | Metadata/checksum | Generation-pinned read | Status |
| --- | --- | --- | --- | --- |
| LocalStorageService | Path-only file open | Size, computed SHA-256 | Not exposed | UNSUPPORTED |
| SmbStorageService | smbclient path-only open | Size, computed SHA-256 | Not exposed | UNSUPPORTED |
| ExternalBridgeStorageService | Bridge GET by path/root | Bridge stat and checksum | Not exposed | UNSUPPORTED |

StorageEntry contains relative path, name, directory flag and size. The StorageServiceProtocol read_stream signature does not accept a generation ID or return a binding to one immutable object version.

A checksum confirms observed bytes, **not** that the path remains immutable, nor that two reads or a subsequent operation use the same generation. A fabricated ETag, timestamp, or version_id is not proof of pinning. The static inspector never touches storage and will not elevate unsupported adapters.

An eventual, separately reviewed contract must define backend-specific generation identifiers, version/conditional reads, lifetime guarantees, integrity proofs and concurrent replacement/ABA tests. Do not treat this inventory as vendor validation.

No renderer, Word UAT, production storage or database changes. ready_to_render=False; Issues #74 and #144 stay OPEN.
