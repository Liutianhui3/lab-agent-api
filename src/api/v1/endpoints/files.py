from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile

from schemas.response import BaseResponse
from schemas.file import FileResponse
from services.file_service import save_uploaded_file

router = APIRouter(prefix="/files", tags=["文件管理"])


@router.post("/upload", response_model=BaseResponse[FileResponse])
def upload(
    file: UploadFile = File(...),
    purpose: Literal["file", "avatar"] = Form(default="file"),
) -> BaseResponse[FileResponse]:
    """接收 multipart 文件，具体校验和保存逻辑交给 service 层。"""
    # UploadFile 由 FastAPI 在请求结束时关闭，无需在业务代码中重复管理。
    data = save_uploaded_file(file, purpose=purpose)
    return BaseResponse[FileResponse].success(data=data)
