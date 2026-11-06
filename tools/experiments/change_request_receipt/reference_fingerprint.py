"""CONTRACT_PENDING_APPROVAL: illustrative vectors, never imported by runtime."""
import hashlib
import hmac
import json


def fingerprint(*, key, version, actor, site, command, payload):
    """Canonical JSON example: callers must supply validated types and key management."""
    value = {
        'version': version, 'actor': actor, 'site': site,
        'command': command, 'payload': payload,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def normalized_unordered_ids(values):
    """Example only: a future schema must explicitly identify unordered fields."""
    if len(values) != len(set(values)):
        raise ValueError('duplicate identity')
    return sorted(values)
