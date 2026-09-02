import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

import uvicorn


app = FastAPI(
    title="MSWEB APK Build Worker",
    version="1.0.0"
)


BUILD_ROOT = Path("/tmp/msweb-builds")
BUILD_ROOT.mkdir(parents=True, exist_ok=True)

WORKER_SECRET = os.getenv("MSWEB_WORKER_SECRET", "")

PACKAGE_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
)


class BuildRequest(BaseModel):
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
        max_length=30
    )

    version_code: int = Field(
        default=1,
        ge=1,
        le=2147483647
    )

    html: str = Field(
        default="",
        max_length=2_000_000
    )

    css: str = Field(
        default="",
        max_length=2_000_000
    )

    js: str = Field(
        default="",
        max_length=2_000_000
    )


def safe_app_name(name: str) -> str:
    name = name.strip()

    if not name:
        return "MSWEB App"

    return name[:50]


def validate_package(package_name: str):
    if not PACKAGE_PATTERN.fullmatch(package_name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid package name. "
                "Example: com.example.myapp"
            )
        )


def create_web_assets(
    project_dir: Path,
    html: str,
    css: str,
    js: str
):
    assets = (
        project_dir
        / "app"
        / "src"
        / "main"
        / "assets"
    )

    assets.mkdir(parents=True, exist_ok=True)

    # If HTML is empty, create a valid basic document.
    if not html.strip():
        html = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta
    name="viewport"
    content="width=device-width,initial-scale=1.0">
<title>MSWEB App</title>
</head>
<body>
<h1>MSWEB App</h1>
<p>Your application is ready.</p>
</body>
</html>
"""

    # Keep CSS and JS local.
    (assets / "index.html").write_text(
        html,
        encoding="utf-8"
    )

    (assets / "style.css").write_text(
        css,
        encoding="utf-8"
    )

    (assets / "app.js").write_text(
        js,
        encoding="utf-8"
    )


def create_android_project(
    root: Path,
    app_name: str,
    package_name: str,
    version_name: str,
    version_code: int,
    html: str,
    css: str,
    js: str
):
    package_path = package_name.replace(".", "/")

    app_dir = root / "app"
    main_dir = app_dir / "src" / "main"

    java_dir = main_dir / "java" / package_path
    res_dir = main_dir / "res" / "values"

    java_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    # settings.gradle
    (root / "settings.gradle").write_text(
        """pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(
        RepositoriesMode.FAIL_ON_PROJECT_REPOS
    )

    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "MSWEBApp"
include(":app")
""",
        encoding="utf-8"
    )

    # Root build.gradle
    (root / "build.gradle").write_text(
        """plugins {
    id 'com.android.application' version '8.6.1' apply false
}
""",
        encoding="utf-8"
    )

    # gradle.properties
    (root / "gradle.properties").write_text(
        """org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
android.useAndroidX=true
android.nonTransitiveRClass=true
""",
        encoding="utf-8"
    )

    # app/build.gradle
    (app_dir / "build.gradle").write_text(
        f"""plugins {{
    id 'com.android.application'
}}

