"""Codex live limits: the usage reply is mapped onto the 5-hour and weekly windows.

    uv run python tests/test_codex_live.py
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from deskhub import codex_live  # noqa: E402

problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


NOW = 1_000_000.0
reply = {"plan_type": "plus", "rate_limit": {
    "primary_window": {"used_percent": 36.04, "limit_window_seconds": 18000, "reset_after_seconds": 100, "reset_at": NOW + 100},
    "secondary_window": {"used_percent": 100, "limit_window_seconds": 604800, "reset_after_seconds": 5000}}}
got = codex_live.parse_usage(reply, NOW)
check(got.get("five_hour") == {"pct": 36.0, "reset": int(NOW + 100)}, f"five_hour: {got}")
check(got.get("seven_day") == {"pct": 100.0, "reset": int(NOW + 5000)}, f"seven_day from reset_after_seconds: {got}")
check(got.get("updated") == int(NOW), "updated is now")

check(codex_live.parse_usage({}, NOW) == {}, "empty reply")
check(codex_live.parse_usage({"rate_limit": None}, NOW) == {}, "no rate_limit")
expired = {"rate_limit": {"primary_window": {"used_percent": 5, "limit_window_seconds": 18000, "reset_at": NOW - 1}}}
check(codex_live.parse_usage(expired, NOW) == {}, "a window whose reset has passed is dropped")
odd = {"rate_limit": {"primary_window": {"used_percent": 5, "limit_window_seconds": 36000, "reset_at": NOW + 5}}}
check(codex_live.parse_usage(odd, NOW) == {}, "an unknown window length is ignored")

# No sign-in file or an empty token: nothing is requested, no limits.
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "auth.json"
    check(codex_live.CodexLiveLimits(p).get(active=True) == {}, "missing auth.json")
    p.write_text(json.dumps({"tokens": {"access_token": ""}}), encoding="utf-8")
    check(codex_live.CodexLiveLimits(p).get(active=True) == {}, "empty token")

print("PROBLEMS:" if problems else "OK", *problems, sep="\n" if problems else " ")
sys.exit(1 if problems else 0)
