"""Upload validation tests: rejected before anything touches the database."""

from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.main import app
from app.utils.simple_pdf import make_pdf


async def test_non_pdf_extension_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/documents", files={"file": ("notes.txt", b"hello", "text/plain")}
    )

    assert response.status_code == 415
    assert "PDF" in response.json()["detail"]


async def test_pdf_extension_without_pdf_content_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/documents", files={"file": ("fake.pdf", b"<html>not a pdf</html>", "application/pdf")}
    )

    assert response.status_code == 415
    assert "%PDF" in response.json()["detail"]


async def test_empty_file_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/documents", files={"file": ("empty.pdf", b"", "application/pdf")}
    )

    assert response.status_code == 400


async def test_file_over_size_limit_is_rejected(client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_mb=0.001)  # ~1 KB
    pdf = make_pdf(["x" * 3000])

    response = await client.post("/documents", files={"file": ("big.pdf", pdf, "application/pdf")})

    assert response.status_code == 413


async def test_invalid_doc_type_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/documents",
        files={"file": ("a.pdf", make_pdf(["hi"]), "application/pdf")},
        data={"doc_type": "memo"},
    )

    assert response.status_code == 422
