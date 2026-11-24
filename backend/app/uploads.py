from contextlib import asynccontextmanager

from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile

MAX_FILE_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def one_file_form(
    request: Request, *, file_limit: int = MAX_FILE_BYTES, field_limit: int = 16 * 1024
):
    if (
        request.headers.get("content-type", "").split(";", 1)[0]
        != "multipart/form-data"
    ):
        raise HTTPException(415, "Use a multipart form with one file")
    if "transfer-encoding" in request.headers:
        raise HTTPException(411, "Uploads must have a fixed Content-Length")
    try:
        length = int(request.headers.get("content-length", ""))
    except ValueError:
        raise HTTPException(411, "Content-Length is required for uploads") from None
    if not 0 < length <= file_limit + field_limit + 48 * 1024:
        raise HTTPException(413, "Upload exceeds the request size limit")
    async with request.form(
        max_files=1, max_fields=1, max_part_size=field_limit
    ) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(422, "Select one file to upload")
        name = upload.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not name or len(name) > 200 or not name.isprintable():
            raise HTTPException(422, "Invalid attachment filename")
        content = await upload.read(file_limit + 1)
        if len(content) > file_limit:
            raise HTTPException(413, "Files are limited to 5 MiB")
        yield name, content, form
