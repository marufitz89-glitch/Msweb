import os
import re
import json
import uuid
import shutil
import zipfile
from pathlib import Path
from typing import Optional

import httpx

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


# =========================================================
# MSWEB CONFIG
# =========================================================

APP_NAME = "MSWEB"
APP_VERSION = "2.1.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
UPLOADS_DIR = DATA_DIR / "uploads"
EXPORTS_DIR = DATA_DIR / "exports"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# BUILD WORKER CONFIG
# =========================================================

BUILD_WORKER_URL = os.getenv(
    "BUILD_WORKER_URL",
    ""
).rstrip("/")

MSWEB_WORKER_SECRET = os.getenv(
    "MSWEB_WORKER_SECRET",
    "")


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="MSWEB API",
    version=APP_VERSION,
    description="MSWEB App Builder Backend"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# MODELS
# =========================================================

class ProjectCreate(BaseModel):
    name: str = Field(
        default="My MSWEB App",
        min_length=1,
        max_length=100
    )


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        max_length=100
    )

    html: Optional[str] = Field(
        default=None,
        max_length=5_000_000
    )

    css: Optional[str] = Field(
        default=None,
        max_length=5_000_000
    )

    js: Optional[str] = Field(
        default=None,
        max_length=5_000_000
    )


class PageCreate(BaseModel):
    name: str = Field(
        default="New Page",
        min_length=1,
        max_length=100
    )


class APKBuildRequest(BaseModel):
    app_name: str = Field(
        default="MSWEB App",
        min_length=1,
        max_length=50
    )

    package_name: str = Field(
        default="com.msweb.app",
        min_length=3,
        max_length=100
    )

    version_name: str = Field(
        default="1.0.0",
        min_length=1,
        max_length=30
    )

    version_code: int = Field(
        default=1,
        ge=1,
        le=2147483647
    )

    html: str = Field(
        default="",
        max_length=5_000_000
    )

    css: str = Field(
        default="",
        max_length=5_000_000
    )

    js: str = Field(
        default="",
        max_length=5_000_000
    )


# =========================================================
# HELPERS
# =========================================================

def project_file(project_id: str) -> Path:
    if not re.fullmatch(
        r"^[a-f0-9]{32}$",
        project_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID."
        )

    return PROJECTS_DIR / f"{project_id}.json"


def load_project(project_id: str) -> dict:
    path = project_file(project_id)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project not found."
        )

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Project data is corrupted."
        )


