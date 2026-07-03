"""Unit tests for Smithsonian fetcher parsing helpers."""
from __future__ import annotations

from scripts.fetch_smithsonian import (
    is_china,
    normalize_record,
    search_url,
)


def test_search_url_includes_unit_code():
    url = search_url("FSG")
    assert "FSG" in url
    assert "openaccess/api/v1.0/content/FSG/search" in url


def test_normalize_record_extracts_image_and_title():
    """A well-formed record with online_media should produce a normalized dict."""
    sample = {
        "id": "object-123",
        "unitCode": "FSG",
        "content": {
            "descriptiveNonRepeating": {
                "guid": "object-123",
                "title": {"content": "Ming Dynasty Blue-and-White Vase", "label": "Title"},
                "online_media": {
                    "media": [
                        {
                            "content": "https://ids.si.edu/ids/deliveryService?id=NMNHANTHRO-123",
                            "type": "Images",
                        }
                    ]
                },
            },
            "indexedStructured": {
                "place": [{"content": "China"}, {"content": "Asia"}],
                "date": [{"content": "Ming Dynasty, 1368-1644"}],
                "topic": [{"content": "Ceramics"}, {"content": "Porcelain"}],
            },
            "freetext": {
                "physicalDescription": [{"content": "porcelain with cobalt blue underglaze"}],
            },
        },
    }
    result = normalize_record(sample)
    assert result is not None
    assert result["object_id"] == "object-123"
    assert result["title"] == "Ming Dynasty Blue-and-White Vase"
    assert "China" in result["places"]
    assert "Ceramics" in result["topics"]
    assert result["date"] == "Ming Dynasty, 1368-1644"
    assert "porcelain" in result["medium"]


def test_normalize_record_returns_none_for_no_media():
    """Records without online_media have no downloadable image."""
    sample = {
        "id": "obj-no-media",
        "content": {
            "descriptiveNonRepeating": {"guid": "obj-no-media", "title": {"content": "X"}},
            "indexedStructured": {"place": [{"content": "China"}]},
        },
    }
    assert normalize_record(sample) is None


def test_is_china_filters_out_non_china():
    assert is_china({"places": ["China", "Asia"]}) is True
    assert is_china({"places": ["Japan"]}) is False
    assert is_china({"places": []}) is False
    assert is_china({}) is False


def test_normalize_record_handles_minimal_payload():
    """Just object_id + image_url is enough."""
    sample = {
        "id": "min-1",
        "content": {
            "descriptiveNonRepeating": {
                "guid": "min-1",
                "online_media": {
                    "media": [{"content": "https://ids.si.edu/ids/deliveryService?id=X-1"}]
                },
            },
        },
    }
    result = normalize_record(sample)
    assert result is not None
    assert result["object_id"] == "min-1"
    assert result["image_url"].endswith("X-1")
    assert result["title"] is None
    assert result["places"] == []
