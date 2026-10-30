from __future__ import annotations

import hashlib
import re
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request


todo_bp = Blueprint("jaydream_todo", __name__)

BASE_DIR = Path(__file__).resolve().parent
MEMORY_FILE = BASE_DIR / "memory.txt"
MEMORY_LOCK = threading.RLock()
WIB = ZoneInfo("Asia/Jakarta")

# Tetap kompatibel dengan format JayDream lama:
# [MEMORY] 24/05/2024|23:59|WIB|Selesai catatan TKA kelas 9
# Task yang selesai dipindahkan menjadi [DONE_MEMORY].
MEMORY_RE = re.compile(
    r"^\[(MEMORY|DONE_MEMORY)\]\s*"
    r"(\d{2}/\d{2}/\d{4})\|"
    r"(\d{2}:\d{2})\|"
    r"WIB\|"
    r"(.+?)\s*$"
)


def _ensure_file() -> None:
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text("", encoding="utf-8")


def _read_lines() -> list[str]:
    _ensure_file()
    return MEMORY_FILE.read_text(encoding="utf-8").splitlines()


def _write_lines(lines: list[str]) -> None:
    text = "\n".join(lines)
    if lines:
        text += "\n"
    temp = MEMORY_FILE.with_suffix(".txt.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(MEMORY_FILE)


def _todo_id(line: str) -> str:
    return hashlib.sha1(line.encode("utf-8")).hexdigest()[:16]


def _parse_line(line: str):
    match = MEMORY_RE.match(line.strip())
    if not match:
        return None

    kind, date_text, time_text, task = match.groups()
    try:
        parsed_date = datetime.strptime(date_text, "%d/%m/%Y")
    except ValueError:
        return None

    return {
        "id": _todo_id(line),
        "date": date_text,
        "iso_date": parsed_date.strftime("%Y-%m-%d"),
        "time": time_text,
        "timezone": "WIB",
        "task": task.strip(),
        "done": kind == "DONE_MEMORY",
        "progress": "DONE" if kind == "DONE_MEMORY" else "PENDING",
        "raw": line,
    }


def _all_todos(lines: list[str]) -> list[dict]:
    todos = []
    for line in lines:
        item = _parse_line(line)
        if item:
            todos.append(item)

    # Pending: tanggal/waktu naik. Done: paling bawah.
    todos.sort(
        key=lambda item: (
            item["done"],
            item["iso_date"],
            item["time"],
            item["task"].lower(),
        )
    )
    return todos


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%d/%m/%Y")
        return True
    except (TypeError, ValueError):
        return False


def _valid_time(value: str) -> bool:
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except (TypeError, ValueError):
        return False


def _clean_task(value) -> str:
    task = str(value or "").strip().replace("\n", " ").replace("\r", " ")
    # Pipe dipakai sebagai separator memory.txt, jadi jangan izinkan di task.
    task = task.replace("|", "/")
    return task[:300]


@todo_bp.get("/api/todos")
def get_todos():
    with MEMORY_LOCK:
        lines = _read_lines()
        todos = _all_todos(lines)

    now = datetime.now(WIB)
    return jsonify(
        {
            "todos": todos,
            "count": len(todos),
            "today": now.strftime("%Y-%m-%d"),
            "source": "memory.txt",
        }
    )


@todo_bp.post("/api/todos")
def create_todo():
    data = request.get_json(silent=True) or {}
    date_text = str(data.get("date") or "").strip()
    time_text = str(data.get("time") or "23:59").strip()
    task = _clean_task(data.get("task"))

    if not _valid_date(date_text):
        return jsonify({"error": "Format tanggal harus DD/MM/YYYY"}), 400
    if not _valid_time(time_text):
        return jsonify({"error": "Format waktu harus HH:MM"}), 400
    if not task:
        return jsonify({"error": "Task tidak boleh kosong"}), 400

    new_line = f"[MEMORY] {date_text}|{time_text}|WIB|{task}"

    with MEMORY_LOCK:
        lines = _read_lines()
        lines.append(new_line)
        _write_lines(lines)

    return jsonify({"success": True, "todo": _parse_line(new_line)}), 201


@todo_bp.patch("/api/todos/<todo_id>")
def update_todo(todo_id: str):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()

    with MEMORY_LOCK:
        lines = _read_lines()
        target_index = None
        target = None

        for index, line in enumerate(lines):
            item = _parse_line(line)
            if item and item["id"] == todo_id:
                target_index = index
                target = item
                break

        if target_index is None or target is None:
            return jsonify({"error": "Task tidak ditemukan. Coba refresh TDL."}), 404

        date_text = target["date"]
        time_text = target["time"]
        task = target["task"]
        done = target["done"]

        if action == "done":
            done = True
        elif action == "undo":
            done = False
        elif action == "edit":
            if "task" in data:
                task = _clean_task(data.get("task"))
                if not task:
                    return jsonify({"error": "Task tidak boleh kosong"}), 400

            if "date" in data:
                candidate = str(data.get("date") or "").strip()
                if not _valid_date(candidate):
                    return jsonify({"error": "Format tanggal harus DD/MM/YYYY"}), 400
                date_text = candidate

            if "time" in data:
                candidate = str(data.get("time") or "").strip()
                if not _valid_time(candidate):
                    return jsonify({"error": "Format waktu harus HH:MM"}), 400
                time_text = candidate
        else:
            return jsonify({"error": "Action harus done, undo, atau edit"}), 400

        prefix = "DONE_MEMORY" if done else "MEMORY"
        updated_line = f"[{prefix}] {date_text}|{time_text}|WIB|{task}"
        lines[target_index] = updated_line
        _write_lines(lines)

    return jsonify({"success": True, "todo": _parse_line(updated_line)})
