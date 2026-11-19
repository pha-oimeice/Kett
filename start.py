import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def stop_processes(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is not None:
            continue
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except OSError:
                kill_windows_tree(process)
        else:
            process.terminate()

    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                kill_windows_tree(process)
            process.kill()
            process.wait()


def kill_windows_tree(process: subprocess.Popen) -> None:
    # The Windows venv launcher can have a separate Python child process.
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main() -> int:
    node = shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not node:
        print("Node.js is required to start the frontend.", file=sys.stderr)
        return 1
    if not vite.is_file():
        print(
            "Frontend dependencies missing. Run: npm --prefix frontend ci",
            file=sys.stderr,
        )
        return 1

    venv = BACKEND / ".venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    backend_python = str(python) if python.is_file() else sys.executable
    commands = [
        (
            "FastAPI",
            BACKEND,
            [backend_python, "-m", "uvicorn", "app.main:app", "--port", "8000"],
        ),
        (
            "Vite",
            FRONTEND,
            [node, str(vite), "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
        ),
    ]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0

    stop_signal = 0

    def request_stop(signum, _frame):
        nonlocal stop_signal
        stop_signal = signum

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if os.name == "nt":
        signal.signal(signal.SIGBREAK, request_stop)

    processes: list[tuple[str, subprocess.Popen]] = []
    print(
        "Frontend: http://localhost:5173 | API docs: http://127.0.0.1:8000/docs",
        flush=True,
    )
    print("Press Ctrl+C to stop both services.", flush=True)
    try:
        for name, cwd, command in commands:
            if stop_signal:
                break
            process = subprocess.Popen(command, cwd=cwd, creationflags=creationflags)
            processes.append((name, process))
        while not stop_signal:
            for name, process in processes:
                status = process.poll()
                if status is not None and not stop_signal:
                    print(
                        f"{name} exited (status {status}); stopping the other service.",
                        file=sys.stderr,
                    )
                    return status if status > 0 else 1
            time.sleep(0.2)
        return 128 + stop_signal
    except OSError as error:
        print(f"Could not start the services: {error}", file=sys.stderr)
        return 1
    finally:
        stop_processes([process for _, process in processes])


if __name__ == "__main__":
    sys.exit(main())
