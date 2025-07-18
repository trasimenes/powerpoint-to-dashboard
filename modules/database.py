import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
import calendar
from typing import Dict, List, Optional, Any

DB_PATH = Path("cpfr.db")

def init_db():
    """Initialise la base de données avec la structure CPFR complète"""
    with sqlite3.connect(DB_PATH) as conn:
        # Configuration SQLite
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        
        # Table de référence des semaines
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_week (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start_date DATE NOT NULL UNIQUE,
                iso_year INTEGER NOT NULL,
                iso_week INTEGER NOT NULL,
                week_label TEXT GENERATED ALWAYS AS (printf('%04d-W%02d', iso_year, iso_week)) VIRTUAL
            )
        """)
        
        # Table des canaux d'acquisition
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_channel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_code TEXT NOT NULL UNIQUE,
                channel_label TEXT NOT NULL
            )
        """)
        
        # KPI globaux agrégés par semaine
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_id INTEGER NOT NULL,
                sessions INTEGER,
                revenue_b2c REAL,
                average_basket_value REAL,
                conversion_rate REAL,
                nb_bookings INTEGER,
                vs_ly_sessions REAL,
                vs_lw_sessions REAL,
                vs_ly_revenue REAL,
                vs_lw_revenue REAL,
                vs_ly_abv REAL,
                vs_lw_abv REAL,
                vs_ly_cr REAL,
                vs_lw_cr REAL,
                vs_ly_bookings REAL,
                vs_lw_bookings REAL,
                best_day TEXT,
                best_day_sessions INTEGER,
                best_day_revenue REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (week_id) REFERENCES dim_week(id)
            )
        """)
        
        # Répartition et performance des offres
        conn.execute("""
            CREATE TABLE IF NOT EXISTS offers_focus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_id INTEGER NOT NULL,
                last_minute_pct REAL,
                early_booking_pct REAL,
                summer_flash_revenue REAL,
                summer_flash_bookings INTEGER,
                summer_flash_abv REAL,
                lead_gen_revenue REAL,
                lead_gen_bookings INTEGER,
                FOREIGN KEY (week_id) REFERENCES dim_week(id) ON DELETE CASCADE
            )
        """)
        
        # Détail des réservations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_id INTEGER NOT NULL,
                month_july_pct REAL,
                month_august_pct REAL,
                month_sept_pct REAL,
                top_dates_booked TEXT,
                top_dates_searched TEXT,
                top_parks_booked TEXT,
                lengths_of_stay TEXT,
                length_2n_pct REAL,
                length_3n_pct REAL,
                length_4n_pct REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (week_id) REFERENCES dim_week(id)
            )
        """)
        
        # KPI macro par canal
        conn.execute("""
            CREATE TABLE IF NOT EXISTS acquisition_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                sessions INTEGER,
                bookings INTEGER,
                revenue REAL,
                costs REAL,
                wow_sessions REAL,
                yoy_sessions REAL,
                wow_bookings REAL,
                yoy_bookings REAL,
                wow_revenue REAL,
                yoy_revenue REAL,
                wow_costs REAL,
                yoy_costs REAL,
                cvr_vs_lw REAL,
                cvr_vs_ly REAL,
                comments TEXT,
                FOREIGN KEY (week_id) REFERENCES dim_week(id) ON DELETE CASCADE,
                FOREIGN KEY (channel_id) REFERENCES dim_channel(id) ON DELETE CASCADE,
                UNIQUE (week_id, channel_id)
            )
        """)
        
        # Données SEO brand / non-brand
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_seo_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_id INTEGER NOT NULL,
                segment TEXT NOT NULL,
                impressions INTEGER,
                clicks INTEGER,
                ctr REAL,
                avg_position REAL,
                FOREIGN KEY (week_id) REFERENCES dim_week(id) ON DELETE CASCADE,
                UNIQUE (week_id, segment)
            )
        """)
        
        # Notes tactiques par canal et campagne
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channel_campaign_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                campaign_name TEXT NOT NULL,
                metric_bookings INTEGER,
                metric_revenue REAL,
                note TEXT,
                FOREIGN KEY (week_id) REFERENCES dim_week(id) ON DELETE CASCADE,
                FOREIGN KEY (channel_id) REFERENCES dim_channel(id) ON DELETE CASCADE
            )
        """)
        
        # Table existante pour les extractions PowerPoint (conservée pour compatibilité)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                filename TEXT NOT NULL,
                slide_start INTEGER NOT NULL,
                slide_end INTEGER NOT NULL,
                kpi TEXT NOT NULL,
                table_data TEXT NOT NULL,
                file_info TEXT,
                extraction_status TEXT DEFAULT 'success'
            )
        """)
        
        # Table pour les documents collaboratifs (Yjs)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collaborative_documents (
                doc_id TEXT PRIMARY KEY,
                document_type TEXT NOT NULL DEFAULT 'data-history',
                state BLOB,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                version INTEGER DEFAULT 1
            )
        """)
        
        # Indexes
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_summary_week ON weekly_summary(week_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_offers_focus_week ON offers_focus(week_id)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_details_week ON bookings_details(week_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_acq_week ON acquisition_channels(week_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_acq_channel ON acquisition_channels(channel_id)")
        
        # Vues SQL
        conn.execute("""
            CREATE VIEW IF NOT EXISTS vw_kpi_time_series AS 
            SELECT w.week_label, ws.sessions, ws.revenue_b2c, ws.average_basket_value, 
                   ws.conversion_rate, ws.nb_bookings 
            FROM weekly_summary ws 
            JOIN dim_week w ON ws.week_id = w.id 
            ORDER BY w.iso_year, w.iso_week
        """)
        
        conn.execute("""
            CREATE VIEW IF NOT EXISTS vw_offers_mix AS 
            SELECT w.week_label, of.last_minute_pct, of.early_booking_pct, 
                   (1.0 - COALESCE(of.last_minute_pct,0) - COALESCE(of.early_booking_pct,0)) AS other_pct 
            FROM offers_focus of 
            JOIN dim_week w ON of.week_id = w.id 
            ORDER BY w.iso_year, w.iso_week
        """)
        
        conn.execute("""
            CREATE VIEW IF NOT EXISTS vw_bookings_months AS 
            SELECT w.week_label, b.month_july_pct, b.month_august_pct, b.month_sept_pct 
            FROM bookings_details b 
            JOIN dim_week w ON b.week_id = w.id 
            ORDER BY w.iso_year, w.iso_week
        """)
        
        conn.execute("""
            CREATE VIEW IF NOT EXISTS vw_channel_revenue AS 
            SELECT w.week_label, c.channel_code, ac.revenue, ac.wow_revenue, ac.yoy_revenue 
            FROM acquisition_channels ac 
            JOIN dim_week w ON ac.week_id = w.id 
            JOIN dim_channel c ON ac.channel_id = c.id 
            ORDER BY w.iso_year, w.iso_week, c.channel_code
        """)
        
        # Seed des canaux d'acquisition
        seed_channels = [
            ("SEA", "Paid Search"),
            ("SEO", "Organic Search"),
            ("OM", "Online Marketing / Partenaires"),
            ("CRM", "CRM / Email / DB")
        ]
        
        for channel_code, channel_label in seed_channels:
            conn.execute("""
                INSERT OR IGNORE INTO dim_channel (channel_code, channel_label) 
                VALUES (?, ?)
            """, (channel_code, channel_label))
        
        conn.commit()


def get_or_create_week(week_start_date: str) -> int:
    """Récupère ou crée une semaine dans dim_week"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Vérifier si la semaine existe
            cursor = conn.execute(
                "SELECT id FROM dim_week WHERE week_start_date = ?",
                (week_start_date,)
            )
            existing = cursor.fetchone()
            
            if existing:
                return existing[0]
            
            # Calculer ISO year et week
            date_obj = datetime.strptime(week_start_date, "%Y-%m-%d").date()
            iso_year, iso_week, _ = date_obj.isocalendar()
            
            # Insérer la nouvelle semaine
            cursor = conn.execute(
                "INSERT INTO dim_week (week_start_date, iso_year, iso_week) VALUES (?, ?, ?)",
                (week_start_date, iso_year, iso_week)
            )
            conn.commit()
            return cursor.lastrowid
            
    except Exception as e:
        print(f"Erreur lors de la création/récupération de la semaine: {e}")
        raise


def get_channel_id(channel_code: str) -> Optional[int]:
    """Récupère l'ID d'un canal par son code"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT id FROM dim_channel WHERE channel_code = ?",
                (channel_code,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Erreur lors de la récupération du canal {channel_code}: {e}")
        return None


# ============================================================================
# FONCTIONS D'INSERTION CPFR
# ============================================================================

def insert_weekly_summary(data: Dict[str, Any]) -> bool:
    """Insère ou met à jour les données de résumé hebdomadaire"""
    try:
        week_id = get_or_create_week(data['week_start_date'])
        
        with sqlite3.connect(DB_PATH) as conn:
            # Vérifier si la semaine existe déjà
            cursor = conn.execute(
                "SELECT id FROM weekly_summary WHERE week_id = ?",
                (week_id,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Mise à jour
                conn.execute("""
                    UPDATE weekly_summary SET 
                    sessions = ?, revenue_b2c = ?, average_basket_value = ?, 
                    conversion_rate = ?, nb_bookings = ?, vs_ly_sessions = ?,
                    vs_lw_sessions = ?, vs_ly_revenue = ?, vs_lw_revenue = ?,
                    vs_ly_abv = ?, vs_lw_abv = ?, vs_ly_cr = ?, vs_lw_cr = ?,
                    vs_ly_bookings = ?, vs_lw_bookings = ?, best_day = ?,
                    best_day_sessions = ?, best_day_revenue = ?
                    WHERE week_id = ?
                """, (
                    data.get('sessions'), data.get('revenue_b2c'), data.get('average_basket_value'),
                    data.get('conversion_rate'), data.get('nb_bookings'), data.get('vs_ly_sessions'),
                    data.get('vs_lw_sessions'), data.get('vs_ly_revenue'), data.get('vs_lw_revenue'),
                    data.get('vs_ly_abv'), data.get('vs_lw_abv'), data.get('vs_ly_cr'), data.get('vs_lw_cr'),
                    data.get('vs_ly_bookings'), data.get('vs_lw_bookings'), data.get('best_day'),
                    data.get('best_day_sessions'), data.get('best_day_revenue'), week_id
                ))
            else:
                # Insertion
                conn.execute("""
                    INSERT INTO weekly_summary 
                    (week_id, sessions, revenue_b2c, average_basket_value, 
                     conversion_rate, nb_bookings, vs_ly_sessions, vs_lw_sessions,
                     vs_ly_revenue, vs_lw_revenue, vs_ly_abv, vs_lw_abv, vs_ly_cr,
                     vs_lw_cr, vs_ly_bookings, vs_lw_bookings, best_day, best_day_sessions, best_day_revenue)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    week_id, data.get('sessions'), data.get('revenue_b2c'),
                    data.get('average_basket_value'), data.get('conversion_rate'), data.get('nb_bookings'),
                    data.get('vs_ly_sessions'), data.get('vs_lw_sessions'), data.get('vs_ly_revenue'),
                    data.get('vs_lw_revenue'), data.get('vs_ly_abv'), data.get('vs_lw_abv'),
                    data.get('vs_ly_cr'), data.get('vs_lw_cr'), data.get('vs_ly_bookings'),
                    data.get('vs_lw_bookings'), data.get('best_day'), data.get('best_day_sessions'),
                    data.get('best_day_revenue')
                ))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion du résumé hebdomadaire: {e}")
        return False


def insert_offers_focus(data: Dict[str, Any]) -> bool:
    """Insère ou met à jour les données de focus des offres"""
    try:
        week_id = get_or_create_week(data['week_start_date'])
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT id FROM offers_focus WHERE week_id = ?",
                (week_id,)
            )
            existing = cursor.fetchone()
            
            if existing:
                conn.execute("""
                    UPDATE offers_focus SET 
                    last_minute_pct = ?, early_booking_pct = ?, summer_flash_revenue = ?,
                    summer_flash_bookings = ?, summer_flash_abv = ?, lead_gen_revenue = ?,
                    lead_gen_bookings = ?
                    WHERE week_id = ?
                """, (
                    data.get('last_minute_pct'), data.get('early_booking_pct'),
                    data.get('summer_flash_revenue'), data.get('summer_flash_bookings'),
                    data.get('summer_flash_abv'), data.get('lead_gen_revenue'),
                    data.get('lead_gen_bookings'), week_id
                ))
            else:
                conn.execute("""
                    INSERT INTO offers_focus 
                    (week_id, last_minute_pct, early_booking_pct, summer_flash_revenue,
                     summer_flash_bookings, summer_flash_abv, lead_gen_revenue, lead_gen_bookings)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    week_id, data.get('last_minute_pct'), data.get('early_booking_pct'),
                    data.get('summer_flash_revenue'), data.get('summer_flash_bookings'),
                    data.get('summer_flash_abv'), data.get('lead_gen_revenue'), data.get('lead_gen_bookings')
                ))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion du focus des offres: {e}")
        return False


def insert_bookings_details(data: Dict[str, Any]) -> bool:
    """Insère ou met à jour les détails des réservations"""
    try:
        week_id = get_or_create_week(data['week_start_date'])
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT id FROM bookings_details WHERE week_id = ?",
                (week_id,)
            )
            existing = cursor.fetchone()
            
            if existing:
                conn.execute("""
                    UPDATE bookings_details SET 
                    month_july_pct = ?, month_august_pct = ?, month_sept_pct = ?,
                    top_dates_booked = ?, top_dates_searched = ?, top_parks_booked = ?,
                    lengths_of_stay = ?, length_2n_pct = ?, length_3n_pct = ?, length_4n_pct = ?
                    WHERE week_id = ?
                """, (
                    data.get('month_july_pct'), data.get('month_august_pct'), data.get('month_sept_pct'),
                    data.get('top_dates_booked'), data.get('top_dates_searched'), data.get('top_parks_booked'),
                    data.get('lengths_of_stay'), data.get('length_2n_pct'), data.get('length_3n_pct'),
                    data.get('length_4n_pct'), week_id
                ))
            else:
                conn.execute("""
                    INSERT INTO bookings_details 
                    (week_id, month_july_pct, month_august_pct, month_sept_pct,
                     top_dates_booked, top_dates_searched, top_parks_booked,
                     lengths_of_stay, length_2n_pct, length_3n_pct, length_4n_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    week_id, data.get('month_july_pct'), data.get('month_august_pct'),
                    data.get('month_sept_pct'), data.get('top_dates_booked'), data.get('top_dates_searched'),
                    data.get('top_parks_booked'), data.get('lengths_of_stay'), data.get('length_2n_pct'),
                    data.get('length_3n_pct'), data.get('length_4n_pct')
                ))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion des détails des réservations: {e}")
        return False


def insert_acquisition_channel(data: Dict[str, Any]) -> bool:
    """Insère ou met à jour les données d'un canal d'acquisition"""
    try:
        week_id = get_or_create_week(data['week_start_date'])
        channel_id = get_channel_id(data['channel_code'])
        
        if not channel_id:
            print(f"Canal {data['channel_code']} non trouvé")
            return False
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT id FROM acquisition_channels WHERE week_id = ? AND channel_id = ?",
                (week_id, channel_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                conn.execute("""
                    UPDATE acquisition_channels SET 
                    sessions = ?, bookings = ?, revenue = ?, costs = ?,
                    wow_sessions = ?, yoy_sessions = ?, wow_bookings = ?, yoy_bookings = ?,
                    wow_revenue = ?, yoy_revenue = ?, wow_costs = ?, yoy_costs = ?,
                    cvr_vs_lw = ?, cvr_vs_ly = ?, comments = ?
                    WHERE week_id = ? AND channel_id = ?
                """, (
                    data.get('sessions'), data.get('bookings'), data.get('revenue'),
                    data.get('costs'), data.get('wow_sessions'), data.get('yoy_sessions'),
                    data.get('wow_bookings'), data.get('yoy_bookings'), data.get('wow_revenue'),
                    data.get('yoy_revenue'), data.get('wow_costs'), data.get('yoy_costs'),
                    data.get('cvr_vs_lw'), data.get('cvr_vs_ly'), data.get('comments'),
                    week_id, channel_id
                ))
            else:
                conn.execute("""
                    INSERT INTO acquisition_channels 
                    (week_id, channel_id, sessions, bookings, revenue, costs,
                     wow_sessions, yoy_sessions, wow_bookings, yoy_bookings,
                     wow_revenue, yoy_revenue, wow_costs, yoy_costs,
                     cvr_vs_lw, cvr_vs_ly, comments)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    week_id, channel_id, data.get('sessions'), data.get('bookings'),
                    data.get('revenue'), data.get('costs'), data.get('wow_sessions'),
                    data.get('yoy_sessions'), data.get('wow_bookings'), data.get('yoy_bookings'),
                    data.get('wow_revenue'), data.get('yoy_revenue'), data.get('wow_costs'),
                    data.get('yoy_costs'), data.get('cvr_vs_lw'), data.get('cvr_vs_ly'),
                    data.get('comments')
                ))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion du canal d'acquisition: {e}")
        return False


def insert_seo_detail(data: Dict[str, Any]) -> bool:
    """Insère ou met à jour les détails SEO"""
    try:
        week_id = get_or_create_week(data['week_start_date'])
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT id FROM channel_seo_detail WHERE week_id = ? AND segment = ?",
                (week_id, data['segment'])
            )
            existing = cursor.fetchone()
            
            if existing:
                conn.execute("""
                    UPDATE channel_seo_detail SET 
                    impressions = ?, clicks = ?, ctr = ?, avg_position = ?
                    WHERE week_id = ? AND segment = ?
                """, (
                    data.get('impressions'), data.get('clicks'), data.get('ctr'),
                    data.get('avg_position'), week_id, data['segment']
                ))
            else:
                conn.execute("""
                    INSERT INTO channel_seo_detail 
                    (week_id, segment, impressions, clicks, ctr, avg_position)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    week_id, data['segment'], data.get('impressions'), data.get('clicks'),
                    data.get('ctr'), data.get('avg_position')
                ))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion des détails SEO: {e}")
        return False


def insert_campaign_note(data: Dict[str, Any]) -> bool:
    """Insère une note de campagne"""
    try:
        week_id = get_or_create_week(data['week_start_date'])
        channel_id = get_channel_id(data['channel_code'])
        
        if not channel_id:
            print(f"Canal {data['channel_code']} non trouvé")
            return False
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO channel_campaign_notes 
                (week_id, channel_id, campaign_name, metric_bookings, metric_revenue, note)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                week_id, channel_id, data['campaign_name'], data.get('metric_bookings'),
                data.get('metric_revenue'), data.get('note')
            ))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion de la note de campagne: {e}")
        return False


# ============================================================================
# FONCTIONS DE RÉCUPÉRATION CPFR
# ============================================================================

def get_weeks(limit: int = 52) -> List[Dict[str, Any]]:
    """Récupère la liste des semaines disponibles"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT id, week_start_date, iso_year, iso_week, week_label
                FROM dim_week 
                ORDER BY week_start_date DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"Erreur lors de la récupération des semaines: {e}")
        return []


def get_weekly_summary(limit: int = 12) -> List[Dict[str, Any]]:
    """Récupère les données de résumé hebdomadaire avec jointure dim_week"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, ws.*
                FROM weekly_summary ws
                JOIN dim_week w ON ws.week_id = w.id
                ORDER BY w.week_start_date DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"Erreur lors de la récupération du résumé hebdomadaire: {e}")
        return []


def get_offers_focus(limit: int = 12) -> List[Dict[str, Any]]:
    """Récupère les données de focus des offres avec jointure dim_week"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, of.*
                FROM offers_focus of
                JOIN dim_week w ON of.week_id = w.id
                ORDER BY w.week_start_date DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"Erreur lors de la récupération du focus des offres: {e}")
        return []


def get_bookings_details(limit: int = 12) -> List[Dict[str, Any]]:
    """Récupère les détails des réservations"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, bd.*
                FROM bookings_details bd
                JOIN dim_week w ON bd.week_id = w.id
                ORDER BY w.iso_year DESC, w.iso_week DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            result = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                
                # Décoder les données JSON
                for field in ['top_dates_booked', 'top_dates_searched', 'top_parks_booked', 'lengths_of_stay']:
                    if row_dict.get(field):
                        try:
                            row_dict[field] = json.loads(row_dict[field])
                        except (json.JSONDecodeError, TypeError):
                            row_dict[field] = []
                    else:
                        row_dict[field] = []
                
                result.append(row_dict)
            
            return result
    except Exception as e:
        print(f"Erreur lors de la récupération des détails des réservations: {e}")
        return []


def get_acquisition_channels(limit: int = 12) -> List[Dict[str, Any]]:
    """Récupère les données des canaux d'acquisition avec jointures"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, c.channel_code, c.channel_label, ac.*
                FROM acquisition_channels ac
                JOIN dim_week w ON ac.week_id = w.id
                JOIN dim_channel c ON ac.channel_id = c.id
                ORDER BY w.week_start_date DESC, c.channel_code
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"Erreur lors de la récupération des canaux d'acquisition: {e}")
        return []


