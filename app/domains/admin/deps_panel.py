"""Dependency freshness for the admin Ops panel.

Reads **GitHub Dependabot alerts** for the configured repos (the app + the
backend), so an admin can spot outdated / vulnerable libraries in one place
without leaving Famo. GitHub is the source of truth — we don't re-implement
version comparison or a CVE database.

Results are cached per repo (1h) so opening the page doesn't hammer the API; a
manual refresh bypasses the cache.
"""

import concurrent.futures
import re
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from app.core.config import settings

_CACHE_TTL = 3600  # seconds
_GITHUB_API = "https://api.github.com"
_PYPI = "https://pypi.org/pypi"
_PUB = "https://pub.dev/api/packages"
_RAW_GH = "https://raw.githubusercontent.com"
_VERSION_RE = re.compile(r"\d[\w.]*")
# pubspec entries that are SDK/lints refs, not pub.dev packages with a plain version.
_SKIP_PUB = {"flutter", "flutter_localizations", "flutter_test", "flutter_lints"}
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lib_cache: dict[str, tuple[float, dict[str, Any]]] = {}


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


# --- Library version check (current vs latest, like travel-mate's Ops & libs) ---


def _first_version(text: str) -> str:
    """Extract the first version-looking token from a constraint (``^2.6.1`` → ``2.6.1``)."""
    match = _VERSION_RE.search(text or "")
    return match.group() if match else ""


def _read_pyproject_deps() -> dict[str, str]:
    """``name -> pinned version`` from this app's ``pyproject.toml`` (baked into the image)."""
    path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    project = data.get("project", {})
    reqs: list[str] = list(project.get("dependencies", []))
    for group in (project.get("optional-dependencies", {}) or {}).values():
        reqs.extend(group)
    out: dict[str, str] = {}
    for req in reqs:
        match = re.match(r"^([A-Za-z0-9._-]+)", req)
        if not match:
            continue
        name = match.group(1)
        out[name] = _first_version(req[len(name) :])
    return out


def _parse_pubspec(text: str) -> dict[str, str]:
    """``name -> version`` from a pubspec's ``dependencies``/``dev_dependencies`` (direct,
    plain-version entries only — sdk/git/path refs and Flutter SDK packages are skipped)."""
    out: dict[str, str] = {}
    section: str | None = None
    for line in text.splitlines():
        if line and not line[0].isspace():
            key = line.split(":", 1)[0].strip()
            section = key if key in ("dependencies", "dev_dependencies") else None
            continue
        if section is None:
            continue
        entry = re.match(r"^  ([A-Za-z0-9_]+):\s*(.*)$", line)
        if not entry:
            continue
        name, value = entry.group(1), entry.group(2).strip()
        if name in _SKIP_PUB:
            continue
        version = _first_version(value)
        if version:  # a Map value (sdk/git/path) has no inline version → skip
            out[name] = version
    return out


def _pypi_latest(name: str) -> str | None:
    try:
        resp = requests.get(f"{_PYPI}/{name}/json", timeout=8)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    version = resp.json().get("info", {}).get("version")
    return str(version) if version else None


def _pub_latest(name: str) -> str | None:
    try:
        resp = requests.get(f"{_PUB}/{name}", headers={"Accept": "application/json"}, timeout=8)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    version = resp.json().get("latest", {}).get("version")
    return str(version) if version else None


def _statuses(deps: dict[str, str], latest_fn: Callable[[str], str | None]) -> list[dict[str, Any]]:
    def one(item: tuple[str, str]) -> dict[str, Any]:
        name, current = item
        latest = latest_fn(name)
        return {
            "name": name,
            "current": current or "?",
            "latest": latest or "?",
            "outdated": bool(latest and current and latest != current),
            "note": "" if latest else "lookup failed",
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(one, deps.items()))
    # Outdated first, then alphabetical.
    rows.sort(key=lambda r: (not r["outdated"], str(r["name"]).lower()))
    return rows


def library_report(force: bool = False) -> dict[str, Any]:
    """Backend (pip → PyPI) and app (pub.dev) dependencies with their latest versions.
    Cached in memory (1h) so page loads make no outbound calls unless ``force``."""
    now = time.time()
    cached = _lib_cache.get("libs")
    if not force and cached is not None and now - cached[0] < _CACHE_TTL:
        return cached[1]

    app_repo = next((r for r in settings.github_repo_list if r.endswith("-app")), "")
    pub_deps: dict[str, str] = {}
    if app_repo:
        try:
            resp = requests.get(f"{_RAW_GH}/{app_repo}/master/pubspec.yaml", timeout=8)
            if resp.status_code == 200:
                pub_deps = _parse_pubspec(resp.text)
        except requests.RequestException:
            pub_deps = {}

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
        "pip": _statuses(_read_pyproject_deps(), _pypi_latest),
        "pub": _statuses(pub_deps, _pub_latest),
        "app_repo": app_repo,
    }
    _lib_cache["libs"] = (now, report)
    return report
