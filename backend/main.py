from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from dq_checker.batch import run_db_batch
from dq_checker.core import SellerFileSpec
from dq_checker.db import DbCredentials, load_clients


ROOT = Path(__file__).resolve().parents[1]
APP_VERSION = os.getenv("RENDER_GIT_COMMIT", os.getenv("VERCEL_GIT_COMMIT_SHA", "local"))[:12]


def _writable_output_dir() -> Path:
    candidates = [
        Path(os.getenv("DQ_OUTPUT_DIR", "")).expanduser() if os.getenv("DQ_OUTPUT_DIR") else None,
        Path(tempfile.gettempdir()) / "dq_outputs",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
            resolved.mkdir(parents=True, exist_ok=True)
            probe = tempfile.NamedTemporaryFile(dir=resolved, delete=True)
            probe.close()
            return resolved
        except OSError:
            continue
    raise RuntimeError("No writable output directory is available for generated reports.")


OUTPUTS = _writable_output_dir()


def _allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [item.strip() for item in raw.split(",") if item.strip()]


app = FastAPI(title="Data Quality Checker API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost(:[0-9]+)?|http://127\.0\.0\.1(:[0-9]+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/runtime")
def runtime() -> dict[str, str]:
    return {
        "status": "ok",
        "entrypoint": "backend/main.py",
        "version": APP_VERSION,
        "output_dir": str(OUTPUTS),
        "dq_output_dir_env": os.getenv("DQ_OUTPUT_DIR", ""),
    }


@app.get("/api/clients")
def clients() -> dict[str, list[str]]:
    return {"clients": list(load_clients().keys())}


def _save_upload(upload: UploadFile, upload_dir: Path) -> Path:
    filename = Path(upload.filename or "upload").name
    target = upload_dir / filename
    with target.open("wb") as handle:
        handle.write(upload.file.read())
    return target


@app.post("/api/batch-db")
async def batch_db(
    client: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    granularity: str = Form("day"),
    data_level: str = Form("sku"),
    mapping_json: str = Form(...),
    platform_files: list[UploadFile] = File(...),
) -> dict:
    import json

    upload_dir = Path(tempfile.mkdtemp(prefix="dq_checker_api_"))
    try:
        saved_by_name = {_file.filename: _save_upload(_file, upload_dir) for _file in platform_files if _file.filename}
        mapping = json.loads(mapping_json)
        specs: list[SellerFileSpec] = []
        for row in mapping:
            file_name = row.get("fileName", "")
            seller_id = (row.get("sellerId") or "").strip()
            if not file_name or not seller_id:
                raise HTTPException(status_code=400, detail="Every file needs a seller_id.")
            if file_name not in saved_by_name:
                raise HTTPException(status_code=400, detail=f"Uploaded file not found in mapping: {file_name}")
            specs.append(
                SellerFileSpec(
                    file_path=saved_by_name[file_name],
                    seller_id=seller_id,
                    marketplace=(row.get("marketplace") or "AUTO").upper(),
                    platform_sheet=(row.get("sheet") or "").strip() or None,
                    use_item_sales=bool(row.get("useItemSales")),
                )
            )

        result = run_db_batch(
            credentials=DbCredentials(client=client, username=username, password=password),
            specs=specs,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            output_dir=OUTPUTS,
            data_level=data_level,
        )
        report_name = Path(result["report_path"]).name
        result["report_name"] = report_name
        result["download_url"] = f"/api/download/{report_name}"
        result["api_version"] = APP_VERSION
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/download/{report_name}")
def download(report_name: str) -> FileResponse:
    safe_name = Path(report_name).name
    target = (OUTPUTS / safe_name).resolve()
    if not str(target).startswith(str(OUTPUTS)) or not target.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(
        target,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_name,
    )
