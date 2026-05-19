import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

JOBS = {
    "exchange": BASE_DIR / "send_messages_bot.py",
    "billing": BASE_DIR / "send_messages_cuoc.py",
    "refund": BASE_DIR / "send_messages_refund.py",
}

job_state = {
    key: {
        "status": "idle",
        "last_started_at": None,
        "last_finished_at": None,
        "last_exit_code": None,
        "last_output": "",
        "script": str(path.name),
    }
    for key, path in JOBS.items()
}

job_lock = threading.Lock()
active_job = {"name": None}

app = FastAPI(title="SunShine Message Control API")

allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
allow_all_origins = "*" in allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else (allowed_origins or ["*"]),
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunJobResponse(BaseModel):
    message: str
    job: str
    status: str


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_script(job_name: str) -> None:
    script_path = JOBS[job_name]
    state = job_state[job_name]
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        state["status"] = "succeeded" if completed.returncode == 0 else "failed"
        state["last_exit_code"] = completed.returncode
        state["last_output"] = output[-12000:]
    except Exception as exc:
        state["status"] = "failed"
        state["last_exit_code"] = -1
        state["last_output"] = f"{type(exc).__name__}: {exc}"
    finally:
        state["last_finished_at"] = utc_now_iso()
        with job_lock:
            active_job["name"] = None


@app.get("/api/health")
def health():
    return {"status": "ok", "active_job": active_job["name"]}


@app.get("/api/jobs")
def get_jobs():
    return {"jobs": job_state}


@app.post("/api/jobs/{job_name}/run", response_model=RunJobResponse)
def start_job(job_name: str):
    if job_name not in JOBS:
        raise HTTPException(status_code=404, detail="Job không tồn tại")

    if not JOBS[job_name].exists():
        raise HTTPException(status_code=500, detail=f"Không tìm thấy file {JOBS[job_name].name}")

    with job_lock:
        if active_job["name"] is not None:
            raise HTTPException(status_code=409, detail=f"Đang chạy job {active_job['name']}, hãy chờ xong rồi chạy tiếp")
        active_job["name"] = job_name

    state = job_state[job_name]
    state["status"] = "running"
    state["last_started_at"] = utc_now_iso()
    state["last_finished_at"] = None
    state["last_exit_code"] = None
    state["last_output"] = ""

    worker = threading.Thread(target=run_script, args=(job_name,), daemon=True)
    worker.start()

    return RunJobResponse(
        message=f"Đã bắt đầu chạy {job_name}",
        job=job_name,
        status=state["status"],
    )
