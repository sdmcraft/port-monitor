import functools
import os
import signal
import socket
import shutil
import subprocess
from typing import List, Dict, Tuple

from flask import Flask, jsonify, request, abort

app = Flask(__name__, static_folder="static", static_url_path="")

ASSIGNED_PORT_ENV = "PORTER_ASSIGNED_PORT"


class PortFetchError(RuntimeError):
    """Raised when the list of occupied ports cannot be retrieved."""


def _get_lsof_path() -> str:
    path = shutil.which("lsof")
    if not path:
        raise PortFetchError("The 'lsof' command is required but was not found on this system.")
    return path


def _split_host_port(address: str) -> Tuple[str, str]:
    host = address
    port = ""
    if not address:
        return host, port

    if "->" in address:
        host = address.split("->", 1)[0]

    if host.startswith("[") and "]" in host:
        closing = host.find("]")
        bracketed = host[1:closing]
        tail = host[closing + 1 :]
        if tail.startswith(":"):
            port = tail[1:]
        host = bracketed
    elif ":" in host:
        parts = host.rsplit(":", 1)
        if len(parts) == 2:
            host, port = parts
    return host or address, port


def _parse_lsof_output(output: str) -> List[Dict]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []

    entries: List[Dict] = []
    header_skipped = False
    for line in lines:
        if not header_skipped:
            header_skipped = True
            continue

        parts = line.split()
        if len(parts) < 9:
            # Unexpected line format, skip it.
            continue

        command, pid_str, user, fd, type_, device, size_off, node = parts[:8]
        name_parts = parts[8:]
        protocol = node
        state = ""

        if name_parts and name_parts[-1].startswith("(") and name_parts[-1].endswith(")"):
            state = name_parts[-1][1:-1]
            name_parts = name_parts[:-1]

        address = " ".join(name_parts)
        host, port = _split_host_port(address)

        try:
            pid = int(pid_str)
        except ValueError:
            # Skip rows with non-numeric PIDs (shouldn't happen, but be safe)
            continue

        process_details = _get_process_details(pid)

        entries.append(
            {
                "command": command,
                "pid": pid,
                "ppid": process_details.get("ppid"),
                "user": user,
                "fd": fd,
                "type": type_,
                "protocol": protocol,
                "address": address,
                "host": host,
                "port": port,
                "state": state,
                "full_command": process_details.get("command_path") or command,
                "cwd": process_details.get("cwd") or "",
                "details": {
                    "device": device,
                    "size_off": size_off,
                    "node": node,
                },
            }
        )

    return entries


def _collect_ports() -> List[Dict]:
    lsof = _get_lsof_path()
    cmd = [lsof, "-nP", "-iTCP", "-iUDP"]
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PortFetchError(exc.stderr.strip() or "Failed to collect port information.") from exc
    return _parse_lsof_output(completed.stdout)


@functools.lru_cache(maxsize=1024)
def _get_process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


@functools.lru_cache(maxsize=1024)
def _get_parent_pid(pid: int) -> int | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "ppid="],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        value = result.stdout.strip()
        return int(value) if value.isdigit() else None
    except subprocess.CalledProcessError:
        return None


@functools.lru_cache(maxsize=1024)
def _get_process_cwd(pid: int) -> str:
    lsof = _get_lsof_path()
    cmd = [lsof, "-a", "-p", str(pid), "-d", "cwd", "-Fn"]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError:
        return ""

    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return line[1:].strip()
    return ""


def _get_process_details(pid: int) -> Dict[str, str]:
    return {
        "ppid": _get_parent_pid(pid),
        "command_path": _get_process_command(pid),
        "cwd": _get_process_cwd(pid),
    }


def _kill_process(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError as exc:
        abort(404, description=f"Process {pid} was not found.")
    except PermissionError as exc:
        abort(403, description=f"Insufficient permissions to signal process {pid}.")
    except Exception as exc:  # pylint: disable=broad-except
        abort(500, description=f"Failed to signal process {pid}: {exc}")


@app.route("/api/ports", methods=["GET"])
def api_ports():
    ports = _collect_ports()
    return jsonify({"ports": ports, "count": len(ports)})


@app.route("/api/kill", methods=["POST"])
def api_kill():
    payload = request.get_json(silent=True) or {}
    pid = payload.get("pid")
    if pid is None:
        abort(400, description="Missing 'pid' in request body.")
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        abort(400, description="'pid' must be an integer.")

    _kill_process(pid_int, signal.SIGTERM)
    return jsonify({"status": "ok", "message": f"Sent SIGTERM to process {pid_int}."})


@app.route("/api/force-kill", methods=["POST"])
def api_force_kill():
    payload = request.get_json(silent=True) or {}
    pid = payload.get("pid")
    if pid is None:
        abort(400, description="Missing 'pid' in request body.")
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        abort(400, description="'pid' must be an integer.")

    _kill_process(pid_int, signal.SIGKILL)
    return jsonify({"status": "ok", "message": f"Sent SIGKILL to process {pid_int}."})


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.errorhandler(PortFetchError)
def handle_port_fetch_error(err):
    return jsonify({"error": str(err)}), 500


@app.errorhandler(400)
def handle_bad_request(err):
    return jsonify({"error": err.description if hasattr(err, "description") else str(err)}), 400


@app.errorhandler(403)
def handle_forbidden(err):
    return jsonify({"error": err.description if hasattr(err, "description") else str(err)}), 403


@app.errorhandler(404)
def handle_not_found(err):
    return jsonify({"error": err.description if hasattr(err, "description") else str(err)}), 404


@app.errorhandler(500)
def handle_server_error(err):
    description = err.description if hasattr(err, "description") else str(err)
    return jsonify({"error": description or "Internal server error."}), 500


def _find_available_port(preferred: int, host: str = "0.0.0.0", max_attempts: int = 50) -> int:
    """Return the first available port, starting at `preferred`."""
    candidate = preferred
    attempts = 0
    while attempts < max_attempts:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                candidate += 1
                attempts += 1
    raise RuntimeError(f"No free port found starting at {preferred} after {max_attempts} attempts.")


def _resolve_run_port(host: str, preferred: int) -> int:
    """Determine which port the Flask dev server should bind to."""
    assigned = os.environ.get(ASSIGNED_PORT_ENV)
    if assigned:
        try:
            return int(assigned)
        except ValueError:
            os.environ.pop(ASSIGNED_PORT_ENV, None)

    port = _find_available_port(preferred, host)
    os.environ[ASSIGNED_PORT_ENV] = str(port)
    if port != preferred:
        print(f"Port {preferred} is busy, switching to {port}.", flush=True)
    return port


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    preferred_port = int(os.environ.get("PORT", "5000"))
    try:
        port = _resolve_run_port(host, preferred_port)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    app.run(host=host, port=port, debug=True)
