from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3, os
from datetime import datetime

app = Flask(__name__)
DB = "unipod.db"

ROOMS = [
    ("ia_robotics",    "IA & Robotics Lab",     "#00d4ff"),
    ("eco_innovation", "Eco Innovation Lab",     "#00e676"),
    ("prototyping",    "Prototyping Lab",        "#ffd740"),
    ("food",           "Food Lab",               "#ff8a65"),
    ("multimedia",     "Multimedia Lab",         "#c77dff"),
]

DEPARTMENTS = [
    "DSTI",
    "DGAE",
    "DUAADT",
    "DSTAAN",
    "DGO",
    "STA",
    "TECNA",
    "SEG",
]

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nom       TEXT NOT NULL,
            prenom    TEXT NOT NULL,
            dept      TEXT NOT NULL,
            code      TEXT NOT NULL,
            room      TEXT NOT NULL,
            entree    TEXT NOT NULL,
            sortie    TEXT
        )
    """)
    conn.commit()
    conn.close()

def fmt_time(iso):
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except:
        return iso

def fmt_duration(entree, sortie=None):
    try:
        start = datetime.fromisoformat(entree)
        end   = datetime.fromisoformat(sortie) if sortie else datetime.now()
        mins  = int((end - start).total_seconds() / 60)
        if mins < 60:
            return f"{mins}min"
        return f"{mins//60}h{str(mins%60).zfill(2)}"
    except:
        return "—"

def room_name(rid):
    return next((r[1] for r in ROOMS if r[0] == rid), rid)

def room_color(rid):
    return next((r[2] for r in ROOMS if r[0] == rid), "#aaa")

# ── ADMIN ──────────────────────────────────────────────────────────────────────
@app.route("/")
def admin():
    conn = get_db()
    present  = conn.execute("SELECT * FROM visits WHERE sortie IS NULL ORDER BY entree DESC").fetchall()
    recent   = conn.execute("SELECT * FROM visits ORDER BY entree DESC LIMIT 6").fetchall()
    total    = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    departed = conn.execute("SELECT COUNT(*) FROM visits WHERE sortie IS NOT NULL").fetchone()[0]

    room_stats = []
    for rid, rname, rcolor in ROOMS:
        now_count   = conn.execute("SELECT COUNT(*) FROM visits WHERE room=? AND sortie IS NULL", (rid,)).fetchone()[0]
        total_count = conn.execute("SELECT COUNT(*) FROM visits WHERE room=?", (rid,)).fetchone()[0]
        room_stats.append({ "id": rid, "name": rname, "color": rcolor, "now": now_count, "total": total_count })
    conn.close()

    checkin_url = request.url_root + "checkin"

    return render_template("admin.html",
        present=present, recent=recent, total=total, departed=departed,
        room_stats=room_stats, checkin_url=checkin_url,
        fmt_time=fmt_time, fmt_duration=fmt_duration,
        room_name=room_name, room_color=room_color,
    )

# ── CHECK-IN ───────────────────────────────────────────────────────────────────
@app.route("/checkin", methods=["GET", "POST"])
def checkin():
    error = None
    if request.method == "POST":
        nom    = request.form.get("nom", "").strip()
        prenom = request.form.get("prenom", "").strip()
        dept   = request.form.get("dept", "").strip()
        code   = request.form.get("code", "").strip()
        room   = request.form.get("room", "").strip()
        if not all([nom, prenom, dept, code, room]):
            error = "Tous les champs sont obligatoires."
        else:
            conn = get_db()
            conn.execute(
                "INSERT INTO visits (nom, prenom, dept, code, room, entree) VALUES (?,?,?,?,?,?)",
                (nom, prenom, dept, code, room, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            return redirect(url_for("checkin_success", nom=nom, prenom=prenom, room=room,
                                     code=code, dept=dept,
                                     heure=datetime.now().strftime("%H:%M")))
    return render_template("checkin.html", rooms=ROOMS, departments=DEPARTMENTS, error=error)

@app.route("/checkin/success")
def checkin_success():
    return render_template("checkin_success.html",
        prenom=request.args.get("prenom"),
        nom=request.args.get("nom"),
        room=request.args.get("room"),
        room_name=room_name(request.args.get("room","")),
        room_color=room_color(request.args.get("room","")),
        code=request.args.get("code"),
        dept=request.args.get("dept"),
        heure=request.args.get("heure"),
    )

# ── CHECK-OUT ──────────────────────────────────────────────────────────────────
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    visitor = None
    error   = None
    success = None
    code    = request.args.get("code", "")

    if request.method == "POST":
        action = request.form.get("action")
        code   = request.form.get("code", "").strip()

        if action == "search":
            conn    = get_db()
            visitor = conn.execute(
                "SELECT * FROM visits WHERE LOWER(code)=LOWER(?) AND sortie IS NULL ORDER BY entree DESC LIMIT 1", (code,)
            ).fetchone()
            conn.close()
            if not visitor:
                error = "Aucun visiteur présent trouvé avec ce code."

        elif action == "confirm":
            vid  = request.form.get("vid")
            conn = get_db()
            row  = conn.execute("SELECT * FROM visits WHERE id=?", (vid,)).fetchone()
            conn.execute("UPDATE visits SET sortie=? WHERE id=?", (datetime.now().isoformat(), vid))
            conn.commit()
            conn.close()
            return redirect(url_for("checkout_success",
                prenom=row["prenom"], nom=row["nom"],
                entree=fmt_time(row["entree"]),
                duree=fmt_duration(row["entree"]),
                room=row["room"],
                room_label=room_name(row["room"]),
                room_color=room_color(row["room"]),
            ))

    # GET with code pre-fill (from admin quick link)
    if request.method == "GET" and code:
        conn    = get_db()
        visitor = conn.execute(
            "SELECT * FROM visits WHERE LOWER(code)=LOWER(?) AND sortie IS NULL ORDER BY entree DESC LIMIT 1", (code,)
        ).fetchone()
        conn.close()
        if not visitor:
            error = "Aucun visiteur présent avec ce code."

    conn    = get_db()
    present = conn.execute("SELECT * FROM visits WHERE sortie IS NULL ORDER BY entree DESC").fetchall()
    conn.close()

    return render_template("checkout.html",
        visitor=visitor, error=error, code=code,
        present=present, fmt_time=fmt_time, fmt_duration=fmt_duration,
        room_name=room_name, room_color=room_color,
    )

@app.route("/checkout/success")
def checkout_success():
    return render_template("checkout_success.html",
        prenom=request.args.get("prenom"),
        nom=request.args.get("nom"),
        entree=request.args.get("entree"),
        duree=request.args.get("duree"),
        room=request.args.get("room"),
        room_label=request.args.get("room_label"),
        room_color=request.args.get("room_color"),
        heure_sortie=datetime.now().strftime("%H:%M"),
    )

# ── DASHBOARD ──────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    filtre = request.args.get("filtre", "all")
    search = request.args.get("q", "")

    conn = get_db()
    query  = "SELECT * FROM visits WHERE 1=1"
    params = []
    if filtre == "present":
        query += " AND sortie IS NULL"
    elif filtre == "parti":
        query += " AND sortie IS NOT NULL"
    if search:
        query += " AND (LOWER(nom) LIKE ? OR LOWER(prenom) LIKE ? OR LOWER(code) LIKE ? OR LOWER(dept) LIKE ?)"
        s = f"%{search.lower()}%"
        params += [s, s, s, s]
    query += " ORDER BY entree DESC"
    visits = conn.execute(query, params).fetchall()

    total    = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    present  = conn.execute("SELECT COUNT(*) FROM visits WHERE sortie IS NULL").fetchone()[0]
    departed = conn.execute("SELECT COUNT(*) FROM visits WHERE sortie IS NOT NULL").fetchone()[0]

    # avg duration
    rows = conn.execute("SELECT entree, sortie FROM visits WHERE sortie IS NOT NULL").fetchall()
    avg_min = 0
    if rows:
        total_min = sum(int((datetime.fromisoformat(r["sortie"]) - datetime.fromisoformat(r["entree"])).total_seconds()/60) for r in rows)
        avg_min   = total_min // len(rows)
    avg_dur = f"{avg_min//60}h{str(avg_min%60).zfill(2)}" if avg_min >= 60 else f"{avg_min}min"

    room_stats = []
    for rid, rname, rcolor in ROOMS:
        cnt = conn.execute("SELECT COUNT(*) FROM visits WHERE room=?", (rid,)).fetchone()[0]
        pct = round((cnt / total * 100)) if total else 0
        room_stats.append({ "id": rid, "name": rname, "color": rcolor, "count": cnt, "pct": pct })
    top_room = max(room_stats, key=lambda r: r["count"]) if room_stats else None
    conn.close()

    return render_template("dashboard.html",
        visits=visits, filtre=filtre, search=search,
        total=total, present=present, departed=departed,
        avg_dur=avg_dur, room_stats=room_stats, top_room=top_room,
        fmt_time=fmt_time, fmt_duration=fmt_duration,
        room_name=room_name, room_color=room_color,
    )

# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/present")
def api_present():
    conn  = get_db()
    count = conn.execute("SELECT COUNT(*) FROM visits WHERE sortie IS NULL").fetchone()[0]
    conn.close()
    return jsonify({"count": count})

# ── CONTEXT PROCESSOR ─────────────────────────────────────────────────────────
@app.context_processor
def inject_now():
    return {"now": datetime.now()}

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", debug=True, port=5001)