def get_campaign_notes(week_start_date: str = None) -> List[Dict[str, Any]]:
    """Récupère les notes de campagne"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if week_start_date:
                week_id = get_or_create_week(week_start_date)
                cursor = conn.execute("""
                    SELECT w.week_label, c.channel_code, ccn.*
                    FROM channel_campaign_notes ccn
                    JOIN dim_week w ON ccn.week_id = w.id
                    JOIN dim_channel c ON ccn.channel_id = c.id
                    WHERE ccn.week_id = ?
                    ORDER BY c.channel_code, ccn.campaign_name
                """, (week_id,))
            else:
                cursor = conn.execute("""
                    SELECT w.week_label, c.channel_code, ccn.*
                    FROM channel_campaign_notes ccn
                    JOIN dim_week w ON ccn.week_id = w.id
                    JOIN dim_channel c ON ccn.channel_id = c.id
                    ORDER BY w.week_start_date DESC, c.channel_code
                    LIMIT 50
                """)
            
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        print(f"Erreur lors de la récupération des notes de campagne: {e}")
        return []


def format_kpi_value(value, metric_type):
    """Formate une valeur KPI selon son type"""
    if value is None or value == 0:
        return None
    
    if metric_type == 'sessions':
        if value >= 1000:
            return f"{value/1000:.0f}K"
        else:
            return str(int(value))
    elif metric_type == 'revenue':
        if value >= 1000000:
            return f"{value/1000000:.2f}M€"
        elif value >= 1000:
            return f"{value/1000:.0f}K€"
        else:
            return f"{value:.0f}€"
    elif metric_type == 'basket_value':
        return f"{value:.0f}€"
    elif metric_type == 'conversion_rate':
        return f"{value*100:.2f}%"
    elif metric_type == 'bookings':
        if value >= 1000:
            return f"{value:,}".replace(',', ' ')
        else:
            return str(int(value))
    elif metric_type == 'percentage':
        if value == 0:
            return None
        sign = '+' if value > 0 else ''
        return f"{sign}{value*100:.0f}%"
    else:
        return str(value) if value is not None else None


def get_latest_weekly_data() -> Dict[str, Any]:
    """Récupère les données de la semaine la plus récente"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Résumé hebdomadaire
            weekly_cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, ws.*
                FROM weekly_summary ws
                JOIN dim_week w ON ws.week_id = w.id
                ORDER BY w.week_start_date DESC LIMIT 1
            """)
            weekly = weekly_cursor.fetchone()
            weekly_columns = [col[0] for col in weekly_cursor.description]
            
            # Focus des offres
            offers_cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, of.*
                FROM offers_focus of
                JOIN dim_week w ON of.week_id = w.id
                ORDER BY w.week_start_date DESC LIMIT 1
            """)
            offers = offers_cursor.fetchone()
            offers_columns = [col[0] for col in offers_cursor.description]
            
            # Détails des réservations
            bookings_cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, bd.*
                FROM bookings_details bd
                JOIN dim_week w ON bd.week_id = w.id
                ORDER BY w.week_start_date DESC LIMIT 1
            """)
            bookings = bookings_cursor.fetchone()
            bookings_columns = [col[0] for col in bookings_cursor.description]
            
            # Canaux d'acquisition
            channels_cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, c.channel_code, c.channel_label, ac.*
                FROM acquisition_channels ac
                JOIN dim_week w ON ac.week_id = w.id
                JOIN dim_channel c ON ac.channel_id = c.id
                WHERE w.week_start_date = (SELECT MAX(week_start_date) FROM dim_week)
                ORDER BY c.channel_code
            """)
            channels = channels_cursor.fetchall()
            channels_columns = [col[0] for col in channels_cursor.description]
            
            # Notes de campagne
            campaign_notes_cursor = conn.execute("""
                SELECT w.week_label, c.channel_code, ccn.*
                FROM channel_campaign_notes ccn
                JOIN dim_week w ON ccn.week_id = w.id
                JOIN dim_channel c ON ccn.channel_id = c.id
                WHERE w.week_start_date = (SELECT MAX(week_start_date) FROM dim_week)
                ORDER BY c.channel_code, ccn.campaign_name
            """)
            campaign_notes = campaign_notes_cursor.fetchall()
            campaign_notes_columns = [col[0] for col in campaign_notes_cursor.description]
            
            # Créer les dictionnaires avec les données brutes
            weekly_data = dict(zip(weekly_columns, weekly)) if weekly else None
            offers_data = dict(zip(offers_columns, offers)) if offers else None
            bookings_data = dict(zip(bookings_columns, bookings)) if bookings else None
            
            # Formater les valeurs du résumé hebdomadaire
            if weekly_data:
                weekly_data['sessions'] = format_kpi_value(weekly_data['sessions'], 'sessions')
                weekly_data['revenue_b2c'] = format_kpi_value(weekly_data['revenue_b2c'], 'revenue')
                weekly_data['average_basket_value'] = format_kpi_value(weekly_data['average_basket_value'], 'basket_value')
                weekly_data['conversion_rate'] = format_kpi_value(weekly_data['conversion_rate'], 'conversion_rate')
                weekly_data['nb_bookings'] = format_kpi_value(weekly_data['nb_bookings'], 'bookings')
                
                # Formater les variations
                weekly_data['vs_ly_sessions'] = format_kpi_value(weekly_data['vs_ly_sessions'], 'percentage')
                weekly_data['vs_lw_sessions'] = format_kpi_value(weekly_data['vs_lw_sessions'], 'percentage')
                weekly_data['vs_ly_revenue'] = format_kpi_value(weekly_data['vs_ly_revenue'], 'percentage')
                weekly_data['vs_lw_revenue'] = format_kpi_value(weekly_data['vs_lw_revenue'], 'percentage')
                weekly_data['vs_ly_abv'] = format_kpi_value(weekly_data['vs_ly_abv'], 'percentage')
                weekly_data['vs_lw_abv'] = format_kpi_value(weekly_data['vs_lw_abv'], 'percentage')
                weekly_data['vs_ly_cr'] = format_kpi_value(weekly_data['vs_ly_cr'], 'percentage')
                weekly_data['vs_lw_cr'] = format_kpi_value(weekly_data['vs_lw_cr'], 'percentage')
                weekly_data['vs_ly_bookings'] = format_kpi_value(weekly_data['vs_ly_bookings'], 'percentage')
                weekly_data['vs_lw_bookings'] = format_kpi_value(weekly_data['vs_lw_bookings'], 'percentage')
            
            # Formater les valeurs des offres
            if offers_data:
                offers_data['last_minute_pct'] = format_kpi_value(offers_data['last_minute_pct'], 'percentage')
                offers_data['early_booking_pct'] = format_kpi_value(offers_data['early_booking_pct'], 'percentage')
                offers_data['summer_flash_revenue'] = format_kpi_value(offers_data['summer_flash_revenue'], 'revenue')
                offers_data['summer_flash_bookings'] = format_kpi_value(offers_data['summer_flash_bookings'], 'bookings')
                offers_data['summer_flash_abv'] = format_kpi_value(offers_data['summer_flash_abv'], 'basket_value')
                offers_data['lead_gen_revenue'] = format_kpi_value(offers_data['lead_gen_revenue'], 'revenue')
                offers_data['lead_gen_bookings'] = format_kpi_value(offers_data['lead_gen_bookings'], 'bookings')
            
            # Formater les valeurs des détails des réservations
            if bookings_data:
                bookings_data['month_july_pct'] = format_kpi_value(bookings_data['month_july_pct'], 'percentage')
                bookings_data['month_august_pct'] = format_kpi_value(bookings_data['month_august_pct'], 'percentage')
                bookings_data['month_sept_pct'] = format_kpi_value(bookings_data['month_sept_pct'], 'percentage')
                bookings_data['length_2n_pct'] = format_kpi_value(bookings_data['length_2n_pct'], 'percentage')
                bookings_data['length_3n_pct'] = format_kpi_value(bookings_data['length_3n_pct'], 'percentage')
                bookings_data['length_4n_pct'] = format_kpi_value(bookings_data['length_4n_pct'], 'percentage')
            
            return {
                'weekly_summary': weekly_data,
                'offers_focus': offers_data,
                'bookings_details': bookings_data,
                'acquisition_channels': [dict(zip(channels_columns, row)) for row in channels],
                'campaign_notes': [dict(zip(campaign_notes_columns, row)) for row in campaign_notes]
            }
    except Exception as e:
        print(f"Erreur lors de la récupération des données hebdomadaires: {e}")
        return {}


