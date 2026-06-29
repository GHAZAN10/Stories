import io
import json
import os
import threading

import psycopg2
from flask import Flask, Response, jsonify, request, send_from_directory
from pypdf import PdfReader, PdfWriter

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # hasta 64MB para subir el PDF de planos

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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS planos (
                    id INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL,
                    data BYTEA NOT NULL,
                    num_paginas INTEGER NOT NULL
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


@app.route("/logo.png")
def logo():
    # Si todavía no se subió logo.png, devuelve 404 y el HTML cae al wordmark de texto.
    return send_from_directory(os.path.dirname(__file__), "logo.png")


@app.route("/api/planos", methods=["GET"])
def get_planos_info():
    with _lock, get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT filename, num_paginas FROM planos WHERE id = 1")
            row = cur.fetchone()
    if row is None:
        return jsonify({"exists": False})
    return jsonify({"exists": True, "filename": row[0], "numPaginas": row[1]})


@app.route("/api/planos", methods=["POST"])
def upload_planos():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "Falta el archivo PDF"}), 400
    data = file.read()
    try:
        num_paginas = len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return jsonify({"error": "El archivo no es un PDF válido"}), 400
    with _lock, get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO planos (id, filename, data, num_paginas) VALUES (1, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET filename = EXCLUDED.filename, data = EXCLUDED.data, num_paginas = EXCLUDED.num_paginas
                """,
                (file.filename, psycopg2.Binary(data), num_paginas),
            )
        conn.commit()
    return jsonify({"ok": True, "filename": file.filename, "numPaginas": num_paginas})


@app.route("/planos.pdf")
def serve_planos():
    with _lock, get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM planos WHERE id = 1")
            row = cur.fetchone()
    if row is None:
        return jsonify({"error": "Todavía no se subió el PDF de planos"}), 404
    return Response(bytes(row[0]), mimetype="application/pdf", headers={"Content-Disposition": "inline; filename=planos.pdf"})


@app.route("/api/planos/pagina/<int:n>.pdf")
def serve_plano_pagina(n):
    with _lock, get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM planos WHERE id = 1")
            row = cur.fetchone()
    if row is None:
        return jsonify({"error": "Todavía no se subió el PDF de planos"}), 404
    reader = PdfReader(io.BytesIO(bytes(row[0])))
    if n < 1 or n > len(reader.pages):
        return jsonify({"error": "Página fuera de rango"}), 404
    writer = PdfWriter()
    writer.add_page(reader.pages[n - 1])
    out = io.BytesIO()
    writer.write(out)
    return Response(
        out.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=plano-pagina-{n}.pdf"},
    )


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
