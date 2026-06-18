"""Dependency freshness for the admin Ops panel.

Reads **GitHub Dependabot alerts** for the configured repos (the app + the
backend), so an admin can spot outdated / vulnerable libraries in one place
without leaving Famo. GitHub is the source of truth — we don't re-implement
version comparison or a CVE database.

Results are cached per repo (1h) so opening the page doesn't hammer the API; a
manual refresh bypasses the cache.
"""

import time
from typing import Any

import requests

from app.core.config import settings

_CACHE_TTL = 3600  # seconds
_GITHUB_API = "https://api.github.com"
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _parse_alert(alert: dict[str, Any]) -> dict[str, Any]:
    vuln = alert.get("security_vulnerability") or {}
    package = vuln.get("package") or {}
    advisory = alert.get("security_advisory") or {}
    patched = (vuln.get("first_patched_version") or {}).get("identifier") or ""
    return {
        "package": package.get("name", ""),
        "ecosystem": package.get("ecosystem", ""),
        "severity": (advisory.get("severity") or vuln.get("severity") or "").lower(),
        "summary": advisory.get("summary", ""),
        "vulnerable_range": vuln.get("vulnerable_version_range", ""),
        "patched": patched,
        "state": alert.get("state", ""),
        "url": alert.get("html_url", ""),
        "created_at": (alert.get("created_at") or "")[:10],
    }


def _fetch_repo(repo: str, token: str) -> dict[str, Any]:
    """Fetch open Dependabot alerts for one ``owner/repo``."""
    try:
        resp = requests.get(
            f"{_GITHUB_API}/repos/{repo}/dependabot/alerts",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"state": "open", "per_page": 100},
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"ok": False, "alerts": [], "error": str(exc)}

    if resp.status_code == 200:
        alerts = [_parse_alert(a) for a in resp.json()]
        # Sort most-severe first for display.
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        alerts.sort(key=lambda a: order.get(a["severity"], 9))
        return {"ok": True, "alerts": alerts, "error": None}

    # 403 = alerts disabled or insufficient scope; 404 = no access / wrong slug.
    try:
        message = resp.json().get("message", f"HTTP {resp.status_code}")
    except ValueError:
        message = f"HTTP {resp.status_code}"
    return {"ok": False, "alerts": [], "error": message}


def dependency_report(force: bool = False) -> dict[str, Any]:
    """Per-repo Dependabot alert summary. ``configured`` is False (with a hint)
    when no token is set; otherwise each repo is fetched (cached unless
    ``force``)."""
    token = settings.github_token.strip()
    repos = settings.github_repo_list
    if not token:
        return {
            "configured": False,
            "repos": [
                {"repo": r, "ok": False, "alerts": [], "error": "GITHUB_TOKEN not set"}
                for r in repos
            ],
        }

    now = time.time()
    out: list[dict[str, Any]] = []
    for repo in repos:
        cached = _cache.get(repo)
        if not force and cached is not None and now - cached[0] < _CACHE_TTL:
            result = cached[1]
        else:
            result = _fetch_repo(repo, token)
            if result["ok"]:  # don't cache transient errors
                _cache[repo] = (now, result)
        out.append({"repo": repo, **result})
    return {"configured": True, "repos": out}
