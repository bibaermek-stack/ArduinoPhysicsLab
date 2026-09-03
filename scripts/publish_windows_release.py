"""GitHub Release-ке ArduinoPhysicsLab.exe жүктеу (git credential арқылы).

77MB .exe git-ке commit етілмейді — тек Releases asset.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "bibaermek-stack"
REPO = "ArduinoPhysicsLab"
ASSET_NAME = "ArduinoPhysicsLab.exe"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_token() -> str:
    filled = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    username = ""
    password = ""
    for line in filled.splitlines():
        if line.startswith("username="):
            username = line.split("=", 1)[1].strip()
        elif line.startswith("password="):
            password = line.split("=", 1)[1].strip()
    if password:
        return password
    if username:
        return username
    raise SystemExit("GitHub token табылмады (git credential fill бос).")


def _request(
    method: str,
    url: str,
    token: str,
    *,
    data: bytes | None = None,
    content_type: str = "application/json",
    extra_headers: dict[str, str] | None = None,
    allow_statuses: frozenset[int] | None = None,
) -> tuple[int, dict | str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ArduinoPhysicsLab-release",
    }
    if extra_headers:
        headers.update(extra_headers)
    if data is not None:
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(data))
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            parsed: dict | str
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = body
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if allow_statuses and exc.code in allow_statuses:
            try:
                parsed_error: dict | str = json.loads(detail) if detail else {}
            except json.JSONDecodeError:
                parsed_error = detail
            return exc.code, parsed_error
        raise SystemExit(f"GitHub API {method} {url} -> {exc.code}: {detail}") from exc


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: publish_windows_release.py <tag> [exe_path]")
    tag = sys.argv[1]
    exe_path = Path(sys.argv[2]) if len(sys.argv) > 2 else _project_root() / "release" / ASSET_NAME
    if not exe_path.is_file() or exe_path.stat().st_size < 1024:
        raise SystemExit(f"exe табылмады немесе тым кішкентай: {exe_path}")

    token = _git_token()
    print(f"Token OK (len={len(token)}), exe={exe_path} ({exe_path.stat().st_size} bytes)")

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    status, existing = _request(
        "GET",
        f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{tag}",
        token,
        allow_statuses=frozenset({404}),
    )
    if status == 200 and isinstance(existing, dict) and existing.get("id"):
        release_id = existing["id"]
        print(f"Release {tag} already exists id={release_id}")
        for asset in existing.get("assets") or []:
            if asset.get("name") == ASSET_NAME:
                print(f"Deleting old asset {asset['id']}")
                _request(
                    "DELETE",
                    f"https://api.github.com/repos/{OWNER}/{REPO}/releases/assets/{asset['id']}",
                    token,
                )
    else:
        payload = json.dumps(
            {
                "tag_name": tag,
                "target_commitish": sha,
                "name": f"Arduino Physics Lab {tag.lstrip('v')}",
                "body": (
                    "Windows onefile: ArduinoPhysicsLab.exe (_internal қалта жоқ).\n"
                    "Сайт жүктеуі: https://arduinophysicslab-production-ab65.up.railway.app/download/windows"
                ),
                "draft": False,
                "prerelease": False,
                "make_latest": "true",
            }
        ).encode("utf-8")
        status, created = _request(
            "POST",
            f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
            token,
            data=payload,
        )
        if not isinstance(created, dict) or not created.get("id"):
            raise SystemExit(f"Release құрылмады: {created}")
        release_id = created["id"]
        print(f"Created release {tag} id={release_id}")

    print("Uploading exe...")
    data = exe_path.read_bytes()
    upload_url = (
        f"https://uploads.github.com/repos/{OWNER}/{REPO}/releases/{release_id}"
        f"/assets?name={ASSET_NAME}"
    )
    status, uploaded = _request(
        "POST",
        upload_url,
        token,
        data=data,
        content_type="application/octet-stream",
    )
    if not isinstance(uploaded, dict) or not uploaded.get("browser_download_url"):
        raise SystemExit(f"Upload сәтсіз: {uploaded}")
    print(f"OK {status} {uploaded['browser_download_url']} ({uploaded.get('size')} bytes)")


if __name__ == "__main__":
    main()
