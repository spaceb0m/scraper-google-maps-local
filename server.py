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
HISTORY_PATH = BASE_DIR / "out" / "history.json"


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


def _load_history() -> None:
    """Carga el historial de ejecuciones desde disco al arrancar el servidor."""
    if not HISTORY_PATH.exists():
        return
    try:
        entries = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        for entry in entries:
            jobs[entry["job_id"]] = {
                "city": entry.get("city", ""),
                "category": entry.get("category", ""),
                "started_at": entry.get("started_at", ""),
                "status": entry.get("status", "done"),
                "valid_count": entry.get("valid_count", 0),
                "output": entry.get("output", ""),
                "lines": [],
                "proc": None,
            }
    except Exception:
        pass  # fichero corrupto — arrancar sin historial


def _save_history() -> None:
    """Persiste el historial de ejecuciones a disco."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "job_id": jid,
            "city": j.get("city", ""),
            "category": j.get("category", ""),
            "started_at": j.get("started_at", ""),
            "status": j["status"],
            "valid_count": j.get("valid_count", 0),
            "output": j.get("output", ""),
        }
        for jid, j in jobs.items()
        if j.get("started_at")
    ]
    HISTORY_PATH.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_load_history()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((BASE_DIR / "static" / "index.html").read_text(encoding="utf-8"))


@app.post("/run")
async def run_scraper(
    city: str = Form(...),
    category: str = Form(...),
    headless: str = Form("true"),
    max_results: int = Form(0),
    slow_ms: int = Form(250),
    timeout_ms: int = Form(15000),
    concurrency: int = Form(3),
    adaptive_subdivision: str = Form("false"),
) -> dict:
    job_id = str(uuid.uuid4())
    output = _make_output_path(city, category)
    jobs[job_id] = {
        "city": city,
        "category": category,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "valid_count": 0,
        "output": output,
        "lines": [],
        "proc": None,
    }

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
        "--adaptive-subdivision", adaptive_subdivision,
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
            m = re.search(r"valid=(\d+)", line)
            if m:
                jobs[job_id]["valid_count"] = int(m.group(1))
        await proc.wait()
        if jobs[job_id]["status"] != "stopped":
            jobs[job_id]["status"] = "done" if proc.returncode == 0 else "error"
        _save_history()

    asyncio.create_task(run())
    return {"job_id": job_id, "output": output}


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
    _save_history()
    return {"status": "stopped"}


@app.get("/download/{job_id}")
async def download(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job:
        return FileResponse("/dev/null")  # fallback; should not happen
    output_path = BASE_DIR / job["output"]
    return FileResponse(str(output_path), filename=output_path.name, media_type="text/csv")
