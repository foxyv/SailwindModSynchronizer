from sailwind_mod_sync.models import is_newer, parse_mod_version, version_key


def test_parse_strips_v_prefix() -> None:
    assert parse_mod_version("v1.3.3") == "1.3.3"
    assert parse_mod_version("1.2.0") == "1.2.0"
    assert parse_mod_version("Release 19.0") == "19.0"


def test_parse_none_is_unavailable() -> None:
    assert parse_mod_version("none") is None
    assert parse_mod_version("") is None
    assert parse_mod_version(None) is None


def test_is_newer() -> None:
    assert is_newer("v1.4.0", "1.3.4")
    assert not is_newer("1.3.3", "v1.3.3")
    assert version_key("v2.0.0") > version_key("v1.10.0")
