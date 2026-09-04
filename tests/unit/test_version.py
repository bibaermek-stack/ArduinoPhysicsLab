"""``core/version.py`` юнит-тесті (Phase 9 — Production Deployment,
§ Part G "Application Versioning" — "one canonical version source")."""

import re

from core.version import __version__


def test_version_is_a_non_empty_semver_like_string() -> None:
    assert isinstance(__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+$", __version__), __version__


def test_version_matches_current_release() -> None:
    assert __version__ == "0.10.2"
