from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from flask import session, flash, redirect, url_for
from datetime import datetime
import os
import re
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from sqlalchemy import text
load_dotenv()



app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# (İstersen yerelde fallback dursun, prod'da ENV kullanılsın)
DB_CONFIG = {
    "host": "localhost",
    "database": "exp",
    "user": "postgres",
    "password": "1035",  # yerel için; repoda kalmaması önerilir
}




def get_db_url() -> str:
    env_url = (os.getenv("DATABASE_URL") or "").strip()
    if env_url:
        # Yanlışlıkla "psql '...'" yapıştırıldıysa temizle
        if env_url.startswith("psql "):
            env_url = env_url.replace("psql ", "", 1).strip().strip(" '\"")
        # Geçerli bir postgres URL'i mi?
        if not re.match(r"^postgresql(\+\w+)?://", env_url):
            raise RuntimeError("DATABASE_URL geçersiz görünüyor.")
        return env_url
    # ENV yoksa (sadece yerelde) fallback:
    return f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}/{DB_CONFIG['database']}"

# SQLAlchemy ayarları
app.config["SQLALCHEMY_DATABASE_URI"] = get_db_url()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,   # ölü bağlantıyı otomatik fark et
    "pool_recycle": 300,     # 5 dk'da bir bağlantıyı yenile
}


db = SQLAlchemy(app)


def get_db_connection():
    """
    SQLAlchemy engine üzerinden bir bağlantı döndürür.
    Kullanım:
        with get_db_connection() as conn:
            conn.execute(text("SELECT 1"))
    """
    return db.engine.connect()


