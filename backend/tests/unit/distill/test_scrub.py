from coffer.domain.distill.scrub import scrub_text


def test_redacts_common_secret_patterns():
    out = scrub_text("token sk-ABCDEF0123456789ABCDEF and AKIA1234567890ABCD ok")
    assert "sk-ABCDEF0123456789ABCDEF" not in out
    assert "AKIA1234567890ABCD" not in out
    assert "[redacted]" in out


def test_truncates_long_blobs():
    out = scrub_text("x" * 5000, max_chars=2000)
    assert len(out) <= 2000 + len(" …[truncated]")


def test_scrubs_password_assignment() -> None:
    out = scrub_text("password=hunter2longvalue in config")
    assert "hunter2longvalue" not in out
    assert "[redacted]" in out


def test_scrubs_url_credentials() -> None:
    out = scrub_text("connect to https://user:s3cretpass@host/db")
    assert "s3cretpass" not in out
    assert "[redacted]" in out
