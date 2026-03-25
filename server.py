from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

app = FastAPI(title="Google Maps Scraper")

BASE_DIR = Path(__file__).parent

# job_id -> {"lines": [...], "status": "running"|"done"|"error", "output": str}
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
    zones: Optional[str] = Form(None),
) -> dict:
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"lines": [], "status": "running", "output": output}

    cmd = [
        sys.executable, "-u", "-m", "src.cli",
        "--city", city,
        "--category", category,
        "--output", output,
        "--headless", headless,
        "--max-results", str(max_results),
        "--slow-ms", str(slow_ms),
        "--timeout-ms", str(timeout_ms),
    ]
    if zones and zones.strip():
        cmd += ["--zones", zones.strip()]

    async def run() -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
        )
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            jobs[job_id]["lines"].append(line)
        await proc.wait()
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


@app.get("/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job:
        return FileResponse("/dev/null")  # fallback; should not happen
    output_path = BASE_DIR / job["output"]
    return FileResponse(str(output_path), filename=output_path.name, media_type="text/csv")
