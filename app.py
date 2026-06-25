import json
import os
import threading

import psycopg2
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=None)

DATABASE_URL = os.environ.get("DATABASE_URL")
_lock = threading.Lock()


def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    id INTEGER PRIMARY KEY,
                    data JSONB NOT NULL
                )
                """
            )
        conn.commit()


if DATABASE_URL:
    init_db()


@app.route("/")
def index():
    # no-cache: el navegador siempre baja la última versión del HTML tras cada deploy.
    # Sin esto, quedaba sirviendo HTML viejo cacheado y los arreglos no se veían.
    resp = send_from_directory(os.path.dirname(__file__), "erp-inmobiliario.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/api/state", methods=["GET"])
def get_state():
    with _lock, get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM app_state WHERE id = 1")
            row = cur.fetchone()
    if row is None:
        return jsonify({"exists": False})
    return jsonify({"exists": True, "state": row[0]})


@app.route("/api/state", methods=["POST"])
def save_state():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "JSON invalido"}), 400
    with _lock, get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (id, data) VALUES (1, %s)
                ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                """,
                (json.dumps(payload),),
            )
        conn.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5051)
