import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from core.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE, UPLOAD_DIR
from core.exceptions import AppException
from schemas.file import FileResponse

logger = logging.getLogger(__name__)


def save_uploaded_file(file: UploadFile, *, purpose: str = "file") -> FileResponse:
    """分块保存上传文件；失败时清理本次创建的文件，不泄露磁盘路径。"""
    # 浏览器可能传入 Windows 路径，在 Unix 上也需要去掉反斜杠前的目录。
    origin_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not origin_name or origin_name in {".", ".."}:
        raise AppException(code=4000, message="文件名不能为空", status_code=400)

    ext = Path(origin_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AppException(
            code=4150, message=f"不支持的文件后缀：{ext}", status_code=415
        )

    limit = MAX_UPLOAD_SIZE
    if purpose == "avatar":
        limit = 5 * 1024 * 1024
        signature = file.file.read(32)
        file.file.seek(0)
        is_png = ext == ".png" and file.content_type == "image/png" and signature.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpeg = ext in {".jpg", ".jpeg"} and file.content_type == "image/jpeg" and signature.startswith(b"\xff\xd8\xff")
        if not (is_png or is_jpeg):
            raise AppException(code=4150, message="头像仅支持 JPG 或 PNG 图片", status_code=415)

    # 使用服务端生成的完整 UUID，不将客户端文件名用于磁盘路径。
    disk_name = f"{uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / disk_name
    total_size = 0
    created = False
    try:
        # 排他创建防止覆盖已有文件；只有本次创建的文件才能被清理。
        with save_path.open("xb") as destination:
            created = True
            while chunk := file.file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > limit:
                    raise AppException(
                        code=4130,
                        message=f"文件不能超过 {limit // 1024 // 1024}MB",
                        status_code=413,
                    )
                destination.write(chunk)
            if total_size == 0:
                raise AppException(code=4000, message="不能上传空文件", status_code=400)
    except Exception as error:
        # 离开 with 后文件已关闭，避免在 Windows 上删除仍打开的文件。
        if created:
            try:
                save_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("清理上传文件失败")
        if isinstance(error, AppException):
            raise
        logger.exception("文件上传失败")
        raise AppException(
            code=5000, message="文件上传失败，请稍后重试", status_code=500
        ) from error

    return FileResponse(
        origin_name=origin_name,
        disk_name=disk_name,
        size=total_size,
        url=f"/uploads/{disk_name}",
    )
