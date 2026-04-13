from tests.downloads.mime_utils import build_target, mime_folder_name


def test_mime_folder_name_uses_url_extension_for_generic_content_type() -> None:
    folder = mime_folder_name(
        "application/octet-stream",
        "https://example.org/files/catalog-data-gov-atlsist0112-20260408.pdf",
    )
    assert folder == "pdf"


def test_mime_folder_name_maps_pptx_content_type() -> None:
    folder = mime_folder_name(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "https://example.org/download?id=42",
    )
    assert folder == "pptx"


def test_build_target_supports_pptx_alias() -> None:
    target = build_target(["pptx"])
    assert "pptx" in target.extensions
    assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in (
        target.mime_types
    )
