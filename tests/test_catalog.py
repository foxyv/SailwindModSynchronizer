from sailwind_mod_sync.catalog.github import (
    fetch_readme,
    fetch_release,
    list_releases,
    pick_release_asset,
    pick_zip_asset,
    parse_repo_url,
    repo_page_url,
)
from sailwind_mod_sync.catalog.mvc import merge_catalog
from sailwind_mod_sync.http_util import HttpError
from sailwind_mod_sync.models import ReleaseAsset


def test_merge_dedupes_duplicate_guids() -> None:
    mod_list = [
        {"guid": "com.raddude.sailadex", "repo": "https://github.com/bryon82/SailwindSail-a-dex"},
        {"guid": "com.raddude82.sailadex", "repo": "https://github.com/bryon82/SailwindSail-a-dex"},
        {"guid": "com.nandbrew.stickyfix", "repo": "https://github.com/NANDbrew/StickyFix"},
    ]
    versions = [
        {"guid": "com.raddude.sailadex", "repo": "https://github.com/bryon82/SailwindSail-a-dex", "version": "v2.0.0"},
        {"guid": "com.raddude82.sailadex", "repo": "https://github.com/bryon82/SailwindSail-a-dex", "version": "v2.0.0"},
        {"guid": "com.nandbrew.stickyfix", "repo": "https://github.com/NANDbrew/StickyFix", "version": "none"},
    ]
    entries = merge_catalog(mod_list, versions)
    by_name = {entry.name: entry for entry in entries}
    sailadex = by_name["SailwindSail-a-dex"]
    assert sailadex.available
    assert sailadex.latest_version == "2.0.0"
    assert "com.raddude.sailadex" in sailadex.guids
    assert "com.raddude82.sailadex" in sailadex.guids
    sticky = by_name["StickyFix"]
    assert not sticky.available
    assert sticky.latest_version is None


def test_parse_github_and_gitlab_urls() -> None:
    github = parse_repo_url("https://github.com/foxyv/dizzy_sailwind_mods/")
    assert github.is_github
    assert github.full_path == "foxyv/dizzy_sailwind_mods"
    gitlab = parse_repo_url("https://gitlab.com/group/sub/project.git")
    assert gitlab.is_gitlab
    assert gitlab.full_path == "group/sub/project"


def test_repo_page_url_normalizes_hosts() -> None:
    assert (
        repo_page_url("https://github.com/NANDbrew/StickyFix.git/")
        == "https://github.com/NANDbrew/StickyFix"
    )
    assert repo_page_url("NANDbrew/StickyFix") == "https://github.com/NANDbrew/StickyFix"
    assert (
        repo_page_url("https://gitlab.com/group/sub/project.git")
        == "https://gitlab.com/group/sub/project"
    )
    assert (
        repo_page_url("https://github.com/NANDbrew/StickyFix/releases/tag/v1.2.3")
        == "https://github.com/NANDbrew/StickyFix"
    )
    assert (
        repo_page_url("https://gitlab.com/group/sub/project/-/releases")
        == "https://gitlab.com/group/sub/project"
    )
    assert repo_page_url("") is None
    assert repo_page_url("not a url") is None


def test_pick_zip_prefers_matching_name() -> None:
    assets = [
        ReleaseAsset("source.zip", "https://example/source.zip"),
        ReleaseAsset("Dizzy.Calendar-0.1.0.zip", "https://example/cal.zip"),
        ReleaseAsset("Dizzy.Gamma-0.3.3.zip", "https://example/gamma.zip"),
    ]
    chosen = pick_zip_asset(assets, "com.dizzy.sailwind.gamma", "dizzy_sailwind_mods")
    assert chosen.name == "Dizzy.Gamma-0.3.3.zip"


def test_pick_release_accepts_dll_when_no_zip() -> None:
    assets = [ReleaseAsset("SaveCleaner.dll", "https://example/SaveCleaner.dll")]
    chosen = pick_release_asset(assets, "com.nandbrew.savecleaner", "SaveCleaner")
    assert chosen.name == "SaveCleaner.dll"


def test_pick_release_prefers_zip_over_dll() -> None:
    assets = [
        ReleaseAsset("CookedInfo.dll", "https://example/CookedInfo.dll"),
        ReleaseAsset("CookedInfo.zip", "https://example/CookedInfo.zip"),
    ]
    chosen = pick_release_asset(assets, "pr0skynesis.cookedinfo", "CookedInfo-Sailwind-Mod")
    assert chosen.name == "CookedInfo.zip"


class _GithubListHttp:
    def __init__(self, latest_error: Exception | None, payload) -> None:
        self.latest_error = latest_error
        self.payload = payload
        self.urls: list[str] = []

    def get_json(self, url, extra_headers=None, etag=None):
        self.urls.append(url)
        if url.endswith("/releases/latest"):
            if self.latest_error is not None:
                raise self.latest_error
            return self.payload, None, False
        if url.endswith("/releases"):
            return self.payload, None, False
        raise AssertionError(url)


