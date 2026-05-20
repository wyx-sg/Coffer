from coffer import __version__


def test_version_is_semver_string() -> None:
    assert isinstance(__version__, str)
    parts = __version__.split(".")
    assert len(parts) >= 3
    assert all(part.isdigit() for part in parts[:3])
