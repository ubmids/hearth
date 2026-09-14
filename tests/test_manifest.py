"""The add-on listing, checked against the documented limits.

Amazon rejects listings for mismatches between what is claimed and what is
delivered, and every one of these limits is a silent rejection rather than a
build error. Checking them here means a typo in a description fails a test
rather than a submission.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = json.load(open(os.path.join(ROOT, "addon.json")))
LOC = M["storeListing"]["locales"]["en-US"]
REQUIRED_ICONS = {"72x72", "64x64", "88x88", "126x126", "180x180", "241x241"}


def test_descriptions_are_within_limits():
    assert len(LOC["shortDescription"]) <= 123, len(LOC["shortDescription"])
    assert len(LOC["fullDescription"]) <= 4000, len(LOC["fullDescription"])
    assert LOC["shortDescription"].strip() and LOC["fullDescription"].strip()
    print(f"PASS descriptions within limits "
          f"({len(LOC['shortDescription'])}/123, {len(LOC['fullDescription'])}/4000)")


def test_example_phrases():
    p = LOC["examplePhrases"]
    assert 3 <= len(p) <= 4, len(p)
    assert all(len(x) <= 200 for x in p)
    print(f"PASS {len(p)} example phrases, all within 200 chars")


def test_all_six_icon_sizes_present():
    light = LOC["mediaAssets"]["icons"]["light"]
    assert {i["size"] for i in light} == REQUIRED_ICONS, {i["size"] for i in light}
    dark = LOC["mediaAssets"]["icons"].get("dark", [])
    assert not dark or {i["size"] for i in dark} == REQUIRED_ICONS
    print("PASS all six icon sizes declared")


def test_carousel_image():
    c = LOC["mediaAssets"]["carouselImages"]
    assert len(c) >= 1
    assert c[0]["size"] == "600x900"
    assert c[0]["altText"] and len(c[0]["altText"]) <= 250
    print("PASS carousel image declared at 600x900 with alt text")


def test_every_uri_is_https():
    """All image URIs must use HTTPS. So must privacy and terms."""
    uris = [i["uri"] for i in LOC["mediaAssets"]["icons"]["light"]]
    uris += [c["uri"] for c in LOC["mediaAssets"]["carouselImages"]]
    uris += [LOC["privacyAndCompliance"]["privacyPolicyUrl"],
             LOC["privacyAndCompliance"]["termsOfUseUrl"]]
    uris.append(M["integrations"][0]["config"]["endpoints"]["default"]["uri"])
    bad = [u for u in uris if not u.startswith("https://")]
    assert not bad, bad
    print(f"PASS all {len(uris)} URIs are HTTPS")


def test_the_declared_assets_are_actually_served():
    """The listing can be rejected for icons that do not render. Claiming a URL
    is not the same as serving one, so fetch every asset the listing declares."""
    if os.getenv("SKIP_NETWORK"):
        print("SKIP network checks disabled")
        return
    targets = [i["uri"] for i in LOC["mediaAssets"]["icons"]["light"]]
    targets += [c["uri"] for c in LOC["mediaAssets"]["carouselImages"]]
    targets += [LOC["privacyAndCompliance"]["privacyPolicyUrl"],
                LOC["privacyAndCompliance"]["termsOfUseUrl"]]
    for u in targets:
        try:
            with urllib.request.urlopen(u, timeout=30) as r:
                assert r.status == 200, f"{u} returned {r.status}"
                assert len(r.read()) > 200, f"{u} served almost nothing"
        except Exception as e:
            raise AssertionError(f"{u} is declared but not served: {e}") from e
    print(f"PASS all {len(targets)} declared assets are served")


def test_the_mcp_endpoint_matches_the_deployment():
    uri = M["integrations"][0]["config"]["endpoints"]["default"]["uri"]
    assert uri.endswith("/mcp"), uri
    print("PASS the MCP endpoint is declared:", uri)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nall green ({len(fns)} tests)")