# ============================================================================
# FONCTIONS D'INGESTION COMPLÈTE
# ============================================================================

def ingest_weekly_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ingère un payload complet pour une semaine"""
    try:
        week_start_date = payload.get('week_start_date')
        if not week_start_date:
            return {'success': False, 'error': 'week_start_date requis'}
        
        results = {'success': True, 'inserted': [], 'errors': []}
        
        # Weekly Summary
        if 'weekly_summary' in payload:
            if insert_weekly_summary({**payload['weekly_summary'], 'week_start_date': week_start_date}):
                results['inserted'].append('weekly_summary')
            else:
                results['errors'].append('weekly_summary')
                results['success'] = False
        
        # Offers Focus
        if 'offers_focus' in payload:
            if insert_offers_focus({**payload['offers_focus'], 'week_start_date': week_start_date}):
                results['inserted'].append('offers_focus')
            else:
                results['errors'].append('offers_focus')
                results['success'] = False
        
        # Bookings Details
        if 'bookings_details' in payload:
            if insert_bookings_details({**payload['bookings_details'], 'week_start_date': week_start_date}):
                results['inserted'].append('bookings_details')
            else:
                results['errors'].append('bookings_details')
                results['success'] = False
        
        # Acquisition Channels
        if 'acquisition_channels' in payload:
            for channel_data in payload['acquisition_channels']:
                if insert_acquisition_channel({**channel_data, 'week_start_date': week_start_date}):
                    results['inserted'].append(f"acquisition_channel_{channel_data.get('channel_code', 'unknown')}")
                else:
                    results['errors'].append(f"acquisition_channel_{channel_data.get('channel_code', 'unknown')}")
                    results['success'] = False
        
        # Campaign Notes
        if 'campaign_notes' in payload:
            for note_data in payload['campaign_notes']:
                if insert_campaign_note({**note_data, 'week_start_date': week_start_date}):
                    results['inserted'].append(f"campaign_note_{note_data.get('campaign_name', 'unknown')}")
                else:
                    results['errors'].append(f"campaign_note_{note_data.get('campaign_name', 'unknown')}")
                    results['success'] = False
        
        # SEO Details
        if 'seo_detail' in payload:
            for seo_data in payload['seo_detail']:
                if insert_seo_detail({**seo_data, 'week_start_date': week_start_date}):
                    results['inserted'].append(f"seo_detail_{seo_data.get('segment', 'unknown')}")
                else:
                    results['errors'].append(f"seo_detail_{seo_data.get('segment', 'unknown')}")
                    results['success'] = False
        
        return results
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================================
# FONCTIONS COMPATIBILITÉ (anciennes fonctions PowerPoint)
# ============================================================================

def insert_record(filename, slide_start, slide_end, kpi, table_data, file_info=None):
    """
    Insère un nouvel enregistrement d'extraction PowerPoint (compatibilité)
    """
    try:
        kpi_json = json.dumps(kpi, ensure_ascii=False) if kpi is not None else "[]"
        table_data_json = json.dumps(table_data, ensure_ascii=False) if table_data is not None else "{}"
        file_info_json = json.dumps(file_info, ensure_ascii=False) if file_info is not None else None
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO extractions 
                   (timestamp, filename, slide_start, slide_end, kpi, table_data, file_info, extraction_status) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
                    filename,
                    slide_start,
                    slide_end,
                    kpi_json,
                    table_data_json,
                    file_info_json,
                    'success'
                ),
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de l'insertion en base: {e}")
        return False


def get_history(limit=50):
    """Récupère l'historique des extractions PowerPoint (compatibilité)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                """SELECT timestamp, filename, slide_start, slide_end, kpi, table_data, file_info, extraction_status 
                   FROM extractions 
                   ORDER BY id DESC 
                   LIMIT ?""",
                (limit,)
            )
            rows = cursor.fetchall()
        
        history = []
        for row in rows:
            try:
                history.append({
                    "timestamp": row[0],
                    "filename": row[1],
                    "slide_start": row[2],
                    "slide_end": row[3],
                    "kpi": json.loads(row[4]) if row[4] else [],
                    "table_data": json.loads(row[5]) if row[5] else {"headers": [], "rows": []},
                    "file_info": json.loads(row[6]) if row[6] else {},
                    "extraction_status": row[7]
                })
            except json.JSONDecodeError:
                history.append({
                    "timestamp": row[0],
                    "filename": row[1],
                    "slide_start": row[2],
                    "slide_end": row[3],
                    "kpi": [],
                    "table_data": {"headers": [], "rows": []},
                    "file_info": {},
                    "extraction_status": row[7]
                })
        
        return history
    except Exception as e:
        print(f"Erreur lors de la récupération de l'historique: {e}")
        return []


def get_statistics():
    """Récupère des statistiques sur les extractions PowerPoint (compatibilité)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            total = conn.execute("SELECT COUNT(*) FROM extractions").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM extractions WHERE extraction_status = 'success'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM extractions WHERE extraction_status != 'success'").fetchone()[0]
            last_extraction = conn.execute("SELECT timestamp FROM extractions ORDER BY id DESC LIMIT 1").fetchone()
            
            return {
                "total_extractions": total,
                "successful_extractions": success,
                "failed_extractions": failed,
                "last_extraction": last_extraction[0] if last_extraction else None
            }
    except Exception as e:
        print(f"Erreur lors de la récupération des statistiques: {e}")
        return {
            "total_extractions": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "last_extraction": None
        }


