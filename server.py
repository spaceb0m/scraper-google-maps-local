from __future__ import annotations

import asyncio
import json
import platform
import re
import subprocess
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

app = FastAPI(title="Google Maps Scraper")

BASE_DIR = Path(__file__).parent


def _slugify(text: str) -> str:
    """Convierte texto a slug ASCII seguro para nombres de fichero."""
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lower = ascii_text.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", lower)
    slug = slug.strip("_")
    return slug[:40]


def _make_output_path(city: str, category: str) -> str:
    """Genera una ruta única para el CSV basada en ciudad, categoría y timestamp."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"out/{_slugify(city)}_{_slugify(category)}_{ts}.csv"


# job_id -> {"lines": [...], "status": "running"|"done"|"error"|"stopped", "output": str, "proc": Process|None}
jobs: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((BASE_DIR / "static" / "index.html").read_text(encoding="utf-8"))


@app.post("/run")
async def run_scraper(
    city: str = Form(...),
    category: str = Form(...),
    output: str = Form(...),
    headless: str = Form("true"),
    max_results: int = Form(0),
    slow_ms: int = Form(250),
    timeout_ms: int = Form(15000),
    concurrency: int = Form(3),
) -> dict:
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"lines": [], "status": "running", "output": output, "proc": None}

    cmd = [
        sys.executable, "-u", "-m", "src.cli",
        "--city", city,
        "--category", category,
        "--output", output,
        "--headless", headless,
        "--max-results", str(max_results),
        "--slow-ms", str(slow_ms),
        "--timeout-ms", str(timeout_ms),
        "--concurrency", str(concurrency),
    ]

    async def run() -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )
        jobs[job_id]["proc"] = proc
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            jobs[job_id]["lines"].append(line)
        await proc.wait()
        if jobs[job_id]["status"] != "stopped":
            jobs[job_id]["status"] = "done" if proc.returncode == 0 else "error"

    asyncio.create_task(run())
    return {"job_id": job_id}


@app.get("/stream/{job_id}")
async def stream(job_id: str) -> StreamingResponse:
    if job_id not in jobs:
        async def not_found():
            yield "data: Job no encontrado\n\nevent: done\ndata: error\n\n"
        return StreamingResponse(not_found(), media_type="text/event-stream")

    async def event_generator():
        sent = 0
        while True:
            job = jobs[job_id]
            lines = job["lines"]
            while sent < len(lines):
                # Escape newlines within the log line so SSE stays valid
                safe = lines[sent].replace("\n", " ")
                yield f"data: {safe}\n\n"
                sent += 1
            if job["status"] != "running":
                yield f"event: done\ndata: {job['status']}\n\n"
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/stop/{job_id}")
async def stop_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        return {"error": "not found"}
    if job["status"] != "running":
        return {"status": job["status"]}
    job["status"] = "stopped"
    proc = job.get("proc")
    if proc and proc.returncode is None:
        proc.terminate()
    return {"status": "stopped"}


@app.get("/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job:
        return FileResponse("/dev/null")  # fallback; should not happen
    output_path = BASE_DIR / job["output"]
    return FileResponse(str(output_path), filename=output_path.name, media_type="text/csv")
