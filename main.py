from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import json
import re
import shutil
import tempfile
import zipfile
import uuid

# ============================================================
# MSWEB BACKEND
# ============================================================

APP_NAME = "MSWEB"
VERSION = "2.0.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
EXPORTS_DIR = DATA_DIR / "exports"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="MSWEB API",
    description="Backend API for MSWEB Ultimate Web App Builder",
    version=VERSION
)

# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production-এ নিজের frontend domain দিন
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MODELS
# ============================================================

class Page(BaseModel):
    name: str = "Home"
    html: str = ""
    css: str = ""
    js: str = ""


class ProjectCreate(BaseModel):
    name: str = Field(default="Untitled Project", min_length=1, max_length=100)
    pages: Dict[str, Page] = {}


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    pages: Optional[Dict[str, Page]] = None
    current: Optional[str] = None


class Project(BaseModel):
    id: str
    name: str
    pages: Dict[str, Page]
    current: str
    created_at: str
    updated_at: str


# ============================================================
# HELPERS
# ============================================================

def safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_\- ]+", "", value)
    value = value.strip().replace(" ", "-")
    return value[:80] or "project"


def project_file(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def load_project(project_id: str) -> dict:
    path = project_file(project_id)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Project data is corrupted"
        )


def save_project(data: dict) -> None:
    path = project_file(data["id"])

    temp_path = path.with_suffix(".tmp")

    temp_path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    temp_path.replace(path)


def create_default_page() -> Dict[str, Page]:
    return {
        "home": Page(
            name="Home",
            html="",
            css="",
            js=""
        )
    }


def validate_page_id(page_id: str):
    if not re.fullmatch(r"[a-zA-Z0-9_\-]{1,80}", page_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid page ID"
        )


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "name": APP_NAME,
        "version": VERSION,
        "status": "online",
        "message": "MSWEB backend is running"
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": VERSION,
        "time": datetime.utcnow().isoformat() + "Z"
    }


# ============================================================
# PROJECT CREATE
# ============================================================

@app.post("/api/projects")
def create_project(payload: ProjectCreate):

    project_id = str(uuid.uuid4())

    pages = payload.pages

    if not pages:
        pages = create_default_page()

    current = next(iter(pages))

    now = datetime.utcnow().isoformat() + "Z"

    project = {
        "id": project_id,
        "name": payload.name.strip(),
        "pages": {
            key: page.model_dump()
            for key, page in pages.items()
        },
        "current": current,
        "created_at": now,
        "updated_at": now
    }

    save_project(project)

    return {
        "success": True,
        "project": project
    }


# ============================================================
# LIST PROJECTS
# ============================================================

@app.get("/api/projects")
def list_projects():

    projects = []

    for path in PROJECTS_DIR.glob("*.json"):

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            projects.append({
                "id": data.get("id"),
                "name": data.get("name"),
                "current": data.get("current"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at")
            })

        except Exception:
            continue

    projects.sort(
        key=lambda x: x.get("updated_at") or "",
        reverse=True
    )

    return {
        "success": True,
        "count": len(projects),
        "projects": projects
    }


# ============================================================
# GET PROJECT
# ============================================================

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):

    project = load_project(project_id)

    return {
        "success": True,
        "project": project
    }


# ============================================================
# UPDATE PROJECT
# ============================================================

@app.put("/api/projects/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectUpdate
):

    project = load_project(project_id)

    if payload.name is not None:

        name = payload.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Project name cannot be empty"
            )

        project["name"] = name

    if payload.pages is not None:

        project["pages"] = {
            key: page.model_dump()
            for key, page in payload.pages.items()
        }

    if payload.current is not None:

        if payload.current not in project["pages"]:
            raise HTTPException(
                status_code=400,
                detail="Current page does not exist"
            )

        project["current"] = payload.current

    project["updated_at"] = (
        datetime.utcnow().isoformat() + "Z"
    )

    save_project(project)

    return {
        "success": True,
        "project": project
    }


# ============================================================
# DELETE PROJECT
# ============================================================

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):

    path = project_file(project_id)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    path.unlink()

    return {
        "success": True,
        "message": "Project deleted"
    }


# ============================================================
# ADD PAGE
# ============================================================

@app.post("/api/projects/{project_id}/pages/{page_id}")
def add_page(
    project_id: str,
    page_id: str,
    page: Page
):

    validate_page_id(page_id)

    project = load_project(project_id)

    if page_id in project["pages"]:
        raise HTTPException(
            status_code=409,
            detail="Page already exists"
        )

    project["pages"][page_id] = page.model_dump()

    project["updated_at"] = (
        datetime.utcnow().isoformat() + "Z"
    )

    save_project(project)

    return {
        "success": True,
        "page_id": page_id,
        "page": page.model_dump()
    }


# ============================================================
# GET PAGE
# ============================================================

@app.get("/api/projects/{project_id}/pages/{page_id}")
def get_page(
    project_id: str,
    page_id: str
):

    project = load_project(project_id)

    if page_id not in project["pages"]:
        raise HTTPException(
            status_code=404,
            detail="Page not found"
        )

    return {
        "success": True,
        "page_id": page_id,
        "page": project["pages"][page_id]
    }


# ============================================================
# UPDATE PAGE
# ============================================================

@app.put("/api/projects/{project_id}/pages/{page_id}")
def update_page(
    project_id: str,
    page_id: str,
    page: Page
):

    project = load_project(project_id)

    if page_id not in project["pages"]:
        raise HTTPException(
            status_code=404,
            detail="Page not found"
        )

    project["pages"][page_id] = page.model_dump()

    project["updated_at"] = (
        datetime.utcnow().isoformat() + "Z"
    )

    save_project(project)

    return {
        "success": True,
        "page_id": page_id,
        "page": page.model_dump()
    }