# Kategoriler tablosunu oluştur ve başlangıç verilerini yükle
def ensure_categories_table_and_seed():
    try:
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

        # Transaction + otomatik commit için begin()
        with db.engine.begin() as conn:
            # Tabloyu oluştur (yoksa)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    riskCategories TEXT,
                    eventCategories TEXT
                )
            """))

            # Var olan kayıtları al
            rows = conn.execute(
                text("SELECT COALESCE(riskCategories,''), COALESCE(eventCategories,'') FROM categories")
            ).fetchall()
            existing_risks = {r[0] for r in rows if r[0]}
            existing_events = {r[1] for r in rows if r[1]}

            # Eksik riskleri ekle (eventCategories NULL)
            for risk in seed_risks:
                if risk not in existing_risks:
                    conn.execute(
                        text("INSERT INTO categories (riskCategories, eventCategories) VALUES (:risk, :ev)"),
                        {"risk": risk, "ev": None}
                    )

            # Eksik olayları ekle (riskCategories NULL)
            for ev in seed_events:
                if ev not in existing_events:
                    conn.execute(
                        text("INSERT INTO categories (riskCategories, eventCategories) VALUES (:risk, :ev)"),
                        {"risk": None, "ev": ev}
                    )

    except Exception as e:
        app.logger.exception("categories seed hatası")
        print("categories seed hatası:", e)


# Giriş kontrolü için decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Admin kontrolü için decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    text("SELECT role FROM users WHERE id = :uid"),
                    {"uid": session['user_id']}
                ).fetchone()

            if not row or not row[0]:
                flash('Bu sayfaya erişim yetkiniz yok!', 'error')
                return redirect(url_for('index'))

            return f(*args, **kwargs)

        except Exception as e:
            app.logger.exception("Yetki kontrolü hatası")
            flash(f'Yetki kontrolü hatası: {str(e)}', 'error')
            return redirect(url_for('index'))

    return decorated_function


# Ensure admin flag exists in session for template checks
@app.before_request
def ensure_admin_flag():
    try:
        if 'user_id' in session and 'is_admin' not in session:
            with get_db_connection() as conn:
                row = conn.execute(
                    text("SELECT role FROM users WHERE id = :uid"),
                    {"uid": session['user_id']}
                ).fetchone()
            session['is_admin'] = bool(row[0]) if row else False
    except Exception:
        # Sessiyon bayrağı zorunlu değil; hata durumunda sessiyona dokunma
        pass


# not: Flask 3.x 'before_first_request' kaldırıldı; gerekirse seeding işlemini manuel çağırın

@app.route('/')
def index():
    # Flash mesajlarını temizle (sadece başarı mesajları için)
    if '_flashes' in session:
        flashes = session['_flashes']
        # Sadece logout mesajını tut, diğerlerini temizle
        session['_flashes'] = [(category, message) for category, message in flashes if 'çıkış' in message.lower()]
    
    return render_template('index.html', active_page='index')









@app.route("/db-ping")
def db_ping():
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text("select version(), current_database();")).fetchone()
        return f"OK ✅ {row[0]} | DB={row[1]}"
    except Exception as e:
        app.logger.exception("DB PING FAILED")
        return f"DB FAIL ❌ {e}", 500










@app.route('/precautions')
def precautions():
    try:
        # with bloğu bağlantıyı otomatik kapatır
        with get_db_connection() as conn:
            # SQL sorgusu
            precautions_data = conn.execute(
                text("SELECT id, title, explanation FROM precautions ORDER BY id")
            ).fetchall()

        # fetchall() Row objeleri döner; Jinja şablonunda row.id, row.title, row.explanation
        return render_template(
            'precautions.html',
            active_page='precautions',
            precautions=precautions_data
        )

    except Exception as e:
        flash(f'Veri yükleme hatası: {e}', 'error')
        return render_template(
            'precautions.html',
            active_page='precautions',
            precautions=[]
        )

@app.route('/submit-precautions', methods=['POST'])
@admin_required
def submit_precautions():
    try:
        title = (request.form.get('title') or '').strip()
        explanation = (request.form.get('explanation') or '').strip()

        # Validasyon
        if not title or len(title) < 5:
            return jsonify({'success': False, 'message': 'Başlık en az 5 karakter olmalıdır!'})
        if not explanation or len(explanation) < 10:
            return jsonify({'success': False, 'message': 'Açıklama en az 10 karakter olmalıdır!'})
        if len(title) > 200:
            return jsonify({'success': False, 'message': 'Başlık en fazla 200 karakter olabilir!'})
        if len(explanation) > 1000:
            return jsonify({'success': False, 'message': 'Açıklama en fazla 1000 karakter olabilir!'})

        # Transaction + auto-commit
        with db.engine.begin() as conn:
            # Aynı başlık var mı?
            exists = conn.execute(
                text("SELECT 1 FROM precautions WHERE LOWER(title) = LOWER(:t) LIMIT 1"),
                {"t": title}
            ).fetchone()

            if exists:
                return jsonify({'success': False, 'message': 'Bu başlıkta bir önlem zaten mevcut!'})

            # Ekle
            conn.execute(
                text("INSERT INTO precautions (title, explanation) VALUES (:t, :e)"),
                {"t": title, "e": explanation}
            )

        return jsonify({'success': True, 'message': 'Önlem başarıyla eklendi!'})

    except Exception as e:
        # begin() bloğu hata alırsa otomatik rollback yapar
        return jsonify({'success': False, 'message': f'Veritabanı hatası: {e}'})

@app.route('/delete-precautions', methods=['POST'])
@admin_required
def delete_precautions():
    try:
        data = request.get_json()
        if not data or 'ids' not in data:
            return jsonify({'success': False, 'message': 'Geçersiz veri!'})

        ids = data['ids']
        if not isinstance(ids, list) or len(ids) == 0:
            return jsonify({'success': False, 'message': 'Silinecek önlem seçilmedi!'})

        # ID'lerin int olduğunu doğrula
        try:
            ids = [int(i) for i in ids]
        except ValueError:
            return jsonify({'success': False, 'message': 'Geçersiz ID formatı!'})

        # Transaction + auto-commit
        with db.engine.begin() as conn:
            # Önce gerçekten var mı kontrol et
            existing_ids = [
                row[0] for row in conn.execute(
                    text("SELECT id FROM precautions WHERE id = ANY(:ids)"),
                    {"ids": ids}
                ).fetchall()
            ]

            if not existing_ids:
                return jsonify({'success': False, 'message': 'Silinecek önlem bulunamadı!'})

            # Seçili önlemleri sil
            result = conn.execute(
                text("DELETE FROM precautions WHERE id = ANY(:ids)"),
                {"ids": existing_ids}
            )

        # result.rowcount, silinen satır sayısını verir
        return jsonify({
            'success': True,
            'message': f'{result.rowcount} adet önlem başarıyla silindi!',
            'deleted_count': result.rowcount
        })

    except Exception as e:
        # begin() bloğu hata alırsa otomatik rollback yapar
        return jsonify({'success': False, 'message': f'Veritabanı hatası: {e}'})

@app.route('/risk-bildir')
def risk_bildir():
    return render_template('riskreport.html', active_page='risk')

@app.route('/olay-bildir')
def olay_bildir():
    return render_template('eventreport.html', active_page='event')

# Kategori listeleme ve ekleme API'leri
@app.route('/api/categories', methods=['GET'])
def list_categories():
    try:
        cat_type = (request.args.get('type') or '').strip().lower()
        if cat_type not in ('risk', 'event'):
            return jsonify({'success': False, 'message': 'Geçersiz kategori tipi'}), 400

        with get_db_connection() as conn:
            # 1) Bilgi şemasından tablo adını tespit et
            if cat_type == 'risk':
                tables = {
                    r[0] for r in conn.execute(text("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND LOWER(table_name) IN ('riskcategories')
                    """)).fetchall()
                }
                # Tercih sırası
                if 'riskCategories' in tables:
                    rows = conn.execute(
                        text('SELECT "type" FROM "riskCategories" ORDER BY "type" ASC')
                    ).fetchall()
                elif 'riskcategories' in tables:
                    rows = conn.execute(
                        text('SELECT type FROM riskcategories ORDER BY type ASC')
                    ).fetchall()
                else:
                    # Her iki isim de yoksa fallback (deneme-yakalama)
                    try:
                        rows = conn.execute(
                            text('SELECT "type" FROM "riskCategories" ORDER BY "type" ASC')
                        ).fetchall()
                    except Exception:
                        rows = conn.execute(
                            text('SELECT type FROM riskcategories ORDER BY type ASC')
                        ).fetchall()

            else:  # event
                tables = {
                    r[0] for r in conn.execute(text("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND LOWER(table_name) IN ('eventcategories')
                    """)).fetchall()
                }
                if 'eventCategories' in tables:
                    rows = conn.execute(
                        text('SELECT "type" FROM "eventCategories" ORDER BY "type" ASC')
                    ).fetchall()
                elif 'eventcategories' in tables:
                    rows = conn.execute(
                        text('SELECT type FROM eventcategories ORDER BY type ASC')
                    ).fetchall()
                else:
                    try:
                        rows = conn.execute(
                            text('SELECT "type" FROM "eventCategories" ORDER BY "type" ASC')
                        ).fetchall()
                    except Exception:
                        rows = conn.execute(
                            text('SELECT type FROM eventcategories ORDER BY type ASC')
                        ).fetchall()

        return jsonify({'success': True, 'items': [r[0] for r in rows]})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/api/categories', methods=['POST'])
@admin_required
def add_category():
    try:
        # JSON ya da form'dan oku
        if request.is_json:
            name = (request.json.get('name') or '').strip()
            cat_type = (request.json.get('type') or '').strip().lower()
        else:
            name = (request.form.get('name') or '').strip()
            cat_type = (request.form.get('type') or '').strip().lower()

        if not name or not cat_type:
            return jsonify({'success': False, 'message': 'Eksik alanlar'}), 400
        if cat_type not in ('risk', 'event'):
            return jsonify({'success': False, 'message': 'Geçersiz kategori tipi'}), 400

        # Transaction + auto-commit
        with db.engine.begin() as conn:
            if cat_type == 'risk':
                # Önce CamelCase dene
                try:
                    exists = conn.execute(
                        text('SELECT 1 FROM "riskCategories" WHERE "type" = :name LIMIT 1'),
                        {"name": name}
                    ).fetchone() is not None
                    if not exists:
                        conn.execute(
                            text('INSERT INTO "riskCategories" ("type") VALUES (:name)'),
                            {"name": name}
                        )
                except Exception:
                    # Fallback: lowercase tablo
                    exists = conn.execute(
                        text('SELECT 1 FROM riskcategories WHERE type = :name LIMIT 1'),
                        {"name": name}
                    ).fetchone() is not None
                    if not exists:
                        conn.execute(
                            text('INSERT INTO riskcategories (type) VALUES (:name)'),
                            {"name": name}
                        )
            else:  # event
                try:
                    exists = conn.execute(
                        text('SELECT 1 FROM "eventCategories" WHERE "type" = :name LIMIT 1'),
                        {"name": name}
                    ).fetchone() is not None
                    if not exists:
                        conn.execute(
                            text('INSERT INTO "eventCategories" ("type") VALUES (:name)'),
                            {"name": name}
                        )
                except Exception:
                    exists = conn.execute(
                        text('SELECT 1 FROM eventcategories WHERE type = :name LIMIT 1'),
                        {"name": name}
                    ).fetchone() is not None
                    if not exists:
                        conn.execute(
                            text('INSERT INTO eventcategories (type) VALUES (:name)'),
                            {"name": name}
                        )

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


# Kategori toplu silme (admin)
@app.route('/api/categories/bulk-delete', methods=['POST'])
@admin_required
def delete_categories():
    try:
        payload = request.get_json(silent=True) or {}
        cat_type = str(payload.get('type', '')).strip().lower()
        names = payload.get('names') or []

        if cat_type not in ('risk', 'event') or not isinstance(names, list) or len(names) == 0:
            return jsonify({'success': False, 'message': 'Geçersiz parametreler'}), 400

        deleted = 0

        # Transaction + auto-commit
        with db.engine.begin() as conn:
            try:
                if cat_type == 'risk':
                    result = conn.execute(
                        text('DELETE FROM "riskCategories" WHERE "type" = ANY(:names)'),
                        {"names": names}
                    )
                else:
                    result = conn.execute(
                        text('DELETE FROM "eventCategories" WHERE "type" = ANY(:names)'),
                        {"names": names}
                    )
                deleted = result.rowcount
            except Exception:
                # lowercase fallback
                if cat_type == 'risk':
                    result = conn.execute(
                        text('DELETE FROM riskcategories WHERE type = ANY(:names)'),
                        {"names": names}
                    )
                else:
                    result = conn.execute(
                        text('DELETE FROM eventcategories WHERE type = ANY(:names)'),
                        {"names": names}
                    )
                deleted = result.rowcount

        return jsonify({'success': True, 'deleted': deleted})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/egitimler')
def egitimler():
    return render_template('educations.html', active_page='education')

@app.route('/raporlar')
@admin_required
def raporlar():
    return render_template('reports.html', active_page='reports')

@app.route('/api/reports')
@login_required
def api_reports():
    try:
        # 1) Şema güvenliği: details kolonu yoksa ekle (DDL -> transaction ile)
        try:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE IF NOT EXISTS reports ADD COLUMN IF NOT EXISTS details TEXT"))
        except Exception:
            # Şema değişikliği zorunlu değil; hata yutsa da olur
            pass

        # 2) Query params (pagination)
        try:
            limit = int(request.args.get('limit', 20))
            offset = int(request.args.get('offset', 0))
        except ValueError:
            return jsonify({'success': False, 'message': 'Geçersiz parametre'}), 400

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        # 3) Admin kontrolü
        with get_db_connection() as conn:
            role_row = conn.execute(
                text("SELECT role FROM users WHERE id = :uid"),
                {"uid": session['user_id']}
            ).fetchone()

        if not role_row or not role_row[0]:
            return jsonify({'success': False, 'message': 'Erişim reddedildi'}), 403

        # 4) Filtreleri hazırla
        q = (request.args.get('q') or '').strip()            # users.fullname üzerinde arama
        report_type = (request.args.get('type') or '').strip()
        date_from = (request.args.get('date_from') or '').strip()
        date_to = (request.args.get('date_to') or '').strip()

        where_clauses = []
        params = {}

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

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # 5) Toplam kayıt sayısı
        with get_db_connection() as conn:
            total_count = conn.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM reports r
                    JOIN users u ON r.id = u.id
                    {where_sql}
                """),
                params
            ).scalar() or 0

        # 6) Sayfa verisi (yeniden en yeni üstte)
        with get_db_connection() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT
                        r.id,
                        r.type,
                        r.date,
                        r.fullname,
                        u.fullname AS reporter_name,
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

        # 7) JSON dönüştürme
        items = []
        for row in rows:
            # row[2] tarih alanı olabilir
            raw_date = row[2]
            if isinstance(raw_date, datetime):
                date_value = raw_date.isoformat()
            else:
                date_value = str(raw_date) if raw_date is not None else None

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
            "next_offset": offset + len(items)
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500

def ensure_upload_dir():
    upload_dir = os.path.join('static', 'uploads')
    if not os.path.isdir(upload_dir):
        try:
            os.makedirs(upload_dir, exist_ok=True)
        except Exception as e:
            print('Upload klasörü oluşturulamadı:', e)
    return upload_dir

def ensure_reports_table_witnesses_column() -> bool:
    """
    reports tablosuna witnesses ve department sütunlarını ekler (yoksa).
    SQLAlchemy engine.begin() kullanır; hata olursa otomatik rollback yapar.
    """
    try:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE IF NOT EXISTS reports ADD COLUMN IF NOT EXISTS witnesses TEXT"))
            conn.execute(text("ALTER TABLE IF NOT EXISTS reports ADD COLUMN IF NOT EXISTS department VARCHAR(10)"))
        return True
    except Exception as e:
        app.logger.exception("reports tablosuna witnesses/department sütunu ekleme hatası")
        print("reports tablosuna witnesses/department sütunu ekleme hatası:", e)
        return False




@app.route('/submit-risk-report', methods=['POST'])
def submit_risk_report():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Giriş gerekli'}), 401

    department = request.form.get('department')
    risk_types = request.form.getlist('risk_type[]')  # çoklu seçim
    details = (request.form.get('details') or '').strip()

    if not department or not risk_types or len(details) < 5:
        return jsonify({'success': False, 'message': 'Eksik veya hatalı alanlar'}), 400

    # Görselleri kaydet
    upload_dir = ensure_upload_dir()
    saved_paths = []
    files = request.files.getlist('images[]') or []
    for f in files[:5]:
        if not f or not f.filename:
            continue
        if not f.mimetype or not f.mimetype.startswith('image/'):
            continue
        filename = secure_filename(f.filename)
        ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        _, ext = os.path.splitext(filename)
        final_name = f"{session['user_id']}_{ts}{ext.lower()}"
        filepath = os.path.join(upload_dir, final_name)
        try:
            f.save(filepath)
            saved_paths.append(f"/static/uploads/{final_name}")
        except Exception as e:
            app.logger.exception("Görsel kaydedilemedi")

    # reports tablosu için gerekli kolonları güvene al
    if not ensure_reports_table_witnesses_column():
        return jsonify({'success': False, 'message': 'Veritabanı hatası'}), 500

    # Raporu kaydet
    try:
        summary_type = "Risk Bildirim Raporlaması"
        # Görsel yollarını da detaylara eklemek istersen:
        attachments_text = f" | Görseller: {', '.join(saved_paths)}" if saved_paths else ""
        summary_details = (
            f"Departman: {department} | Risk Türleri: {', '.join(risk_types)} | "
            f"Detaylar: {details}{attachments_text}"
        )

        with db.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO reports (id, type, date, fullname, details, witnesses, department)
                    VALUES (:uid, :type, :date, :fullname, :details, :witnesses, :department)
                """),
                {
                    "uid": session['user_id'],
                    "type": summary_type,
                    "date": datetime.utcnow(),          # timestamp sütununa doğrudan datetime
                    "fullname": session.get('fullname', ''),
                    "details": summary_details,
                    "witnesses": None,
                    "department": department,
                }
            )

        return jsonify({'success': True, 'message': 'Risk raporu başarıyla kaydedildi'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/submit-event-report', methods=['POST'])
def submit_event_report():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Giriş gerekli'}), 401

    department  = request.form.get('department')
    event_types = request.form.getlist('event_type[]')  # çoklu seçim
    location    = (request.form.get('location') or '').strip()
    details     = (request.form.get('details') or '').strip()
    witnesses   = (request.form.get('witnesses') or '').strip()

    if not department or not event_types or not location or len(details) < 5:
        return jsonify({'success': False, 'message': 'Eksik veya hatalı alanlar'}), 400

    # Görselleri kaydet
    upload_dir  = ensure_upload_dir()
    saved_paths = []
    files = request.files.getlist('images[]') or []
    for f in files[:5]:
        if not f or not f.filename:
            continue
        if not f.mimetype or not f.mimetype.startswith('image/'):
            continue
        filename   = secure_filename(f.filename)
        ts         = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        _, ext     = os.path.splitext(filename)
        final_name = f"{session['user_id']}_{ts}{ext.lower()}"
        filepath   = os.path.join(upload_dir, final_name)
        try:
            f.save(filepath)
            saved_paths.append(f"/static/uploads/{final_name}")
        except Exception:
            app.logger.exception("Görsel kaydedilemedi")

    # reports tablosuna gerekli kolonları güvene al
    if not ensure_reports_table_witnesses_column():
        return jsonify({'success': False, 'message': 'Veritabanı hatası'}), 500

    # Sadece reports tablosuna kayıt
    try:
        summary_type = "Olay Bildirim Raporlaması"
        attachments_text = f" | Görseller: {', '.join(saved_paths)}" if saved_paths else ""
        summary_details = (
            f"Departman: {department} | Olay Türleri: {', '.join(event_types)} | "
            f"Yer: {location} | Detaylar: {details}{attachments_text}"
        )

        with db.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO reports (id, type, date, fullname, details, witnesses, department)
                    VALUES (:uid, :type, :date, :fullname, :details, :witnesses, :department)
                """),
                {
                    "uid": session['user_id'],
                    "type": summary_type,
                    "date": datetime.utcnow(),                 # timestamp sütununa direkt datetime
                    "fullname": session.get('fullname', ''),
                    "details": summary_details,
                    "witnesses": witnesses or None,
                    "department": department,
                }
            )

        return jsonify({'success': True, 'message': 'Olay raporu başarıyla kaydedildi'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = (request.form.get('fullname') or '').strip()
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''

        # Basit validasyon (opsiyonel güçlendirebilirsin)
        if not fullname or not email or not password:
            flash('Lütfen tüm alanları doldurun.', 'error')
            return render_template('register.html', active_page='register')

        try:
            # Transaction + auto-commit
            with db.engine.begin() as conn:
                # E-posta zaten kayıtlı mı?
                exists = conn.execute(
                    text("SELECT 1 FROM users WHERE LOWER(email) = LOWER(:e) LIMIT 1"),
                    {"e": email}
                ).fetchone()

                if exists:
                    flash('Bu e-posta adresi zaten kayıtlı!', 'error')
                    return render_template('register.html', active_page='register')

                # Şifreyi hash'le ve kaydet
                hashed_password = generate_password_hash(password)
                conn.execute(
                    text("""
                        INSERT INTO users (fullname, email, password, role)
                        VALUES (:fn, :em, :pw, :role)
                    """),
                    {"fn": fullname, "em": email, "pw": hashed_password, "role": False}
                )

            flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            # begin() bloğu hata alırsa otomatik rollback yapar
            flash(f'Kayıt hatası: {e}', 'error')
            return render_template('register.html', active_page='register')

    # GET isteği: önceki flash'ları temizle (isteğe bağlı)
    if '_flashes' in session:
        session.pop('_flashes', None)

    return render_template('register.html', active_page='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''

        try:
            # SQLAlchemy ile tek bağlantı
            with get_db_connection() as conn:
                user = conn.execute(
                    text("""
                        SELECT id, fullname, email, password, role
                        FROM users
                        WHERE email = :email
                        LIMIT 1
                    """),
                    {"email": email}
                ).fetchone()

            # Kullanıcı ve şifre doğrulama
            if user and check_password_hash(user[3], password):
                session['user_id'] = user[0]
                session['fullname'] = user[1]
                session['email'] = user[2]
                session['is_admin'] = bool(user[4])
                flash('Giriş başarılı!', 'success')
                return redirect(url_for('index'))
            else:
                flash('E-Postanız veya Şifreniz hatalı', 'error')
                return render_template('login.html', active_page='login')

        except Exception as e:
            flash(f'Giriş hatası: {e}', 'error')
            return render_template('login.html', active_page='login')

    # GET isteği: önceki flash'ları temizle (isteğe bağlı)
    if '_flashes' in session:
        session.pop('_flashes', None)

    return render_template('login.html', active_page='login')


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', active_page='profile')

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    email = (request.form.get('email') or '').strip()
    password = request.form.get('password') or ''

    if not email or not password:
        flash('E-posta ve şifre boş olamaz.', 'error')
        return redirect(url_for('profile'))

    try:
        with db.engine.begin() as conn:
            # E-posta başka kullanıcıda var mı?
            if email.lower() != session['email'].lower():
                exists = conn.execute(
                    text("SELECT 1 FROM users WHERE LOWER(email) = LOWER(:e) AND id != :uid"),
                    {"e": email, "uid": session['user_id']}
                ).fetchone()
                if exists:
                    flash('Bu e-posta adresi başka bir kullanıcı tarafından kullanılıyor!', 'error')
                    return redirect(url_for('profile'))

            # Şifreyi hash’le ve güncelle
            hashed_password = generate_password_hash(password)
            conn.execute(
                text("UPDATE users SET email = :e, password = :p WHERE id = :uid"),
                {"e": email, "p": hashed_password, "uid": session['user_id']}
            )

        # Session bilgisini güncelle
        session['email'] = email
        flash('Profil bilgileriniz başarıyla güncellendi!', 'success')
        return redirect(url_for('profile'))

    except Exception as e:
        # begin() bloğu hata alırsa otomatik rollback yapılır
        flash(f'Güncelleme hatası: {e}', 'error')
        return redirect(url_for('profile'))


# JSON tabanlı profil güncelleme API'leri
@app.route('/api/profile/email', methods=['POST'])
@login_required
def api_update_email():
    try:
        payload = request.get_json(silent=True) or {}
        new_email = (payload.get('email') or '').strip()

        if not new_email:
            return jsonify({'success': False, 'message': 'E-posta boş olamaz!'}), 400

        # Basit format kontrolü
        if '@' not in new_email or '.' not in new_email.split('@')[-1]:
            return jsonify({'success': False, 'message': 'Geçerli bir e-posta giriniz!'}), 400

        # Zaten aynıysa işlem yapma
        if new_email.lower() == (session.get('email') or '').lower():
            return jsonify({'success': True, 'message': 'E-posta zaten güncel.', 'email': session.get('email')})

        with db.engine.begin() as conn:
            # Başka kullanıcıda var mı?
            exists = conn.execute(
                text("""
                    SELECT 1 FROM users
                    WHERE LOWER(email) = LOWER(:e) AND id <> :uid
                    LIMIT 1
                """),
                {"e": new_email, "uid": session['user_id']}
            ).fetchone()

            if exists:
                return jsonify({'success': False, 'message': 'Bu e-posta başka bir kullanıcı tarafından kullanılıyor!'}), 409

            # Güncelle
            conn.execute(
                text("UPDATE users SET email = :e WHERE id = :uid"),
                {"e": new_email, "uid": session['user_id']}
            )

        # Session'ı güncelle
        session['email'] = new_email
        return jsonify({'success': True, 'message': 'E-posta güncellendi.', 'email': new_email})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500



@app.route('/api/profile/password', methods=['POST'])
@login_required
def api_update_password():
    try:
        payload = request.get_json(silent=True) or {}
        new_password = (payload.get('password') or '').strip()

        if not new_password or len(new_password) < 6:
            return jsonify({'success': False,
                            'message': 'Şifre en az 6 karakter olmalıdır!'}), 400

        hashed_password = generate_password_hash(new_password)

        # Transaction + auto-commit
        with db.engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET password = :p WHERE id = :uid"),
                {"p": hashed_password, "uid": session['user_id']}
            )

        return jsonify({'success': True, 'message': 'Şifre güncellendi.'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/submit-emergency-report', methods=['POST'])
@login_required
def submit_emergency_report():
    try:
        # (İstersen ayrı bir helper çağırma; DDL'yi burada güvenle yapabiliriz)
        with db.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE IF NOT EXISTS reports ADD COLUMN IF NOT EXISTS witnesses TEXT"
            ))

            # Rapor kaydı
            conn.execute(
                text("""
                    INSERT INTO reports (id, type, date, fullname, witnesses, department)
                    VALUES (:uid, :type, :date, :fullname, :witnesses, :department)
                """),
                {
                    "uid": session['user_id'],
                    "type": "Acil Yardım Sinyali",
                    "date": datetime.utcnow(),            # TS alanına direkt datetime ver
                    "fullname": session['fullname'],
                    "witnesses": None,
                    "department": None,
                }
            )

        return jsonify({'success': True, 'message': 'Acil yardım sinyali başarıyla gönderildi!'})

    except Exception as e:
        # begin() bloğu hata alırsa otomatik rollback yapar
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/check-new-reports')
@admin_required
def check_new_reports():
    try:
        # Tek bağlantı – with bloğu çıkışta otomatik kapanır
        with get_db_connection() as conn:
            rows = conn.execute(
                text("""
                    SELECT r.id,
                           r.type,
                           r.date,
                           r.fullname,
                           u.fullname AS reporter_name,
                           r.witnesses,
                           r.department
                    FROM reports r
                    JOIN users u ON r.id = u.id
                    WHERE r.date::timestamp >= NOW() - INTERVAL '10 second'
                    ORDER BY r.date DESC
                """)
            ).fetchall()

        # JSON’a dönüştür
        reports_data = [
            {
                "id": row[0],
                "type": row[1],
                "date": row[2].isoformat() if isinstance(row[2], datetime) else str(row[2]),
                "fullname": row[3],
                "reporter_name": row[4],
                "witnesses": row[5],
                "department": row[6],
            }
            for row in rows
        ]

        return jsonify({
            "success": True,
            "new_reports": reports_data,
            "count": len(reports_data),
        })

    except Exception as e:
        return jsonify({"success": False, "message": f"Hata: {e}"}), 500


@app.route('/check-admin-status')
@login_required
def check_admin_status():
    try:
        # Bağlantı otomatik kapanır
        with get_db_connection() as conn:
            row = conn.execute(
                text("SELECT role FROM users WHERE id = :uid"),
                {"uid": session['user_id']}
            ).fetchone()

        is_admin = bool(row[0]) if row else False

        return jsonify({
            "is_admin": is_admin,
            "success": True
        })

    except Exception as e:
        return jsonify({
            "is_admin": False,
            "message": f"Hata: {e}"
        }), 500


@app.route('/debug-reports')
@login_required
def debug_reports():
    try:
        with get_db_connection() as conn:
            # Tüm raporları getir (son 10 kayıt)
            all_reports = conn.execute(
                text("""
                    SELECT r.id, r.type, r.date, r.fullname,
                           u.fullname AS reporter_name,
                           r.witnesses, r.department
                    FROM reports r
                    JOIN users u ON r.id = u.id
                    ORDER BY r.date DESC
                    LIMIT 10
                """)
            ).fetchall()

            # Son 10 saniyede eklenen raporlar
            new_reports = conn.execute(
                text("""
                    SELECT r.id, r.type, r.date, r.fullname,
                           u.fullname AS reporter_name,
                           r.witnesses, r.department
                    FROM reports r
                    JOIN users u ON r.id = u.id
                    WHERE r.date::timestamp >= NOW() - INTERVAL '10 second'
                    ORDER BY r.date DESC
                """)
            ).fetchall()

        # JSON’a dönüştür
        def serialize(rows):
            return [
                {
                    "id": r[0],
                    "type": r[1],
                    "date": r[2].isoformat() if isinstance(r[2], datetime) else str(r[2]),
                    "fullname": r[3],
                    "reporter_name": r[4],
                    "witnesses": r[5],
                    "department": r[6],
                }
                for r in rows
            ]

        all_reports_data = serialize(all_reports)
        new_reports_data = serialize(new_reports)

        return jsonify({
            "success": True,
            "all_reports": all_reports_data,
            "new_reports": new_reports_data,
            "current_time": datetime.utcnow().isoformat(),
            "total_reports": len(all_reports_data),
            "new_reports_count": len(new_reports_data),
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Hata: {e}"
        }), 500


@app.route('/api/users/search')
@login_required
def search_users():
    try:
        query = (request.args.get('q') or '').strip()
        if len(query) < 2:
            return jsonify({'success': True, 'users': []})

        with get_db_connection() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, fullname
                    FROM users
                    WHERE LOWER(fullname) LIKE LOWER(:pattern)
                    ORDER BY fullname
                    LIMIT 10
                """),
                {"pattern": f"%{query}%"}
            ).fetchall()

        users = [{"id": r[0], "fullname": r[1]} for r in rows]

        return jsonify({'success': True, 'users': users})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Hata: {e}'}), 500


@app.route('/logout')
def logout():
    # Flash mesajlarını temizle
    if '_flashes' in session:
        session.pop('_flashes', None)
    
    session.clear()
    flash('Başarıyla çıkış yaptınız.', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)



