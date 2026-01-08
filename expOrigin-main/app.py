# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename
from sqlalchemy import text
from dotenv import load_dotenv
import os
import re

# -----------------------------------------------------
# .env yükle
# -----------------------------------------------------
load_dotenv()

# -----------------------------------------------------
# Flask ve DB kurulum
# -----------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here")

def get_db_url() -> str:
    """
    Render/Neon için DATABASE_URL zorunlu. (psql '...' formatını da temizler)
    Dilersen local geliştirme için aşağıya fallback ekleyebilirsin.
    """
    env_url = (os.getenv("DATABASE_URL") or "").strip()
    if env_url:
        if env_url.startswith("psql "):
            env_url = env_url.replace("psql ", "", 1).strip().strip(" '\"")
        if not re.match(r"^postgresql(\+\w+)?://", env_url):
            raise RuntimeError("DATABASE_URL geçersiz formatta.")
        return env_url

    # İsteğe bağlı local fallback (istersen kaldır):
    local_user = os.getenv("LOCAL_DB_USER", "postgres")
    local_pass = os.getenv("LOCAL_DB_PASS", "1035")
    local_host = os.getenv("LOCAL_DB_HOST", "localhost")
    local_name = os.getenv("LOCAL_DB_NAME", "exp")
    return f"postgresql://{local_user}:{local_pass}@{local_host}/{local_name}"

app.config["SQLALCHEMY_DATABASE_URI"] = get_db_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
db = SQLAlchemy(app)

def get_db_connection():
    return db.engine.connect()