# ============================================================
# DELETE PAGE
# ============================================================

@app.delete("/api/projects/{project_id}/pages/{page_id}")
def delete_page(
    project_id: str,
    page_id: str
):

    project = load_project(project_id)

    if page_id not in project["pages"]:
        raise HTTPException(
            status_code=404,
            detail="Page not found"
        )

    if len(project["pages"]) <= 1:
        raise HTTPException(
            status_code=400,
            detail="A project must have at least one page"
        )

    del project["pages"][page_id]

    if project["current"] == page_id:
        project["current"] = next(
            iter(project["pages"])
        )

    project["updated_at"] = (
        datetime.utcnow().isoformat() + "Z"
    )

    save_project(project)

    return {
        "success": True,
        "message": "Page deleted",
        "current": project["current"]
    }


# ============================================================
# BUILD SINGLE PAGE
# ============================================================

def build_page(
    project: dict,
    page_id: str,
    output_dir: Path
):

    page = project["pages"][page_id]

    html = page.get("html", "")
    css = page.get("css", "")
    js = page.get("js", "")

    final_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1.0">

<title>{project["name"]}</title>

<style>
{css}
</style>

</head>

<body>

{html}

<script>
"use strict";

try {{
{js}
}} catch(error) {{
    console.error(error);
}}

</script>

</body>
</html>
"""

    filename = (
        "index.html"
        if page_id == "home"
        else f"{safe_name(page.get('name', page_id))}.html"
    )

    target = output_dir / filename

    target.write_text(
        final_html,
        encoding="utf-8"
    )

    return filename


# ============================================================
# BUILD PROJECT
# ============================================================

@app.post("/api/projects/{project_id}/build")
def build_project(project_id: str):

    project = load_project(project_id)

    build_id = str(uuid.uuid4())

    build_dir = EXPORTS_DIR / build_id

    build_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    try:

        files = []

        for page_id in project["pages"]:

            filename = build_page(
                project,
                page_id,
                build_dir
            )

            files.append(filename)

        manifest = {
            "name": project["name"],
            "project_id": project["id"],
            "generated_at":
                datetime.utcnow().isoformat()+"Z",
            "files": files
        }

        (build_dir / "msweb.json").write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        return {
            "success": True,
            "build_id": build_id,
            "files": files
        }

    except Exception as error:

        shutil.rmtree(
            build_dir,
            ignore_errors=True
        )

        raise HTTPException(
            status_code=500,
            detail=f"Build failed: {error}"
        )


# ============================================================
# ZIP EXPORT
# ============================================================

@app.post("/api/projects/{project_id}/export")
def export_project(project_id: str):

    project = load_project(project_id)

    export_id = str(uuid.uuid4())

    temp_dir = EXPORTS_DIR / export_id

    temp_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    try:

        files=[]

        for page_id in project["pages"]:

            filename=build_page(
                project,
                page_id,
                temp_dir
            )

            files.append(filename)

        manifest={
            "name":project["name"],
            "project_id":project["id"],
            "generated_at":
                datetime.utcnow().isoformat()+"Z",
            "files":files
        }

        (temp_dir/"msweb.json").write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        zip_path=EXPORTS_DIR / (
            safe_name(project["name"])
            +"-"
            +export_id[:8]
            +".zip"
        )

        with zipfile.ZipFile(
            zip_path,
            "w",
            zipfile.ZIP_DEFLATED
        ) as archive:

            for file in temp_dir.rglob("*"):

                if file.is_file():

                    archive.write(
                        file,
                        file.relative_to(temp_dir)
                    )

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        return FileResponse(
            path=zip_path,
            filename=zip_path.name,
            media_type="application/zip"
        )

    except Exception as error:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        raise HTTPException(
            status_code=500,
            detail=f"Export failed: {error}"
        )


# ============================================================
# IMPORT PROJECT JSON
# ============================================================

@app.post("/api/projects/import")
def import_project(payload: Dict[str, Any]):

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Invalid project data"
        )

    name = str(
        payload.get(
            "name",
            "Imported Project"
        )
    ).strip()

    pages = payload.get("pages")

    if not isinstance(pages, dict) or not pages:

        raise HTTPException(
            status_code=400,
            detail="Project must contain pages"
        )

    project_id=str(uuid.uuid4())

    now=datetime.utcnow().isoformat()+"Z"

    normalized_pages={}

    for page_id,page in pages.items():

        validate_page_id(str(page_id))

        if not isinstance(page,dict):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid page: {page_id}"
            )

        normalized_pages[str(page_id)]={
            "name":str(
                page.get(
                    "name",
                    page_id
                )
            ),
            "html":str(
                page.get(
                    "html",
                    ""
                )
            ),
            "css":str(
                page.get(
                    "css",
                    ""
                )
            ),
            "js":str(
                page.get(
                    "js",
                    ""
                )
            )
        }

    current=payload.get(
        "current",
        next(iter(normalized_pages))
    )

    if current not in normalized_pages:
        current=next(iter(normalized_pages))

    project={
        "id":project_id,
        "name":name[:100] or "Imported Project",
        "pages":normalized_pages,
        "current":current,
        "created_at":now,
        "updated_at":now
    }

    save_project(project)

    return {
        "success":True,
        "project":project
    }


# ============================================================
# GLOBAL ERROR HANDLER
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):

    return JSONResponse(
        status_code=500,
        content={
            "success":False,
            "error":"Internal server error"
        }
    )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
)