def get_extraction_by_id(extraction_id):
    """Récupère une extraction spécifique par son ID (compatibilité)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                """SELECT timestamp, filename, slide_start, slide_end, kpi, table_data, file_info, extraction_status 
                   FROM extractions 
                   WHERE id = ?""",
                (extraction_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return {
                    "id": extraction_id,
                    "timestamp": row[0],
                    "filename": row[1],
                    "slide_start": row[2],
                    "slide_end": row[3],
                    "kpi": json.loads(row[4]) if row[4] else [],
                    "table_data": json.loads(row[5]) if row[5] else {"headers": [], "rows": []},
                    "file_info": json.loads(row[6]) if row[6] else {},
                    "extraction_status": row[7]
                }
            return None
    except Exception as e:
        print(f"Erreur lors de la récupération de l'extraction {extraction_id}: {e}")
        return None


def delete_extraction(extraction_id):
    """Supprime une extraction par son ID (compatibilité)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM extractions WHERE id = ?", (extraction_id,))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erreur lors de la suppression de l'extraction {extraction_id}: {e}")
        return False


# ============================================================================
# COLLABORATIVE DOCUMENTS (YJS/CRDT) FUNCTIONS
# ============================================================================

def get_or_create_document(doc_id: str, document_type: str = 'data-history') -> Optional[Dict[str, Any]]:
    """Récupère ou crée un document collaboratif"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT doc_id, document_type, state, metadata, created_at, updated_at, version
                FROM collaborative_documents 
                WHERE doc_id = ?
            """, (doc_id,))
            
            row = cursor.fetchone()
            
            if row:
                # Document existe, mettre à jour last_accessed
                conn.execute("""
                    UPDATE collaborative_documents 
                    SET last_accessed = CURRENT_TIMESTAMP 
                    WHERE doc_id = ?
                """, (doc_id,))
                conn.commit()
                
                return {
                    'doc_id': row[0],
                    'document_type': row[1],
                    'state': row[2],  # BLOB binary data
                    'metadata': json.loads(row[3]) if row[3] else {},
                    'created_at': row[4],
                    'updated_at': row[5],
                    'version': row[6]
                }
            else:
                # Créer nouveau document
                initial_metadata = {
                    'title': f'Data History - {doc_id}',
                    'collaborators': [],
                    'permissions': 'public'
                }
                
                conn.execute("""
                    INSERT INTO collaborative_documents 
                    (doc_id, document_type, state, metadata, version)
                    VALUES (?, ?, ?, ?, 1)
                """, (doc_id, document_type, None, json.dumps(initial_metadata)))
                conn.commit()
                
                return {
                    'doc_id': doc_id,
                    'document_type': document_type,
                    'state': None,
                    'metadata': initial_metadata,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat(),
                    'version': 1
                }
                
    except Exception as e:
        print(f"Erreur lors de la récupération/création du document {doc_id}: {e}")
        return None


