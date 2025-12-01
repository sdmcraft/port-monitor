"""
Flask application for monitoring and managing TCP/UDP ports on macOS.

Provides a web interface to view occupied ports, process details,
and send kill signals to processes.
"""

import os
import signal

from flask import Flask, jsonify, request, abort

from port_info import PortFetchError, collect_ports, kill_process
from port_resolution import resolve_run_port


app = Flask(__name__, static_folder="static", static_url_path="")


@app.route("/api/ports", methods=["GET"])
def api_ports():
    """
    API endpoint to retrieve all occupied TCP/UDP ports.

    Returns:
        JSON with 'ports' array and 'count' of total socket entries.
    """
    ports = collect_ports()
    return jsonify({"ports": ports, "count": len(ports)})


@app.route("/api/kill", methods=["POST"])
def api_kill():
    """
    API endpoint to send SIGTERM to a process.

    Expects JSON body with 'pid' field.
    SIGTERM allows the process to clean up gracefully before terminating.

    Returns:
        JSON with status and confirmation message.
    """
    payload = request.get_json(silent=True) or {}
    pid = payload.get("pid")
    if pid is None:
        abort(400, description="Missing 'pid' in request body.")
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        abort(400, description="'pid' must be an integer.")

    kill_process(pid_int, signal.SIGTERM)
    return jsonify({"status": "ok", "message": f"Sent SIGTERM to process {pid_int}."})


@app.route("/api/force-kill", methods=["POST"])
def api_force_kill():
    """
    API endpoint to send SIGKILL to a process.

    Expects JSON body with 'pid' field.
    SIGKILL immediately terminates the process without cleanup.
    Use when SIGTERM fails to stop a process.

    Returns:
        JSON with status and confirmation message.
    """
    payload = request.get_json(silent=True) or {}
    pid = payload.get("pid")
    if pid is None:
        abort(400, description="Missing 'pid' in request body.")
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        abort(400, description="'pid' must be an integer.")

    kill_process(pid_int, signal.SIGKILL)
    return jsonify({"status": "ok", "message": f"Sent SIGKILL to process {pid_int}."})


@app.route("/")
def index():
    """
    Serve the main web interface.

    Returns:
        Static HTML file from the static folder.
    """
    return app.send_static_file("index.html")


@app.errorhandler(PortFetchError)
def handle_port_fetch_error(err):
    """Handle PortFetchError exceptions by returning JSON error response."""
    return jsonify({"error": str(err)}), 500


@app.errorhandler(400)
def handle_bad_request(err):
    """Handle 400 Bad Request errors with JSON response."""
    return jsonify({"error": err.description if hasattr(err, "description") else str(err)}), 400


@app.errorhandler(403)
def handle_forbidden(err):
    """Handle 403 Forbidden errors with JSON response."""
    return jsonify({"error": err.description if hasattr(err, "description") else str(err)}), 403


@app.errorhandler(404)
def handle_not_found(err):
    """Handle 404 Not Found errors with JSON response."""
    return jsonify({"error": err.description if hasattr(err, "description") else str(err)}), 404


@app.errorhandler(500)
def handle_server_error(err):
    """Handle 500 Internal Server Error with JSON response."""
    description = err.description if hasattr(err, "description") else str(err)
    return jsonify({"error": description or "Internal server error."}), 500


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    preferred_port = int(os.environ.get("PORT", "5000"))
    try:
        port = resolve_run_port(host, preferred_port)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    app.run(host=host, port=port, debug=True)