android {{
    namespace '{package_name}'
    compileSdk 35

    defaultConfig {{
        applicationId '{package_name}'
        minSdk 23
        targetSdk 35
        versionCode {version_code}
        versionName '{version_name}'
    }}

    buildTypes {{
        debug {{
            minifyEnabled false
        }}

        release {{
            minifyEnabled false
        }}
    }}
}}
""",
        encoding="utf-8"
    )

    # AndroidManifest.xml
    (main_dir / "AndroidManifest.xml").write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<manifest
    xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission
        android:name="android.permission.INTERNET" />

    <application
        android:theme="@style/AppTheme"
        android:label="{safe_app_name(app_name)}"
        android:allowBackup="false"
        android:supportsRtl="true">

        <activity
            android:name=".{Path(package_path).name}.MainActivity"
            android:exported="true">

            <intent-filter>
                <action
                    android:name="android.intent.action.MAIN" />

                <category
                    android:name="android.intent.category.LAUNCHER" />
            </intent-filter>

        </activity>

    </application>

</manifest>
""",
        encoding="utf-8"
    )

    # styles.xml
    (res_dir / "styles.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<resources>

    <style
        name="AppTheme"
        parent="android:style/Theme.Material.Light.NoActionBar">

        <item name="android:fontFamily">sans</item>
        <item name="android:windowActionModeOverlay">true</item>
        <item name="android:colorAccent">#6750A4</item>

    </style>

</resources>
""",
        encoding="utf-8"
    )

    # MainActivity.java
    activity_name = Path(package_path).name

    java_code = f"""package {package_name};

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {{

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);

        webView = new WebView(this);

        WebSettings settings = webView.getSettings();

        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);

        webView.setWebViewClient(new WebViewClient());

        webView.loadUrl(
            "file:///android_asset/index.html"
        );

        setContentView(webView);
    }}

    @Override
    public void onBackPressed() {{

        if (webView.canGoBack()) {{
            webView.goBack();
        }} else {{
            super.onBackPressed();
        }}
    }}
}}
"""

    (java_dir / "MainActivity.java").write_text(
        java_code,
        encoding="utf-8"
    )

    create_web_assets(
        root,
        html,
        css,
        js
    )


def run_gradle_build(root: Path):
    command = [
        "gradle",
        "--no-daemon",
        "--stacktrace",
        "assembleDebug"
    ]

    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=900
    )

    if result.returncode != 0:
        error = result.stderr[-8000:]

        if not error.strip():
            error = result.stdout[-8000:]

        raise RuntimeError(error)

    apk = (
        root
        / "app"
        / "build"
        / "outputs"
        / "apk"
        / "debug"
        / "app-debug.apk"
    )

    if not apk.exists():
        raise RuntimeError(
            "Gradle completed but APK was not found."
        )

    return apk


@app.get("/")
def root():
    return {
        "name": "MSWEB Build Worker",
        "version": "1.0.0",
        "status": "online"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "android_sdk": os.getenv(
            "ANDROID_HOME",
            ""
        ),
        "gradle": "8.7"
    }


@app.post("/build")
def build(
    request: BuildRequest,
    x_msweb_secret: str | None = Header(
        default=None
    )
):
    # Authentication is required only when
    # MSWEB_WORKER_SECRET is configured.
    if WORKER_SECRET:
        if x_msweb_secret != WORKER_SECRET:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized"
            )

    validate_package(request.package_name)

    build_id = uuid.uuid4().hex

    work_dir = Path(
        tempfile.mkdtemp(
            prefix=f"msweb-{build_id}-",
            dir="/tmp"
        )
    )

    try:
        create_android_project(
            root=work_dir,
            app_name=request.app_name,
            package_name=request.package_name,
            version_name=request.version_name,
            version_code=request.version_code,
            html=request.html,
            css=request.css,
            js=request.js
        )

        apk = run_gradle_build(work_dir)

        output_apk = BUILD_ROOT / f"{build_id}.apk"

        shutil.copy2(
            apk,
            output_apk
        )

        return {
            "success": True,
            "build_id": build_id,
            "status": "completed",
            "file": f"/download/{build_id}"
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="APK build timed out."
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"APK build failed: {str(exc)[-4000:]}"
        )

    finally:
        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


@app.get("/download/{build_id}")
def download_apk(build_id: str):
    from fastapi.responses import FileResponse

    if not re.fullmatch(
        r"^[a-f0-9]{32}$",
        build_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid build ID."
        )

    apk = BUILD_ROOT / f"{build_id}.apk"

    if not apk.exists():
        raise HTTPException(
            status_code=404,
            detail="APK not found."
        )

    return FileResponse(
        path=str(apk),
        media_type="application/vnd.android.package-archive",
        filename="MSWEB-App.apk"
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=10000
    )