def update_document_state(doc_id: str, state: bytes, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """Met à jour l'état d'un document collaboratif"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if metadata:
                conn.execute("""
                    UPDATE collaborative_documents 
                    SET state = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP, version = version + 1
                    WHERE doc_id = ?
                """, (state, json.dumps(metadata), doc_id))
            else:
                conn.execute("""
                    UPDATE collaborative_documents 
                    SET state = ?, updated_at = CURRENT_TIMESTAMP, version = version + 1
                    WHERE doc_id = ?
                """, (state, doc_id))
            
            conn.commit()
            return True
            
    except Exception as e:
        print(f"Erreur lors de la mise à jour du document {doc_id}: {e}")
        return False


def get_document_history(doc_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Récupère l'historique des versions d'un document"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT doc_id, version, updated_at, metadata
                FROM collaborative_documents 
                WHERE doc_id = ?
                ORDER BY version DESC
                LIMIT ?
            """, (doc_id, limit))
            
            return [
                {
                    'doc_id': row[0],
                    'version': row[1],
                    'updated_at': row[2],
                    'metadata': json.loads(row[3]) if row[3] else {}
                }
                for row in cursor.fetchall()
            ]
            
    except Exception as e:
        print(f"Erreur lors de la récupération de l'historique du document {doc_id}: {e}")
        return []


def list_collaborative_documents(document_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Liste tous les documents collaboratifs"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if document_type:
                cursor = conn.execute("""
                    SELECT doc_id, document_type, metadata, created_at, updated_at, last_accessed, version
                    FROM collaborative_documents 
                    WHERE document_type = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (document_type, limit))
            else:
                cursor = conn.execute("""
                    SELECT doc_id, document_type, metadata, created_at, updated_at, last_accessed, version
                    FROM collaborative_documents 
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,))
            
            return [
                {
                    'doc_id': row[0],
                    'document_type': row[1],
                    'metadata': json.loads(row[2]) if row[2] else {},
                    'created_at': row[3],
                    'updated_at': row[4],
                    'last_accessed': row[5],
                    'version': row[6]
                }
                for row in cursor.fetchall()
            ]
            
    except Exception as e:
        print(f"Erreur lors de la récupération de la liste des documents: {e}")
        return []


def delete_collaborative_document(doc_id: str) -> bool:
    """Supprime un document collaboratif"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("DELETE FROM collaborative_documents WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0
            
    except Exception as e:
        print(f"Erreur lors de la suppression du document {doc_id}: {e}")
        return False