# -----------------------------------------------------
# Şema: tablolar + tohum veriler
# -----------------------------------------------------
def ensure_tables():
    """
    Uygulama ilk ayağa kalktığında eksik tabloları oluşturur.
    """
    with db.engine.begin() as conn:
        # users
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                fullname VARCHAR(100),
                email VARCHAR(100) UNIQUE,
                password VARCHAR(255),
                role BOOLEAN DEFAULT FALSE
            )
        """))

        # precautions
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS precautions (
                id SERIAL PRIMARY KEY,
                title TEXT,
                explanation TEXT
            )
        """))

        # reports
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER,
                type TEXT,
                date TIMESTAMP,
                fullname TEXT,
                details TEXT,
                witnesses TEXT,
                department VARCHAR(50)
            )
        """))

        # Kategori tablosu (legacy)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                riskCategories TEXT,
                eventCategories TEXT
            )
        """))

        # Yeni kategori tabloları (asıl kullanılanlar)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS riskcategories (
                id SERIAL PRIMARY KEY,
                type TEXT UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eventcategories (
                id SERIAL PRIMARY KEY,
                type TEXT UNIQUE
            )
        """))

        # reports missing columns (idempotent)
        conn.execute(text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS details TEXT"))
        conn.execute(text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS witnesses TEXT"))
        conn.execute(text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS department VARCHAR(50)"))


def seed_default_categories():
    """
    riskcategories & eventcategories tablolarına eksik default değerleri ekler.
    """
    seed_risks = [
        "Tadilat Gerektiren Araçlar",
        "Elektrik Kaçağı",
        "Kaygan Zemin",
        "Gaz Sızıntısı",
        "Madde Sızıntısı",
    ]
    seed_events = [
        "Yangın",
        "Elektrikle Temas",
        "Yük Altında Kalma",
        "Patlama",
        "Hırsızlık",
        "Şiddet/Kavga",
    ]
    with db.engine.begin() as conn:
        for r in seed_risks:
            conn.execute(text("""
                INSERT INTO riskcategories (type)
                SELECT :t
                WHERE NOT EXISTS (SELECT 1 FROM riskcategories WHERE LOWER(type)=LOWER(:t))
            """), {"t": r})

        for e in seed_events:
            conn.execute(text("""
                INSERT INTO eventcategories (type)
                SELECT :t
                WHERE NOT EXISTS (SELECT 1 FROM eventcategories WHERE LOWER(type)=LOWER(:t))
            """), {"t": e})

# Flask 3.x'le before_first_request kaldırıldığı için init bayrağıyla çalışıyoruz
_INIT_DONE = False

@app.before_request
def _init_once_and_admin_flag():
    global _INIT_DONE
    if not _INIT_DONE:
        try:
            ensure_tables()
            seed_default_categories()
            _INIT_DONE = True
        except Exception as e:
            app.logger.exception("Şema/seed init hatası: %s", e)

    # Admin flag'i taşı
    try:
        if "user_id" in session and "is_admin" not in session:
            with get_db_connection() as conn:
                row = conn.execute(
                    text("SELECT role FROM users WHERE id=:uid"),
                    {"uid": session["user_id"]}
                ).fetchone()
            session["is_admin"] = bool(row[0]) if row else False
    except Exception:
        pass

# -----------------------------------------------------
# Auth decorator’lar
# -----------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    text("SELECT role FROM users WHERE id=:uid"),
                    {"uid": session["user_id"]}
                ).fetchone()
            if not row or not row[0]:
                flash("Bu sayfaya erişim yetkiniz yok!", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        except Exception as e:
            app.logger.exception("Yetki kontrolü hatası: %s", e)
            flash(f"Yetki kontrolü hatası: {e}", "error")
            return redirect(url_for("index"))
    return decorated_function

# -----------------------------------------------------
# Genel sayfalar
# -----------------------------------------------------
@app.route("/")
def index():
    # logout sonrası kalan flash'ları sadeleştirme (opsiyonel)
    if "_flashes" in session:
        flashes = session["_flashes"]
        session["_flashes"] = [(c, m) for (c, m) in flashes if "çıkış" in m.lower()]
    return render_template("index.html", active_page="index")

@app.route("/egitimler")
def egitimler():
    return render_template("educations.html", active_page="education")

@app.route("/risk-bildir")
def risk_bildir():
    return render_template("riskreport.html", active_page="risk")

@app.route("/olay-bildir")
def olay_bildir():
    return render_template("eventreport.html", active_page="event")

@app.route("/raporlar")
@admin_required
def raporlar():
    return render_template("reports.html", active_page="reports")


# -----------------------------------------------------
# Precautions
# -----------------------------------------------------
@app.route("/precautions")
def precautions():
    try:
        with get_db_connection() as conn:
            precautions_data = conn.execute(
                text("SELECT id, title, explanation FROM precautions ORDER BY id")
            ).fetchall()
        return render_template(
            "precautions.html",
            active_page="precautions",
            precautions=precautions_data
        )
    except Exception as e:
        flash(f"Veri yükleme hatası: {e}", "error")
        return render_template("precautions.html", active_page="precautions", precautions=[])

@app.route("/submit-precautions", methods=["POST"])
@admin_required
def submit_precautions():
    try:
        title = (request.form.get("title") or "").strip()
        explanation = (request.form.get("explanation") or "").strip()

        if not title or len(title) < 5:
            return jsonify({"success": False, "message": "Başlık en az 5 karakter olmalıdır!"})
        if not explanation or len(explanation) < 10:
            return jsonify({"success": False, "message": "Açıklama en az 10 karakter olmalıdır!"})
        if len(title) > 200:
            return jsonify({"success": False, "message": "Başlık en fazla 200 karakter olabilir!"})
        if len(explanation) > 1000:
            return jsonify({"success": False, "message": "Açıklama en fazla 1000 karakter olabilir!"})

        with db.engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM precautions WHERE LOWER(title)=LOWER(:t) LIMIT 1"),
                {"t": title}
            ).fetchone()
            if exists:
                return jsonify({"success": False, "message": "Bu başlıkta bir önlem zaten mevcut!"})

            conn.execute(
                text("INSERT INTO precautions (title, explanation) VALUES (:t, :e)"),
                {"t": title, "e": explanation}
            )

        return jsonify({"success": True, "message": "Önlem başarıyla eklendi!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Veritabanı hatası: {e}"})

@app.route("/delete-precautions", methods=["POST"])
@admin_required
def delete_precautions():
    try:
        data = request.get_json()
        if not data or "ids" not in data:
            return jsonify({"success": False, "message": "Geçersiz veri!"})

        ids = data["ids"]
        if not isinstance(ids, list) or len(ids) == 0:
            return jsonify({"success": False, "message": "Silinecek önlem seçilmedi!"})

        try:
            ids = [int(i) for i in ids]
        except ValueError:
            return jsonify({"success": False, "message": "Geçersiz ID formatı!"})

        with db.engine.begin() as conn:
            existing_ids = [r[0] for r in conn.execute(
                text("SELECT id FROM precautions WHERE id = ANY(:ids)"),
                {"ids": ids}
            ).fetchall()]

            if not existing_ids:
                return jsonify({"success": False, "message": "Silinecek önlem bulunamadı!"})

            result = conn.execute(
                text("DELETE FROM precautions WHERE id = ANY(:ids)"),
                {"ids": existing_ids}
            )

        return jsonify({
            "success": True,
            "message": f"{result.rowcount} adet önlem başarıyla silindi!",
            "deleted_count": result.rowcount
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Veritabanı hatası: {e}"})

# -----------------------------------------------------
# Kategoriler (risk & event)
# -----------------------------------------------------
@app.route("/api/categories", methods=["GET"])
def list_categories():
    try:
        cat_type = (request.args.get("type") or "").strip().lower()
        if cat_type not in ("risk", "event"):
            return jsonify({"success": False, "message": "Geçersiz kategori tipi"}), 400

        with get_db_connection() as conn:
            if cat_type == "risk":
                rows = conn.execute(text("SELECT type FROM riskcategories ORDER BY type ASC")).fetchall()
            else:
                rows = conn.execute(text("SELECT type FROM eventcategories ORDER BY type ASC")).fetchall()

        return jsonify({"success": True, "items": [r[0] for r in rows]})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/api/categories", methods=["POST"])
@admin_required
def add_category():
    try:
        if request.is_json:
            name = (request.json.get("name") or "").strip()
            cat_type = (request.json.get("type") or "").strip().lower()
        else:
            name = (request.form.get("name") or "").strip()
            cat_type = (request.form.get("type") or "").strip().lower()

        if not name or not cat_type or cat_type not in ("risk", "event"):
            return jsonify({"success": False, "message": "Geçersiz/eksik alanlar"}), 400

        with db.engine.begin() as conn:
            if cat_type == "risk":
                exists = conn.execute(
                    text("SELECT 1 FROM riskcategories WHERE LOWER(type)=LOWER(:n) LIMIT 1"),
                    {"n": name}
                ).fetchone()
                if not exists:
                    conn.execute(text("INSERT INTO riskcategories (type) VALUES (:n)"), {"n": name})
            else:
                exists = conn.execute(
                    text("SELECT 1 FROM eventcategories WHERE LOWER(type)=LOWER(:n) LIMIT 1"),
                    {"n": name}
                ).fetchone()
                if not exists:
                    conn.execute(text("INSERT INTO eventcategories (type) VALUES (:n)"), {"n": name})

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/api/categories/bulk-delete", methods=["POST"])
@admin_required
def delete_categories():
    try:
        payload = request.get_json(silent=True) or {}
        cat_type = str(payload.get("type", "")).strip().lower()
        names = payload.get("names") or []

        if cat_type not in ("risk", "event") or not isinstance(names, list) or len(names) == 0:
            return jsonify({"success": False, "message": "Geçersiz parametreler"}), 400

        with db.engine.begin() as conn:
            if cat_type == "risk":
                result = conn.execute(
                    text("DELETE FROM riskcategories WHERE type = ANY(:names)"),
                    {"names": names}
                )
            else:
                result = conn.execute(
                    text("DELETE FROM eventcategories WHERE type = ANY(:names)"),
                    {"names": names}
                )

        return jsonify({"success": True, "deleted": result.rowcount})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

# -----------------------------------------------------
# Raporlar API’leri
# -----------------------------------------------------
def ensure_upload_dir():
    upload_dir = os.path.join("static", "uploads")
    if not os.path.isdir(upload_dir):
        try:
            os.makedirs(upload_dir, exist_ok=True)
        except Exception as e:
            print("Upload klasörü oluşturulamadı:", e)
    return upload_dir

@app.route("/api/reports")
@login_required
def api_reports():
    try:
        # params
        try:
            limit = int(request.args.get("limit", 20))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            return jsonify({"success": False, "message": "Geçersiz parametre"}), 400

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        with get_db_connection() as conn:
            role_row = conn.execute(
                text("SELECT role FROM users WHERE id = :uid"),
                {"uid": session["user_id"]}
            ).fetchone()
        if not role_row or not role_row[0]:
            return jsonify({"success": False, "message": "Erişim reddedildi"}), 403

        q = (request.args.get("q") or "").strip()
        report_type = (request.args.get("type") or "").strip()
        date_from = (request.args.get("date_from") or "").strip()
        date_to = (request.args.get("date_to") or "").strip()

        where_clauses, params = [], {}
        if q:
            where_clauses.append("LOWER(u.fullname) LIKE LOWER(:q)")
            params["q"] = f"%{q}%"
        if report_type:
            where_clauses.append("LOWER(r.type) = LOWER(:rtype)")
            params["rtype"] = report_type
        if date_from:
            where_clauses.append("r.date::timestamp >= :dfrom")
            params["dfrom"] = date_from
        if date_to:
            where_clauses.append("r.date::timestamp <= :dto")
            params["dto"] = date_to

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        with get_db_connection() as conn:
            total_count = conn.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM reports r
                    LEFT JOIN users u ON r.id = u.id

                    {where_sql}
                """),
                params
            ).scalar() or 0

            rows = conn.execute(
                text(f"""
                    SELECT
                        r.id,
                        r.type,
                        r.date,
                        r.fullname,
                        COALESCE(u.fullname, r.fullname) AS reporter_name,
                        r.details,
                        r.witnesses,
                        r.department
                    FROM reports r
                    JOIN users u ON r.id = u.id
                    {where_sql}
                    ORDER BY r.date DESC
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": limit, "offset": offset}
            ).fetchall()

        items = []
        for row in rows:
            raw_date = row[2]
            date_value = raw_date.isoformat() if isinstance(raw_date, datetime) else (str(raw_date) if raw_date else None)
            items.append({
                "user_id": row[0],
                "type": row[1],
                "date": date_value,
                "fullname": row[3],
                "reporter_name": row[4],
                "details": row[5],
                "witnesses": row[6],
                "department": row[7],
            })

        has_more = offset + len(items) < total_count

        return jsonify({
            "success": True,
            "items": items,
            "total": total_count,
            "has_more": has_more,
            "next_offset": offset + len(items),
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/submit-risk-report", methods=["POST"])
def submit_risk_report():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Giriş gerekli"}), 401

    department = request.form.get("department")
    risk_types = request.form.getlist("risk_type[]")
    details = (request.form.get("details") or "").strip()

    if not department or not risk_types or len(details) < 5:
        return jsonify({"success": False, "message": "Eksik veya hatalı alanlar"}), 400

    upload_dir = ensure_upload_dir()
    saved_paths = []
    files = request.files.getlist("images[]") or []
    for f in files[:5]:
        if not f or not f.filename:
            continue
        if not f.mimetype or not f.mimetype.startswith("image/"):
            continue
        filename = secure_filename(f.filename)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        _, ext = os.path.splitext(filename)
        final_name = f"{session['user_id']}_{ts}{ext.lower()}"
        filepath = os.path.join(upload_dir, final_name)
        try:
            f.save(filepath)
            saved_paths.append(f"/static/uploads/{final_name}")
        except Exception:
            app.logger.exception("Görsel kaydedilemedi")

    attachments_text = f" | Görseller: {', '.join(saved_paths)}" if saved_paths else ""
    summary_type = "Risk Bildirim Raporlaması"
    summary_details = f"Departman: {department} | Risk Türleri: {', '.join(risk_types)} | Detaylar: {details}{attachments_text}"

    try:
        with db.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO reports (id, type, date, fullname, details, witnesses, department)
                    VALUES (:uid, :type, :date, :fullname, :details, :witnesses, :department)
                """),
                {
                    "uid": session["user_id"],
                    "type": summary_type,
                    "date": datetime.utcnow(),
                    "fullname": session.get("fullname", ""),
                    "details": summary_details,
                    "witnesses": None,
                    "department": department,
                }
            )
        return jsonify({"success": True, "message": "Risk raporu başarıyla kaydedildi"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/submit-event-report", methods=["POST"])
def submit_event_report():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Giriş gerekli"}), 401

    department = request.form.get("department")
    event_types = request.form.getlist("event_type[]")
    location = (request.form.get("location") or "").strip()
    details = (request.form.get("details") or "").strip()
    witnesses = (request.form.get("witnesses") or "").strip()

    if not department or not event_types or not location or len(details) < 5:
        return jsonify({"success": False, "message": "Eksik veya hatalı alanlar"}), 400

    upload_dir = ensure_upload_dir()
    saved_paths = []
    files = request.files.getlist("images[]") or []
    for f in files[:5]:
        if not f or not f.filename:
            continue
        if not f.mimetype or not f.mimetype.startswith("image/"):
            continue
        filename = secure_filename(f.filename)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        _, ext = os.path.splitext(filename)
        final_name = f"{session['user_id']}_{ts}{ext.lower()}"
        filepath = os.path.join(upload_dir, final_name)
        try:
            f.save(filepath)
            saved_paths.append(f"/static/uploads/{final_name}")
        except Exception:
            app.logger.exception("Görsel kaydedilemedi")

    attachments_text = f" | Görseller: {', '.join(saved_paths)}" if saved_paths else ""
    summary_type = "Olay Bildirim Raporlaması"
    summary_details = f"Departman: {department} | Olay Türleri: {', '.join(event_types)} | Yer: {location} | Detaylar: {details}{attachments_text}"

    try:
        with db.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO reports (id, type, date, fullname, details, witnesses, department)
                    VALUES (:uid, :type, :date, :fullname, :details, :witnesses, :department)
                """),
                {
                    "uid": session["user_id"],
                    "type": summary_type,
                    "date": datetime.utcnow(),
                    "fullname": session.get("fullname", ""),
                    "details": summary_details,
                    "witnesses": witnesses or None,
                    "department": department,
                }
            )
        return jsonify({"success": True, "message": "Olay raporu başarıyla kaydedildi"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/submit-emergency-report", methods=["POST"])
@login_required
def submit_emergency_report():
    try:
        with db.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO reports (id, type, date, fullname, witnesses, department)
                VALUES (:uid, :type, :date, :fullname, :witnesses, :department)
            """), {
                "uid": session["user_id"],
                "type": "Acil Yardım Sinyali",
                "date": datetime.utcnow(),
                "fullname": session.get("fullname"),
                "witnesses": None,
                "department": None,
            })
        return jsonify({"success": True, "message": "Acil yardım sinyali başarıyla gönderildi!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/check-new-reports")
@admin_required
def check_new_reports():
    try:
        with get_db_connection() as conn:
            rows = conn.execute(text("""
                SELECT r.id, r.type, r.date, r.fullname, u.fullname AS reporter_name, r.witnesses, r.department
                FROM reports r
                JOIN users u ON r.id = u.id
                WHERE r.date::timestamp >= NOW() - INTERVAL '10 second'
                ORDER BY r.date DESC
            """)).fetchall()

        reports_data = [{
            "id": row[0],
            "type": row[1],
            "date": row[2].isoformat() if isinstance(row[2], datetime) else str(row[2]),
            "fullname": row[3],
            "reporter_name": row[4],
            "witnesses": row[5],
            "department": row[6],
        } for row in rows]

        return jsonify({"success": True, "new_reports": reports_data, "count": len(reports_data)})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/debug-reports")
@login_required
def debug_reports():
    try:
        with get_db_connection() as conn:
            all_reports = conn.execute(text("""
                SELECT r.id, r.type, r.date, r.fullname, u.fullname AS reporter_name, r.witnesses, r.department
                FROM reports r
                JOIN users u ON r.id = u.id
                ORDER BY r.date DESC
                LIMIT 10
            """)).fetchall()

            new_reports = conn.execute(text("""
                SELECT r.id, r.type, r.date, r.fullname, u.fullname AS reporter_name, r.witnesses, r.department
                FROM reports r
                JOIN users u ON r.id = u.id
                WHERE r.date::timestamp >= NOW() - INTERVAL '10 second'
                ORDER BY r.date DESC
            """)).fetchall()

        def serialize(rows):
            return [{
                "id": r[0],
                "type": r[1],
                "date": r[2].isoformat() if isinstance(r[2], datetime) else str(r[2]),
                "fullname": r[3],
                "reporter_name": r[4],
                "witnesses": r[5],
                "department": r[6],
            } for r in rows]

        return jsonify({
            "success": True,
            "all_reports": serialize(all_reports),
            "new_reports": serialize(new_reports),
            "current_time": datetime.utcnow().isoformat(),
            "total_reports": len(all_reports),
            "new_reports_count": len(new_reports),
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/check-admin-status")
@login_required
def check_admin_status():
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                text("SELECT role FROM users WHERE id=:uid"),
                {"uid": session["user_id"]}
            ).fetchone()
        is_admin = bool(row[0]) if row else False
        return jsonify({"is_admin": is_admin, "success": True})
    except Exception as e:
        return jsonify({"is_admin": False, "message": f"Hata: {e}"}), 500

# -----------------------------------------------------
# Kullanıcı Yönetimi
# -----------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fullname = (request.form.get("fullname") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        if not fullname or not email or not password:
            flash("Lütfen tüm alanları doldurun.", "error")
            return render_template("register.html", active_page="register")

        try:
            with db.engine.begin() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM users WHERE LOWER(email)=LOWER(:e) LIMIT 1"),
                    {"e": email}
                ).fetchone()
                if exists:
                    flash("Bu e-posta adresi zaten kayıtlı!", "error")
                    return render_template("register.html", active_page="register")

                hashed_password = generate_password_hash(password)
                conn.execute(text("""
                    INSERT INTO users (fullname, email, password, role)
                    VALUES (:fn, :em, :pw, :role)
                """), {"fn": fullname, "em": email, "pw": hashed_password, "role": False})

            flash("Kayıt başarılı! Giriş yapabilirsiniz.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"Kayıt hatası: {e}", "error")

    if "_flashes" in session:
        session.pop("_flashes", None)

    return render_template("register.html", active_page="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        try:
            with get_db_connection() as conn:
                user = conn.execute(text("""
                    SELECT id, fullname, email, password, role
                    FROM users
                    WHERE email = :email
                    LIMIT 1
                """), {"email": email}).fetchone()

            if user and check_password_hash(user[3], password):
                session["user_id"] = user[0]
                session["fullname"] = user[1]
                session["email"] = user[2]
                session["is_admin"] = bool(user[4])
                flash("Giriş başarılı!", "success")
                return redirect(url_for("index"))
            else:
                flash("E-Postanız veya Şifreniz hatalı", "error")
        except Exception as e:
            flash(f"Giriş hatası: {e}", "error")

    if "_flashes" in session:
        session.pop("_flashes", None)

    return render_template("login.html", active_page="login")

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", active_page="profile")

@app.route("/update-profile", methods=["POST"])
@login_required
def update_profile():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    if not email or not password:
        flash("E-posta ve şifre boş olamaz.", "error")
        return redirect(url_for("profile"))
    try:
        with db.engine.begin() as conn:
            if email.lower() != (session.get("email") or "").lower():
                exists = conn.execute(
                    text("SELECT 1 FROM users WHERE LOWER(email)=LOWER(:e) AND id!=:uid"),
                    {"e": email, "uid": session["user_id"]}
                ).fetchone()
                if exists:
                    flash("Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor!", "error")
                    return redirect(url_for("profile"))

            hashed_password = generate_password_hash(password)
            conn.execute(
                text("UPDATE users SET email=:e, password=:p WHERE id=:uid"),
                {"e": email, "p": hashed_password, "uid": session["user_id"]}
            )
        session["email"] = email
        flash("Profil bilgileriniz başarıyla güncellendi!", "success")
        return redirect(url_for("profile"))
    except Exception as e:
        flash(f"Güncelleme hatası: {e}", "error")
        return redirect(url_for("profile"))

@app.route("/api/profile/email", methods=["POST"])
@login_required
def api_update_email():
    try:
        payload = request.get_json(silent=True) or {}
        new_email = (payload.get("email") or "").strip()
        if not new_email:
            return jsonify({"success": False, "message": "E-posta boş olamaz!"}), 400
        if "@" not in new_email or "." not in new_email.split("@")[-1]:
            return jsonify({"success": False, "message": "Geçerli bir e-posta giriniz!"}), 400
        if new_email.lower() == (session.get("email") or "").lower():
            return jsonify({"success": True, "message": "E-posta zaten güncel.", "email": session.get("email")})

        with db.engine.begin() as conn:
            exists = conn.execute(text("""
                SELECT 1 FROM users
                WHERE LOWER(email)=LOWER(:e) AND id<>:uid
                LIMIT 1
            """), {"e": new_email, "uid": session["user_id"]}).fetchone()
            if exists:
                return jsonify({"success": False, "message": "Bu e-posta başka bir kullanıcı tarafından kullanılıyor!"}), 409

            conn.execute(text("UPDATE users SET email=:e WHERE id=:uid"),
                         {"e": new_email, "uid": session["user_id"]})
        session["email"] = new_email
        return jsonify({"success": True, "message": "E-posta güncellendi.", "email": new_email})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/api/profile/password", methods=["POST"])
@login_required
def api_update_password():
    try:
        payload = request.get_json(silent=True) or {}
        new_password = (payload.get("password") or "").strip()
        if not new_password or len(new_password) < 6:
            return jsonify({"success": False, "message": "Şifre en az 6 karakter olmalıdır!"}), 400

        hashed_password = generate_password_hash(new_password)
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE users SET password=:p WHERE id=:uid"),
                         {"p": hashed_password, "uid": session["user_id"]})
        return jsonify({"success": True, "message": "Şifre güncellendi."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/api/users/search")
@login_required
def search_users():
    try:
        query = (request.args.get("q") or "").strip()
        if len(query) < 2:
            return jsonify({"success": True, "users": []})

        with get_db_connection() as conn:
            rows = conn.execute(text("""
                SELECT id, fullname
                FROM users
                WHERE LOWER(fullname) LIKE LOWER(:pattern)
                ORDER BY fullname
                LIMIT 10
            """), {"pattern": f"%{query}%"}).fetchall()

        users = [{"id": r[0], "fullname": r[1]} for r in rows]
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500

@app.route("/logout")
def logout():
    if "_flashes" in session:
        session.pop("_flashes", None)
    session.clear()
    flash("Başarıyla çıkış yaptınız.", "success")
    return redirect(url_for("index"))

@app.route("/api/mobile-login", methods=["POST"])
def api_mobile_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "")
    if not email or not password:
        return jsonify({"success": False, "message": "Eksik bilgiler"}), 400

    try:
        with get_db_connection() as conn:
            user = conn.execute(text("""
                SELECT id, fullname, email, password, role
                FROM users
                WHERE email = :email
                LIMIT 1
            """), {"email": email}).fetchone()

        if user and check_password_hash(user[3], password):
            return jsonify({
                "success": True,
                "message": "Giriş başarılı!",
                "user": {
                    "id": user[0],
                    "fullname": user[1],
                    "email": user[2],
                    "is_admin": bool(user[4])
                }
            })
        else:
            return jsonify({"success": False, "message": "E-posta veya şifre hatalı!"}), 401
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500



@app.route("/api/mobile-register", methods=["POST"])
def api_mobile_register():
    data = request.get_json(silent=True) or {}
    fullname = (data.get("fullname") or "").strip()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "")

    if not fullname or not email or not password:
        return jsonify({"success": False, "message": "Tüm alanlar doldurulmalıdır!"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Şifre en az 6 karakter olmalıdır!"}), 400

    try:
        with db.engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM users WHERE LOWER(email)=LOWER(:e) LIMIT 1"),
                {"e": email}
            ).fetchone()
            if exists:
                return jsonify({"success": False, "message": "Bu e-posta adresi zaten kayıtlı!"}), 409

            hashed_pw = generate_password_hash(password)
            conn.execute(
                text("INSERT INTO users (fullname, email, password, role) VALUES (:fn, :em, :pw, :r)"),
                {"fn": fullname, "em": email, "pw": hashed_pw, "r": False}
            )

        return jsonify({"success": True, "message": "Kayıt başarılı! Giriş yapabilirsiniz."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500
    

@app.route('/api/mobile-event-categories', methods=['GET'])
def get_mobile_event_categories():
    try:
        with get_db_connection() as conn:
            rows = conn.execute(text("SELECT type FROM eventcategories ORDER BY id ASC")).fetchall()
        categories = [r[0] for r in rows]
        return jsonify({"success": True, "categories": categories}), 200
    except Exception as e:
        app.logger.exception("ERROR /api/mobile-event-categories")
        return jsonify({"success": False, "message": str(e)}), 500



@app.route('/api/mobile-event-report', methods=['POST'])
def submit_event_report_mobile():
    try:
        payload = request.get_json(silent=True) or {}

        department = (payload.get("department") or "").strip()
        event_types = payload.get("event_types") or []   # List bekliyoruz
        location = (payload.get("location") or "").strip()
        details = (payload.get("details") or "").strip()
        witnesses = (payload.get("witnesses") or "").strip()

        if not department:
            return jsonify({"success": False, "message": "Departman zorunludur."}), 400
        if not isinstance(event_types, list) or len(event_types) == 0:
            return jsonify({"success": False, "message": "En az 1 olay türü seçiniz."}), 400
        if not location:
            return jsonify({"success": False, "message": "Olay yeri zorunludur."}), 400
        if not details or len(details) < 5:
            return jsonify({"success": False, "message": "Detaylar en az 5 karakter olmalıdır."}), 400

        # 🔥 Web tarafının formatıyla aynı "details" stringi
        summary_type = "Olay Bildirim Raporlaması"
        summary_details = (
            f"Departman: {department} | "
            f"Olay Türleri: {', '.join([str(x) for x in event_types])} | "
            f"Yer: {location} | "
            f"Detaylar: {details}"
        )

        # ⚠️ reports tablosu senin yapında kullanıcı id'yi "id" alanına yazıyor (user_id gibi)
        # Mobil login token yoksa en azından email ile user id bulalım:
        email = (payload.get("email") or "").strip().lower()
        if not email:
            return jsonify({"success": False, "message": "E-posta zorunludur (mobil rapor için)."}), 400

        with db.engine.begin() as conn:
            user = conn.execute(
                text("SELECT id, fullname FROM users WHERE LOWER(email)=LOWER(:e) LIMIT 1"),
                {"e": email}
            ).mappings().first()

            if not user:
                return jsonify({"success": False, "message": "Kullanıcı bulunamadı."}), 404

            conn.execute(
                text("""
                    INSERT INTO reports (id, type, date, fullname, details, witnesses, department)
                    VALUES (:uid, :type, :date, :fullname, :details, :witnesses, :department)
                """),
                {
                    "uid": user["id"],
                    "type": summary_type,
                    "date": datetime.utcnow(),
                    "fullname": user["fullname"] or "",
                    "details": summary_details,
                    "witnesses": witnesses or None,
                    "department": department,
                }
            )

        return jsonify({"success": True, "message": "Olay raporu başarıyla kaydedildi!"}), 200

    except Exception as e:
        app.logger.exception("ERROR /api/mobile-event-report")
        return jsonify({"success": False, "message": str(e)}), 500




@app.route("/api/mobile/profile/password", methods=["POST"])
def mobile_api_update_password():
    try:
        payload = request.get_json(force=True)  # force=True -> JSON parse garanti
        email = (payload.get("email") or "").strip().lower()
        current_password = (payload.get("current_password") or "").strip()
        new_password = (payload.get("new_password") or "").strip()

        if not email:
            return jsonify(success=False, message="E-posta zorunludur."), 400
        if not current_password:
            return jsonify(success=False, message="Mevcut şifre zorunludur."), 400
        if not new_password or len(new_password) < 6:
            return jsonify(success=False, message="Yeni şifre en az 6 karakter olmalıdır!"), 400

        with db.engine.begin() as conn:
            user = conn.execute(
                text("SELECT id, password FROM users WHERE email=:e LIMIT 1"),
                {"e": email}
            ).mappings().first()

            if not user:
                return jsonify(success=False, message="Kullanıcı bulunamadı."), 404

            if not check_password_hash(user["password"], current_password):
                return jsonify(success=False, message="Mevcut şifre yanlış."), 401

            conn.execute(
                text("UPDATE users SET password=:p WHERE id=:uid"),
                {"p": generate_password_hash(new_password), "uid": user["id"]}
            )

        return jsonify(success=True, message="Şifre güncellendi."), 200

    except Exception as e:
        # Burada da JSON dönsün
        return jsonify(success=False, message=str(e)), 500

# -----------------------------------------------------
# Araçlar / Debug
# -----------------------------------------------------
@app.route("/db-ping")
def db_ping():
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text("select version(), current_database();")).fetchone()
        return f"OK ✅ {row[0]} | DB={row[1]}"
    except Exception as e:
        app.logger.exception("DB PING FAILED")
        return f"DB FAIL ❌ {e}", 500

# -----------------------------------------------------
# Çalıştırma
# -----------------------------------------------------
if __name__ == "__main__":
    # Yerelde doğrudan çalıştırırken de şemayı kur
    ensure_tables()
    seed_default_categories()
    app.run(debug=True, host="0.0.0.0", port=5000)
