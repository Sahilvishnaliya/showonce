"""Skill Passport: a portable, tamper-evident credential for a learned robot skill.

Teach once -> export the passport -> any ShowOnce bench imports it, executes
the skill, and re-verifies it there. The passport binds the learned program,
its demonstration provenance, and the verification result under one SHA-256.
"""
import hashlib
import json
import time


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sign(payload):
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def create_passport(program, verification=None, bench="showonce-bench"):
    payload = {
        "kind": "showonce.skill-passport",
        "version": 1,
        "skill_id": "skill-" + _sign(program)[:10],
        "issued_at": int(time.time()),
        "bench": bench,
        "program": program,
        "verification": verification or {},
    }
    payload["sha256"] = _sign(payload)
    return payload


def verify_passport(passport):
    if not isinstance(passport, dict) or passport.get("kind") != "showonce.skill-passport":
        return {"valid": False, "reason": "Not a ShowOnce Skill Passport."}
    expected = passport.get("sha256", "")
    payload = {k: v for k, v in passport.items() if k != "sha256"}
    if _sign(payload) != expected:
        return {"valid": False, "reason": "Hash mismatch — passport was modified after issue."}
    program = passport.get("program") or {}
    if not program.get("rules"):
        return {"valid": False, "reason": "Passport carries no learned rules."}
    return {"valid": True, "skill_id": passport.get("skill_id"),
            "task": program.get("task"), "rules": program.get("rules"),
            "issued_verification": (passport.get("verification") or {}).get("score")}