def save_project(project: dict):
    path = project_file(
        project["id"]
    )

    path.write_text(
        json.dumps(
            project,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def clean_filename(filename: str) -> str:
    filename = Path(
        filename or "file"
    ).name

    filename = re.sub(
        r"[^a-zA-Z0-9._-]",
        "_",
        filename
    )

    return filename[:150]


def create_default_project(
    project_id: str,
    name: str
) -> dict:

    return {
        "id": project_id,
        "name": name.strip() or "My MSWEB App",
        "version": 1,
        "created_at": __import__("datetime")
            .datetime.utcnow()
            .isoformat(),
        "updated_at": __import__("datetime")
            .datetime.utcnow()
            .isoformat(),

        "html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>MSWEB App</title>
</head>

<body>

    <main>
        <h1>Welcome to MSWEB</h1>
        <p>Start building your app.</p>
    </main>

</body>
</html>
""",

        "css": """* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    font-family: Arial, sans-serif;
    background: #0f172a;
    color: white;
}

main {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 24px;
}
""",

        "js": """document.addEventListener(
    "DOMContentLoaded",
    () => {
        console.log("MSWEB app loaded");
    }
);
""",

        "pages": [
            {
                "id": "home",
                "name": "Home",
                "path": "index.html"
            }
        ]
    }


# =========================================================
# ROOT / HEALTH
# =========================================================

@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "message": "MSWEB backend is running"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "msweb-main-api",
        "build_worker_configured": bool(
            BUILD_WORKER_URL
        )
    }


@app.get("/api/health")
async def api_health():
    return {
        "status": "online",
        "version": APP_VERSION,
        "build_worker": bool(
            BUILD_WORKER_URL
        )
    }


# =========================================================
# PROJECT CREATE
# =========================================================

@app.post("/api/projects")
async def create_project(
    request: ProjectCreate
):

    project_id = uuid.uuid4().hex

    project = create_default_project(
        project_id,
        request.name
    )

    save_project(project)

    return {
        "success": True,
        "project": project
    }


# =========================================================
# PROJECT LIST
# =========================================================

@app.get("/api/projects")
async def list_projects():

    projects = []

    for file in PROJECTS_DIR.glob("*.json"):

        try:
            project = json.loads(
                file.read_text(
                    encoding="utf-8"
                )
            )

            projects.append({
                "id": project.get("id"),
                "name": project.get("name"),
                "version": project.get(
                    "version",
                    1
                ),
                "created_at": project.get(
                    "created_at"
                ),
                "updated_at": project.get(
                    "updated_at"
                )
            })

        except Exception:
            continue

    projects.sort(
        key=lambda x: x.get(
            "updated_at",
            ""
        ),
        reverse=True
    )

    return {
        "success": True,
        "projects": projects
    }


# =========================================================
# GET PROJECT
# =========================================================

@app.get("/api/projects/{project_id}")
async def get_project(
    project_id: str
):

    project = load_project(
        project_id
    )

    return {
        "success": True,
        "project": project
    }


# =========================================================
# UPDATE PROJECT
# =========================================================

@app.put("/api/projects/{project_id}")
async def update_project(
    project_id: str,
    request: ProjectUpdate
):

    project = load_project(
        project_id
    )

    if request.name is not None:
        project["name"] = (
            request.name.strip()
            or project["name"]
        )

    if request.html is not None:
        project["html"] = request.html

    if request.css is not None:
        project["css"] = request.css

    if request.js is not None:
        project["js"] = request.js

    project["version"] = (
        project.get("version", 1) + 1
    )

    project["updated_at"] = (
        __import__("datetime")
        .datetime.utcnow()
        .isoformat()
    )

    save_project(project)

    return {
        "success": True,
        "project": project
    }


# =========================================================
# DELETE PROJECT
# =========================================================

@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str
):

    path = project_file(
        project_id
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project not found."
        )

    path.unlink()

    return {
        "success": True,
        "message": "Project deleted."
    }


# =========================================================
# CREATE PAGE
# =========================================================

@app.post(
    "/api/projects/{project_id}/pages"
)
async def create_page(
    project_id: str,
    request: PageCreate
):

    project = load_project(
        project_id
    )

    page_id = uuid.uuid4().hex[:12]

    page = {
        "id": page_id,
        "name": request.name.strip()
            or "New Page",
        "path": f"{page_id}.html"
    }

    if "pages" not in project:
        project["pages"] = []

    project["pages"].append(page)

    project["updated_at"] = (
        __import__("datetime")
        .datetime.utcnow()
        .isoformat()
    )

    save_project(project)

    return {
        "success": True,
        "page": page,
        "project": project
    }


# =========================================================
# IMPORT HTML / CSS / JS
# =========================================================

@app.post("/api/import")
async def import_files(
    files: list[UploadFile] = File(...)
):

    imported = {
        "html": "",
        "css": "",
        "js": "",
        "files": []
    }

    allowed = {
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".js": "js"
    }

    for upload in files:

        filename = clean_filename(
            upload.filename
        )

        extension = Path(
            filename
        ).suffix.lower()

        if extension not in allowed:
            continue

        data = await upload.read()

        if len(data) > 5_000_000:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{filename} is too large."
                )
            )

        try:
            content = data.decode(
                "utf-8"
            )
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{filename} must be UTF-8 text."
                )
            )

        key = allowed[extension]

        imported[key] += (
            "\n" + content
        )

        imported["files"].append(
            filename
        )

    if not imported["files"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid HTML, CSS or JS "
                "files were uploaded."
            )
        )

    return {
        "success": True,
        "imported": imported
    }


# =========================================================
# IMPORT ZIP
# =========================================================

@app.post("/api/import/zip")
async def import_zip(
    file: UploadFile = File(...)
):

    filename = clean_filename(
        file.filename
    )

    if not filename.lower().endswith(
        ".zip"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only ZIP files are allowed."
        )

    data = await file.read()

    if len(data) > 25_000_000:
        raise HTTPException(
            status_code=413,
            detail="ZIP file is too large."
        )

    temp_zip = (
        UPLOADS_DIR
        / f"{uuid.uuid4().hex}.zip"
    )

    temp_zip.write_bytes(data)

    extracted_dir = (
        UPLOADS_DIR
        / uuid.uuid4().hex
    )

    extracted_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    try:

        with zipfile.ZipFile(
            temp_zip,
            "r"
        ) as archive:

            for info in archive.infolist():

                member = Path(
                    info.filename
                )

                if member.is_absolute():
                    raise HTTPException(
                        status_code=400,
                        detail="Unsafe ZIP file."
                    )

                if ".." in member.parts:
                    raise HTTPException(
                        status_code=400,
                        detail="Unsafe ZIP file."
                    )

            archive.extractall(
                extracted_dir
            )

        found = {
            "html": [],
            "css": [],
            "js": []
        }

        for path in extracted_dir.rglob("*"):

            if not path.is_file():
                continue

            ext = path.suffix.lower()

            if ext in (
                ".html",
                ".htm"
            ):
                found["html"].append(
                    str(path.relative_to(
                        extracted_dir
                    ))
                )

            elif ext == ".css":
                found["css"].append(
                    str(path.relative_to(
                        extracted_dir
                    ))
                )

            elif ext == ".js":
                found["js"].append(
                    str(path.relative_to(
                        extracted_dir
                    ))
                )

        return {
            "success": True,
            "files": found
        }

    finally:

        temp_zip.unlink(
            missing_ok=True
        )

        shutil.rmtree(
            extracted_dir,
            ignore_errors=True
        )


# =========================================================
# EXPORT PROJECT
# =========================================================

@app.get(
    "/api/projects/{project_id}/export"
)
async def export_project(
    project_id: str
):

    project = load_project(
        project_id
    )

    export_id = uuid.uuid4().hex

    zip_path = (
        EXPORTS_DIR
        / f"{export_id}.zip"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:

        archive.writestr(
            "index.html",
            project.get(
                "html",
                ""
            )
        )

        archive.writestr(
            "style.css",
            project.get(
                "css",
                ""
            )
        )

        archive.writestr(
            "app.js",
            project.get(
                "js",
                ""
            )
        )

        archive.writestr(
            "msweb-project.json",
            json.dumps(
                project,
                indent=2,
                ensure_ascii=False
            )
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=(
            f"{project.get('name', 'MSWEB-App')}.zip"
        )
    )


# =========================================================
# BUILD APK
# =========================================================

@app.post("/api/build")
async def build_apk(
    request: APKBuildRequest
):

    if not BUILD_WORKER_URL:
        raise HTTPException(
            status_code=503,
            detail=(
                "APK build worker is not configured."
            )
        )

    if not MSWEB_WORKER_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Build worker secret is not configured."
            )
        )

    payload = {
        "app_name": request.app_name,
        "package_name": request.package_name,
        "version_name": request.version_name,
        "version_code": request.version_code,
        "html": request.html,
        "css": request.css,
        "js": request.js
    }

    headers = {
        "X-MSWEB-Secret": MSWEB_WORKER_SECRET
    }

    timeout = httpx.Timeout(
        connect=20.0,
        read=920.0,
        write=30.0,
        pool=30.0
    )

    try:

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:

            response = await client.post(
                f"{BUILD_WORKER_URL}/build",
                json=payload,
                headers=headers
            )

        if response.status_code != 200:

            try:
                worker_error = (
                    response.json()
                )
            except Exception:
                worker_error = response.text

            raise HTTPException(
                status_code=502,
                detail={
                    "message": (
                        "Build worker returned "
                        "an error."
                    ),
                    "worker": worker_error
                }
            )

        result = response.json()

        if not result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=(
                    "APK build failed."
                )
            )

        build_id = result.get(
            "build_id"
        )

        return {
            "success": True,
            "build_id": build_id,
            "status": result.get(
                "status",
                "completed"
            ),
            "worker_download": result.get(
                "file"
            ),
            "message": (
                "APK build completed."
            )
        }

    except HTTPException:
        raise

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=(
                "APK build timed out."
            )
        )

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Build worker unavailable: {exc}"
            )
        )


# =========================================================
# BUILD WORKER HEALTH
# =========================================================

@app.get("/api/build/health")
async def build_worker_health():

    if not BUILD_WORKER_URL:
        return {
            "configured": False,
            "status": "not_configured"
        }

    try:

        async with httpx.AsyncClient(
            timeout=15
        ) as client:

            response = await client.get(
                f"{BUILD_WORKER_URL}/health"
            )

        if response.status_code != 200:
            return {
                "configured": True,
                "status": "worker_error"
            }

        return {
            "configured": True,
            "status": "online",
            "worker": response.json()
        }

    except Exception as exc:

        return {
            "configured": True,
            "status": "offline",
            "error": str(exc)
        }


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )