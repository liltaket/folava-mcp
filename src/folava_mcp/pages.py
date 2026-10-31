"""Select page bodies through the reviewed collection route only."""

from __future__ import annotations

from .client import CanvasError
from .policy import PolicyError, operation_path


async def read_page(client, course_id: str, page_url: str, max_pages: int) -> dict:
    try:
        # Reuse the identifier policy without enabling a page-detail request.
        operation_path("page_revisions", {"course_id": course_id, "page_url": page_url})
        if type(max_pages) is not int or not 1 <= max_pages <= 20:
            raise PolicyError("max_pages must be between 1 and 20.")
    except PolicyError as error:
        raise CanvasError("policy", str(error)) from None

    result = await client.read(
        "pages",
        {"course_id": course_id},
        {"include[]": ["body"], "per_page": 20},
        max_pages=max_pages,
    )
    if not isinstance(result.get("data"), list):
        raise CanvasError("upstream", "Canvas returned an invalid page collection.")
    for page in result["data"]:
        if not isinstance(page, dict) or page.get("url") != page_url:
            continue
        output = {key: value for key, value in result.items() if key not in ("data", "next_url")}
        output.update(data=page, collection_complete=result.get("complete", False), complete=True)
        if not isinstance(page.get("body"), str):
            output.update(
                complete=False,
                error={
                    "code": "page_body_unavailable",
                    "message": "Canvas listed this page but did not supply its body. "
                    "The deployment may not support body includes; no detail URL was opened.",
                },
            )
        return output
    if not result.get("complete", False):
        raise CanvasError(
            "page_search_incomplete",
            "Page was not found within the collection limit. Increase max_pages or use "
            "canvas_read with pages and pagination; this does not establish that it is missing.",
        )
    raise CanvasError("not_found", "Page was not listed among the accessible course pages.")
