import json
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=None)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
_lock = threading.Lock()

os.makedirs(DATA_DIR, exist_ok=True)


@app.route("/")
def index():
    return send_from_directory(os.path.dirname(__file__), "erp-inmobiliario.html")


@app.route("/api/state", methods=["GET"])
def get_state():
    with _lock:
        if not os.path.exists(STATE_FILE):
            return jsonify({"exists": False})
        with open(STATE_FILE, encoding="utf-8") as f:
            return jsonify({"exists": True, "state": json.load(f)})


@app.route("/api/state", methods=["POST"])
def save_state():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "JSON invalido"}), 400
    with _lock:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5051)
