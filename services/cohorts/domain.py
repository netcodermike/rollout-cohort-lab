from hashlib import sha256
import json


def operation(data, _):
    flag, subjects = data["flag"], data["subjects"]
    if not isinstance(flag, str) or not flag.strip() or not isinstance(subjects, list):
        raise ValueError("Expected flag and subjects")
    if any(not isinstance(subject, str) or not subject.strip() for subject in subjects):
        raise ValueError("Invalid subject ID")
    buckets = {}
    for subject in subjects:
        key = json.dumps([flag, subject], ensure_ascii=True, separators=(",", ":")).encode()
        buckets[subject] = int.from_bytes(sha256(key).digest()[:8], "big") % 10000
    return {"buckets": buckets}
