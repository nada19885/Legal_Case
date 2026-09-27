import hashlib
import uuid


def random_id(prefix: str) -> str:
    return "{}_{}".format(
        prefix,
        uuid.uuid4().hex[:20].upper(),
    )


def stable_id(prefix: str, *parts) -> str:
    raw = "|".join(
        str(part or "")
        for part in parts
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:20]

    return "{}_{}".format(
        prefix,
        digest.upper(),
    )