def test_fetch_release_falls_back_to_prerelease_list() -> None:
    payload = [
        {
            "tag_name": "v0.3.2",
            "name": "v0.3.2 (alpha)",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-08-09T21:48:02Z",
            "html_url": "https://github.com/DiamondMiner99/sailwind-coop/releases/tag/v0.3.2",
            "assets": [
                {
                    "name": "SailwindCoop-v0.3.2.zip",
                    "browser_download_url": "https://example/SailwindCoop-v0.3.2.zip",
                    "size": 12,
                }
            ],
        },
        {
            "tag_name": "v0.3.1",
            "name": "v0.3.1",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-08-01T00:00:00Z",
            "html_url": "https://github.com/DiamondMiner99/sailwind-coop/releases/tag/v0.3.1",
            "assets": [
                {
                    "name": "SailwindCoop-v0.3.1.zip",
                    "browser_download_url": "https://example/old.zip",
                    "size": 8,
                }
            ],
        },
    ]
    http = _GithubListHttp(HttpError("HTTP 404", status_code=404), payload)
    release = fetch_release(http, "https://github.com/DiamondMiner99/sailwind-coop")
    assert release.tag == "v0.3.2"
    assert release.assets[0].name == "SailwindCoop-v0.3.2.zip"
    assert http.urls[0].endswith("/releases/latest")
    assert http.urls[1].endswith("/releases")


def test_fetch_release_list_prefers_stable_over_newer_prerelease() -> None:
    payload = [
        {
            "tag_name": "v0.4.0-pre",
            "prerelease": True,
            "draft": False,
            "published_at": "2026-09-01T00:00:00Z",
            "assets": [
                {
                    "name": "mod-pre.zip",
                    "browser_download_url": "https://example/pre.zip",
                }
            ],
        },
        {
            "tag_name": "v0.3.0",
            "prerelease": False,
            "draft": False,
            "published_at": "2026-08-01T00:00:00Z",
            "assets": [
                {
                    "name": "mod.zip",
                    "browser_download_url": "https://example/mod.zip",
                }
            ],
        },
    ]
    http = _GithubListHttp(HttpError("HTTP 404", status_code=404), payload)
    release = fetch_release(http, "https://github.com/example/mod")
    assert release.tag == "v0.3.0"


def test_merge_with_custom_keeps_extra_repo() -> None:
    from sailwind_mod_sync.catalog.custom import merge_with_custom
    from sailwind_mod_sync.models import CatalogEntry

    mvc = merge_catalog(
        [{"guid": "com.nandbrew.stickyfix", "repo": "https://github.com/NANDbrew/StickyFix"}],
        [{"guid": "com.nandbrew.stickyfix", "repo": "https://github.com/NANDbrew/StickyFix", "version": "v1.0.0"}],
    )
    custom = [
        CatalogEntry(
            repo="https://github.com/DiamondMiner99/sailwind-coop",
            guids=["com.sailwindcoop.mod"],
            primary_guid="com.sailwindcoop.mod",
            name="sailwind-coop",
            latest_raw="v0.3.2",
            latest_version="0.3.2",
            available=True,
            custom=True,
        )
    ]
    merged = merge_with_custom(mvc, custom)
    names = {entry.name: entry for entry in merged}
    assert "StickyFix" in names
    assert names["sailwind-coop"].custom
    assert names["sailwind-coop"].primary_guid == "com.sailwindcoop.mod"


def test_merge_with_custom_skips_mvc_duplicate() -> None:
    from sailwind_mod_sync.catalog.custom import merge_with_custom
    from sailwind_mod_sync.models import CatalogEntry

    mvc = merge_catalog(
        [{"guid": "com.nandbrew.stickyfix", "repo": "https://github.com/NANDbrew/StickyFix"}],
        [{"guid": "com.nandbrew.stickyfix", "repo": "https://github.com/NANDbrew/StickyFix", "version": "v1.0.0"}],
    )
    custom = [
        CatalogEntry(
            repo="https://github.com/NANDbrew/StickyFix.git",
            guids=["com.nandbrew.stickyfix"],
            primary_guid="com.nandbrew.stickyfix",
            name="StickyFix",
            latest_raw="v9.9.9",
            latest_version="9.9.9",
            available=True,
            custom=True,
        )
    ]
    merged = merge_with_custom(mvc, custom)
    sticky = [entry for entry in merged if "stickyfix" in entry.primary_guid.lower()]
    assert len(sticky) == 1
    assert not sticky[0].custom
    assert sticky[0].latest_version == "1.0.0"


class _ReadmeHttp:
    def get_bytes(self, url, extra_headers=None):
        assert url.endswith("/readme")
        assert extra_headers and "raw" in extra_headers.get("Accept", "")
        return b"# Sailwind Co-op\n\nCrew a ship."

    def get_json(self, url, extra_headers=None, etag=None):
        assert "/releases" in url
        return (
            [
                {
                    "tag_name": "v0.3.2",
                    "name": "v0.3.2",
                    "draft": False,
                    "assets": [],
                },
                {
                    "tag_name": "v0.3.1",
                    "name": "v0.3.1",
                    "draft": True,
                    "assets": [],
                },
            ],
            None,
            False,
        )


def test_fetch_readme_and_list_releases() -> None:
    http = _ReadmeHttp()
    text = fetch_readme(http, "https://github.com/DiamondMiner99/sailwind-coop")
    assert "Crew a ship" in text
    releases = list_releases(http, "https://github.com/DiamondMiner99/sailwind-coop")
    assert [item.tag for item in releases] == ["v0.3.2"]
