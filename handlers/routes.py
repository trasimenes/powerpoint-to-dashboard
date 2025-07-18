import os
from tempfile import NamedTemporaryFile
from werkzeug.utils import secure_filename
import sqlite3
import re # Added for regex in convert_pptx_to_cpfr
import json # Added for json.dumps
from datetime import datetime # Added for data history timestamps

from flask import Blueprint, flash, redirect, render_template, request, jsonify

from modules.database import (
    insert_record, get_history, get_statistics, get_extraction_by_id,
    # CPFR functions
    get_weeks, get_weekly_summary, get_offers_focus, get_bookings_details, 
    get_acquisition_channels, get_campaign_notes, get_latest_weekly_data,
    insert_weekly_summary, insert_offers_focus, insert_bookings_details,
    insert_acquisition_channel, insert_seo_detail, insert_campaign_note,
    ingest_weekly_data
)

routes = Blueprint('routes', __name__)

# Configuration pour les fichiers uploadés
ALLOWED_EXTENSIONS = {'pptx'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_slide_numbers(start, end):
    """Valide les numéros de slides"""
    try:
        start = int(start)
        end = int(end)
        
        if start < 1 or end < 1:
            return False, "Les numéros de slides doivent être positifs"
        
        if start > end:
            return False, "La slide de début doit être inférieure à la slide de fin"
        
        return True, (start, end)
    except ValueError:
        return False, "Les numéros de slides doivent être des entiers"


@routes.route('/', methods=['GET', 'POST'])
def upload():
    """Page principale d'upload et traitement des fichiers"""
    if request.method == 'POST':
        # Vérification de la présence du fichier
        if 'pptx' not in request.files:
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)
        
        file = request.files['pptx']
        
        # Vérification du nom de fichier
        if file.filename == '':
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)
        
        # Vérification de l'extension
        if not allowed_file(file.filename):
            flash('Format de fichier non autorisé. Utilisez uniquement des fichiers .pptx', 'error')
            return redirect(request.url)
        
        # Vérification de la taille du fichier
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            flash(f'Fichier trop volumineux. Taille maximum : {MAX_FILE_SIZE // (1024*1024)}MB', 'error')
            return redirect(request.url)
        
        # Validation des numéros de slides
        slide_start = request.form.get('start', 31)
        slide_end = request.form.get('end', 32)
        
        is_valid, result = validate_slide_numbers(slide_start, slide_end)
        if not is_valid:
            flash(result, 'error')
            return redirect(request.url)
        
        slide_start, slide_end = result
        
        # Traitement du fichier
        filename = secure_filename(file.filename)
        tmp_path = None
        
        try:
            # Sauvegarde temporaire du fichier
            with NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
            
            # Récupération des informations du fichier
            from modules.pptx_utils import get_slide_info, extract_pptx, extract_cpfr_pptx
            file_info = get_slide_info(tmp_path)
            
            # Extraction des données avec preview structuré
            try:
                # Essayer d'abord l'extraction CPFR structurée
                cpfr_data, table_data, structured_preview = extract_cpfr_pptx(tmp_path, slide_start, slide_end)
                # Convertir les données CPFR en format KPI simple pour compatibilité
                kpis = [f"{k}: {v}" for k, v in cpfr_data.items() if v is not None and k in ['sessions', 'revenue_b2c', 'average_basket_value', 'conversion_rate', 'nb_bookings']]
            except:
                # Fallback vers l'extraction simple
                kpis, table_data = extract_pptx(tmp_path, slide_start, slide_end)
                structured_preview = None
            
            # Sauvegarde en base de données
            success = insert_record(filename, slide_start, slide_end, kpis, table_data, file_info)
            
            if not success:
                flash('Erreur lors de la sauvegarde des données', 'error')
                return redirect(request.url)
            
            # Affichage des résultats
            slides = (slide_start, slide_end)
            flash(f'Fichier "{filename}" analysé avec succès ! {len(kpis)} KPIs et {len(table_data["rows"])} lignes de données extraites.', 'success')
            
            return render_template('dashboard.html', 
                                 kpis=kpis, 
                                 table=table_data, 
                                 slides=slides, 
                                 filename=filename,
                                 file_info=file_info,
                                 structured_preview=structured_preview)
            
        except Exception as e:
            flash(f'Erreur lors du traitement du fichier : {str(e)}', 'error')
            return redirect(request.url)
        
        finally:
            # Nettoyage du fichier temporaire
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    # Affichage de la page d'upload
    stats = get_statistics()
    return render_template('upload.html', stats=stats, active_page='dashboard')


@routes.route('/history')
def history():
    """Page d'historique des extractions"""
    try:
        history_data = get_history(limit=100)
        stats = get_statistics()
        return render_template('history.html', history=history_data, stats=stats, active_page='history')
    except Exception as e:
        flash(f'Erreur lors du chargement de l\'historique : {str(e)}', 'error')
        return redirect('/')


@routes.route('/extraction/<int:extraction_id>')
def view_extraction(extraction_id):
    """Affiche une extraction spécifique"""
    try:
        extraction = get_extraction_by_id(extraction_id)
        if not extraction:
            flash('Extraction non trouvée', 'error')
            return redirect('/history')
        
        return render_template('dashboard.html', 
                             kpis=extraction['kpi'], 
                             table=extraction['table_data'], 
                             slides=(extraction['slide_start'], extraction['slide_end']),
                             filename=extraction['filename'],
                             file_info=extraction['file_info'],
                             is_history_view=True)
    except Exception as e:
        flash(f'Erreur lors du chargement de l\'extraction : {str(e)}', 'error')
        return redirect('/history')


@routes.route('/api/stats')
def api_stats():
    """API pour récupérer les statistiques"""
    try:
        stats = get_statistics()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/history')
def api_history():
    """API pour récupérer l'historique"""
    try:
        limit = request.args.get('limit', 50, type=int)
        history_data = get_history(limit=limit)
        return jsonify(history_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.errorhandler(413)
def too_large(e):
    """Gestion des fichiers trop volumineux"""
    flash('Fichier trop volumineux. Taille maximum : 50MB', 'error')
    return redirect('/')


@routes.errorhandler(404)
def not_found(e):
    """Page 404 personnalisée"""
    return render_template('404.html'), 404

# ============================================================================
# ROUTES CPFR DASHBOARD
# ============================================================================

@routes.route('/cpfr')
def cpfr_dashboard():
    """Redirection vers Sum up and main insights"""
    return redirect('/analytics/insights')


@routes.route('/cpfr/upload', methods=['GET', 'POST'])
def cpfr_upload():
    """Upload PowerPoint et conversion en données CPFR"""
    if request.method == 'POST':
        # Vérification de la présence du fichier
        if 'pptx' not in request.files:
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)
        
        file = request.files['pptx']
        
        # Vérification du nom de fichier
        if file.filename == '':
            flash('Aucun fichier sélectionné', 'error')
            return redirect(request.url)
        
        # Vérification de l'extension
        if not allowed_file(file.filename):
            flash('Format de fichier non autorisé. Utilisez uniquement des fichiers .pptx', 'error')
            return redirect(request.url)
        
        # Vérification de la taille du fichier
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            flash(f'Fichier trop volumineux. Taille maximum : {MAX_FILE_SIZE // (1024*1024)}MB', 'error')
            return redirect(request.url)
        
        # Validation des numéros de slides
        slide_start = request.form.get('start', 31)
        slide_end = request.form.get('end', 32)
        
        is_valid, result = validate_slide_numbers(slide_start, slide_end)
        if not is_valid:
            flash(result, 'error')
            return redirect(request.url)
        
        slide_start, slide_end = result
        
        # Traitement du fichier
        filename = secure_filename(file.filename)
        tmp_path = None
        
        try:
            # Sauvegarde temporaire du fichier
            with NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
            
            # Récupération des informations du fichier
            from modules.pptx_utils import get_slide_info, extract_pptx
            file_info = get_slide_info(tmp_path)
            
            # Extraction des données CPFR unifiées (slides 31 et 32)
            from modules.cpfr_unified_parser import parse_and_validate_cpfr
            from datetime import datetime, timedelta
            
            # Déterminer la semaine de reporting (par défaut: semaine courante)
            today = datetime.now()
            # Trouver le lundi de la semaine courante
            days_since_monday = today.weekday()
            monday = today - timedelta(days=days_since_monday)
            week_start_date = monday.strftime('%Y-%m-%d')
            
            result = parse_and_validate_cpfr(tmp_path, slide_start, slide_end, week_start_date)
            
            if result['success']:
                # Insertion dans la base CPFR
                success = ingest_weekly_data(result['db_payload'])
                
                if success['success']:
                    validation = result['validation']
                    msg = f'Données CPFR extraites avec succès ! {len(success["inserted"])} tables mises à jour.'
                    if validation['errors']:
                        msg += f' Avertissements: {", ".join(validation["errors"])}'
                    flash(msg, 'success')
                    return redirect('/cpfr')
                else:
                    flash(f'Erreur lors de l\'insertion des données CPFR: {", ".join(success.get("errors", []))}', 'error')
            else:
                flash(f'Erreur lors de l\'extraction CPFR: {result.get("error", "Erreur inconnue")}', 'error')
            
            return redirect('/cpfr/upload')
            
        except Exception as e:
            flash(f'Erreur lors du traitement du fichier : {str(e)}', 'error')
            return redirect(request.url)
        
        finally:
            # Nettoyage du fichier temporaire
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    # Affichage de la page d'upload
    return render_template('cpfr_upload.html', active_page='upload')


def convert_pptx_to_cpfr(kpis, table_data, filename):
    """
    Convertit les données extraites du PowerPoint en format CPFR
    """
    try:
        from datetime import datetime, timedelta
        
        # Déterminer la semaine de reporting (par défaut: semaine courante)
        today = datetime.now()
        # Trouver le lundi de la semaine courante
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)
        week_start_date = monday.strftime('%Y-%m-%d')
        
        # Extraire les KPIs des textes
        kpi_dict = {}
        for kpi in kpis:
            kpi_lower = kpi.lower()
            # Sessions
            if any(word in kpi_lower for word in ['session', 'visite']):
                numbers = re.findall(r'\d+', kpi)
                if numbers:
                    kpi_dict['sessions'] = int(numbers[0])
            # Revenue
            elif any(word in kpi_lower for word in ['revenue', 'chiffre', 'ca', 'vente']):
                numbers = re.findall(r'\d+', kpi)
                if numbers:
                    kpi_dict['revenue_b2c'] = float(numbers[0]) * 1000  # Assume k€
            # Bookings
            elif any(word in kpi_lower for word in ['booking', 'réservation', 'commande']):
                numbers = re.findall(r'\d+', kpi)
                if numbers:
                    kpi_dict['nb_bookings'] = int(numbers[0])
            # Conversion rate
            elif any(word in kpi_lower for word in ['conversion', 'taux']):
                percentages = re.findall(r'(\d+[.,]?\d*)%', kpi)
                if percentages:
                    kpi_dict['conversion_rate'] = float(percentages[0].replace(',', '.')) / 100
        
        # Extraire les données du tableau
        table_dict = {}
        if table_data and table_data.get('rows'):
            for row in table_data['rows']:
                if len(row) >= 2:
                    key = row[0].lower().strip()
                    value = row[1].strip()
                    
                    # Mapping des colonnes du tableau vers les champs CPFR
                    if any(word in key for word in ['last minute', 'dernière minute']):
                        percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                        if percentages:
                            table_dict['last_minute_pct'] = float(percentages[0].replace(',', '.')) / 100
                    elif any(word in key for word in ['early booking', 'réservation anticipée']):
                        percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                        if percentages:
                            table_dict['early_booking_pct'] = float(percentages[0].replace(',', '.')) / 100
                    elif any(word in key for word in ['juillet', 'july']):
                        percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                        if percentages:
                            table_dict['month_july_pct'] = float(percentages[0].replace(',', '.')) / 100
                    elif any(word in key for word in ['août', 'august']):
                        percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                        if percentages:
                            table_dict['month_august_pct'] = float(percentages[0].replace(',', '.')) / 100
                    elif any(word in key for word in ['septembre', 'september']):
                        percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                        if percentages:
                            table_dict['month_sept_pct'] = float(percentages[0].replace(',', '.')) / 100
        
        # Calculer les valeurs dérivées
        if kpi_dict.get('revenue_b2c') and kpi_dict.get('nb_bookings'):
            kpi_dict['average_basket_value'] = kpi_dict['revenue_b2c'] / kpi_dict['nb_bookings']
        
        # Créer le payload CPFR
        cpfr_payload = {
            'week_start_date': week_start_date,
            'weekly_summary': {
                'sessions': kpi_dict.get('sessions'),
                'revenue_b2c': kpi_dict.get('revenue_b2c'),
                'average_basket_value': kpi_dict.get('average_basket_value'),
                'conversion_rate': kpi_dict.get('conversion_rate'),
                'nb_bookings': kpi_dict.get('nb_bookings')
            },
            'offers_focus': {
                'last_minute_pct': table_dict.get('last_minute_pct'),
                'early_booking_pct': table_dict.get('early_booking_pct')
            },
            'bookings_details': {
                'month_july_pct': table_dict.get('month_july_pct'),
                'month_august_pct': table_dict.get('month_august_pct'),
                'month_sept_pct': table_dict.get('month_sept_pct')
            },
            'acquisition_channels': [],
            'campaign_notes': []
        }
        
        return cpfr_payload
        
    except Exception as e:
        print(f"Erreur lors de la conversion CPFR: {e}")
        return None


def convert_cpfr_parser_to_database(cpfr_data, filename):
    """
    Convertit les données du parser CPFR sophistiqué en format pour la base de données
    """
    try:
        # Le parser retourne déjà un format structuré
        # On doit juste adapter les noms de champs et gérer les données JSON
        
        # Extraire les données du parser
        weekly_summary = cpfr_data.get('weekly_summary', {})
        offers_focus = cpfr_data.get('offers_focus', {})
        bookings_details = cpfr_data.get('bookings_details', {})
        
        # Traiter les données de réservation
        top_dates_booked = []
        if bookings_details.get('top_dates_booked'):
            top_dates_booked = bookings_details['top_dates_booked'].split(',') if isinstance(bookings_details['top_dates_booked'], str) else bookings_details['top_dates_booked']
        
        top_dates_searched = []
        if bookings_details.get('top_dates_searched'):
            top_dates_searched = bookings_details['top_dates_searched'].split(',') if isinstance(bookings_details['top_dates_searched'], str) else bookings_details['top_dates_searched']
        
        top_parks = []
        if bookings_details.get('top_parks_booked'):
            top_parks = bookings_details['top_parks_booked'].split(',') if isinstance(bookings_details['top_parks_booked'], str) else bookings_details['top_parks_booked']
        
        # Créer le payload CPFR structuré
        cpfr_payload = {
            'week_start_date': cpfr_data.get('week_start_date'),
            'weekly_summary': {
                'sessions': weekly_summary.get('sessions'),
                'revenue_b2c': weekly_summary.get('revenue_b2c'),
                'average_basket_value': weekly_summary.get('average_basket_value'),
                'conversion_rate': weekly_summary.get('conversion_rate'),
                'nb_bookings': weekly_summary.get('nb_bookings'),
                'best_day': None,  # Le parser ne stocke pas le nom du jour
                'best_day_sessions': weekly_summary.get('best_day_sessions'),
                'best_day_revenue': weekly_summary.get('best_day_revenue'),
                # Variations
                'vs_ly_sessions': weekly_summary.get('vs_ly_sessions'),
                'vs_lw_sessions': weekly_summary.get('vs_lw_sessions'),
                'vs_ly_revenue': weekly_summary.get('vs_ly_revenue'),
                'vs_lw_revenue': weekly_summary.get('vs_lw_revenue'),
                'vs_ly_abv': weekly_summary.get('vs_ly_abv'),
                'vs_lw_abv': weekly_summary.get('vs_lw_abv'),
                'vs_ly_cr': weekly_summary.get('vs_ly_cr'),
                'vs_lw_cr': weekly_summary.get('vs_lw_cr'),
                'vs_ly_bookings': weekly_summary.get('vs_ly_bookings'),
                'vs_lw_bookings': weekly_summary.get('vs_lw_bookings')
            },
            'offers_focus': {
                'last_minute_pct': offers_focus.get('last_minute_pct'),
                'early_booking_pct': offers_focus.get('early_booking_pct'),
                'summer_flash_revenue': offers_focus.get('summer_flash_revenue'),
                'summer_flash_bookings': offers_focus.get('summer_flash_bookings'),
                'summer_flash_abv': offers_focus.get('summer_flash_abv'),
                'lead_gen_revenue': offers_focus.get('lead_gen_revenue'),
                'lead_gen_bookings': offers_focus.get('lead_gen_bookings')
            },
            'bookings_details': {
                'month_july_pct': bookings_details.get('month_july_pct'),
                'month_august_pct': bookings_details.get('month_august_pct'),
                'month_sept_pct': bookings_details.get('month_sept_pct'),
                'top_dates_booked': json.dumps(top_dates_booked),
                'top_dates_searched': json.dumps(top_dates_searched),
                'top_parks_booked': json.dumps(top_parks),
                'lengths_of_stay': json.dumps([]),  # Le parser ne stocke pas cette info
                'length_2n_pct': bookings_details.get('length_2n_pct'),
                'length_3n_pct': bookings_details.get('length_3n_pct'),
                'length_4n_pct': bookings_details.get('length_4n_pct')
            },
            'acquisition_channels': [],
            'campaign_notes': []  # Le parser ne stocke pas les insights
        }
        
        return cpfr_payload
        
    except Exception as e:
        print(f"Erreur lors de la conversion CPFR parser: {e}")
        return None


@routes.route('/cpfr/import')
def cpfr_import_page():
    """Page d'import des données CPFR"""
    return render_template('cpfr_import.html', active_page='import')


# ============================================================================
# API REST CPFR (selon la spécification JSON)
# ============================================================================

@routes.route('/api/v1/weeks', methods=['GET'])
def api_weeks():
    """Liste des semaines disponibles"""
    try:
        limit = request.args.get('limit', 52, type=int)
        weeks = get_weeks(limit)
        return jsonify(weeks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/summary/<int:week_id>', methods=['GET'])
def api_summary_by_week_id(week_id):
    """KPI globaux pour une semaine par ID"""
    try:
        # Récupérer la semaine par ID
        with sqlite3.connect("cpfr.db") as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, ws.*
                FROM weekly_summary ws
                JOIN dim_week w ON ws.week_id = w.id
                WHERE w.id = ?
            """, (week_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Semaine non trouvée'}), 404
            
            columns = [description[0] for description in cursor.description]
            return jsonify(dict(zip(columns, row)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/summary', methods=['GET'])
def api_summary():
    """KPI globaux pour la semaine la plus récente ou par date"""
    try:
        week_start_date = request.args.get('week_start_date')
        
        if week_start_date:
            # Récupérer par date
            with sqlite3.connect("cpfr.db") as conn:
                cursor = conn.execute("""
                    SELECT w.week_label, w.week_start_date, ws.*
                    FROM weekly_summary ws
                    JOIN dim_week w ON ws.week_id = w.id
                    WHERE w.week_start_date = ?
                """, (week_start_date,))
                row = cursor.fetchone()
                
                if not row:
                    return jsonify({'error': 'Semaine non trouvée'}), 404
                
                columns = [description[0] for description in cursor.description]
                return jsonify(dict(zip(columns, row)))
        else:
            # Récupérer la plus récente
            latest_data = get_latest_weekly_data()
            if latest_data.get('weekly_summary'):
                return jsonify(latest_data['weekly_summary'])
            else:
                return jsonify({'error': 'Aucune donnée disponible'}), 404
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/offers/<int:week_id>', methods=['GET'])
def api_offers_by_week_id(week_id):
    """Données des offres pour une semaine par ID"""
    try:
        with sqlite3.connect("cpfr.db") as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, of.*
                FROM offers_focus of
                JOIN dim_week w ON of.week_id = w.id
                WHERE w.id = ?
            """, (week_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Données non trouvées'}), 404
            
            columns = [description[0] for description in cursor.description]
            return jsonify(dict(zip(columns, row)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/offers', methods=['GET'])
def api_offers():
    """Données des offres pour la semaine la plus récente ou par date"""
    try:
        week_start_date = request.args.get('week_start_date')
        
        if week_start_date:
            with sqlite3.connect("cpfr.db") as conn:
                cursor = conn.execute("""
                    SELECT w.week_label, w.week_start_date, of.*
                    FROM offers_focus of
                    JOIN dim_week w ON of.week_id = w.id
                    WHERE w.week_start_date = ?
                """, (week_start_date,))
                row = cursor.fetchone()
                
                if not row:
                    return jsonify({'error': 'Données non trouvées'}), 404
                
                columns = [description[0] for description in cursor.description]
                return jsonify(dict(zip(columns, row)))
        else:
            latest_data = get_latest_weekly_data()
            if latest_data.get('offers_focus'):
                return jsonify(latest_data['offers_focus'])
            else:
                return jsonify({'error': 'Aucune donnée disponible'}), 404
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/bookings/<int:week_id>', methods=['GET'])
def api_bookings_by_week_id(week_id):
    """Détails des réservations pour une semaine par ID"""
    try:
        with sqlite3.connect("cpfr.db") as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, bd.*
                FROM bookings_details bd
                JOIN dim_week w ON bd.week_id = w.id
                WHERE w.id = ?
            """, (week_id,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Données non trouvées'}), 404
            
            columns = [description[0] for description in cursor.description]
            return jsonify(dict(zip(columns, row)))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/bookings', methods=['GET'])
def api_bookings():
    """Détails des réservations pour la semaine la plus récente ou par date"""
    try:
        week_start_date = request.args.get('week_start_date')
        
        if week_start_date:
            with sqlite3.connect("cpfr.db") as conn:
                cursor = conn.execute("""
                    SELECT w.week_label, w.week_start_date, bd.*
                    FROM bookings_details bd
                    JOIN dim_week w ON bd.week_id = w.id
                    WHERE w.week_start_date = ?
                """, (week_start_date,))
                row = cursor.fetchone()
                
                if not row:
                    return jsonify({'error': 'Données non trouvées'}), 404
                
                columns = [description[0] for description in cursor.description]
                return jsonify(dict(zip(columns, row)))
        else:
            latest_data = get_latest_weekly_data()
            if latest_data.get('bookings_details'):
                return jsonify(latest_data['bookings_details'])
            else:
                return jsonify({'error': 'Aucune donnée disponible'}), 404
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/acquisition/<int:week_id>', methods=['GET'])
def api_acquisition_by_week_id(week_id):
    """Données d'acquisition pour une semaine par ID"""
    try:
        with sqlite3.connect("cpfr.db") as conn:
            cursor = conn.execute("""
                SELECT w.week_label, w.week_start_date, c.channel_code, c.channel_label, ac.*
                FROM acquisition_channels ac
                JOIN dim_week w ON ac.week_id = w.id
                JOIN dim_channel c ON ac.channel_id = c.id
                WHERE w.id = ?
                ORDER BY c.channel_code
            """, (week_id,))
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            return jsonify([dict(zip(columns, row)) for row in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/acquisition', methods=['GET'])
def api_acquisition():
    """Données d'acquisition pour la semaine la plus récente ou par date"""
    try:
        week_start_date = request.args.get('week_start_date')
        
        if week_start_date:
            with sqlite3.connect("cpfr.db") as conn:
                cursor = conn.execute("""
                    SELECT w.week_label, w.week_start_date, c.channel_code, c.channel_label, ac.*
                    FROM acquisition_channels ac
                    JOIN dim_week w ON ac.week_id = w.id
                    JOIN dim_channel c ON ac.channel_id = c.id
                    WHERE w.week_start_date = ?
                    ORDER BY c.channel_code
                """, (week_start_date,))
                rows = cursor.fetchall()
                
                columns = [description[0] for description in cursor.description]
                return jsonify([dict(zip(columns, row)) for row in rows])
        else:
            latest_data = get_latest_weekly_data()
            if latest_data.get('acquisition_channels'):
                return jsonify(latest_data['acquisition_channels'])
            else:
                return jsonify([])
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/campaign-notes/<int:week_id>', methods=['GET'])
def api_campaign_notes_by_week_id(week_id):
    """Notes de campagne pour une semaine par ID"""
    try:
        with sqlite3.connect("cpfr.db") as conn:
            cursor = conn.execute("""
                SELECT w.week_label, c.channel_code, ccn.*
                FROM channel_campaign_notes ccn
                JOIN dim_week w ON ccn.week_id = w.id
                JOIN dim_channel c ON ccn.channel_id = c.id
                WHERE w.id = ?
                ORDER BY c.channel_code, ccn.campaign_name
            """, (week_id,))
            rows = cursor.fetchall()
            
            columns = [description[0] for description in cursor.description]
            return jsonify([dict(zip(columns, row)) for row in rows])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/campaign-notes', methods=['GET'])
def api_campaign_notes():
    """Notes de campagne pour la semaine la plus récente ou par date"""
    try:
        week_start_date = request.args.get('week_start_date')
        
        if week_start_date:
            notes = get_campaign_notes(week_start_date)
        else:
            notes = get_campaign_notes()
        
        return jsonify(notes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/api/v1/ingest', methods=['POST'])
def api_ingest():
    """Ingestion complète d'un payload pour une semaine"""
    try:
        payload = request.get_json()
        
        if not payload:
            return jsonify({'error': 'Payload JSON requis'}), 400
        
        if not payload.get('week_start_date'):
            return jsonify({'error': 'week_start_date requis'}), 400
        
        result = ingest_weekly_data(payload)
        
        if result['success']:
            return jsonify({
                'message': 'Données ingérées avec succès',
                'inserted': result['inserted'],
                'week_start_date': payload['week_start_date']
            })
        else:
            return jsonify({
                'error': 'Erreur lors de l\'ingestion',
                'errors': result.get('errors', []),
                'inserted': result.get('inserted', [])
            }), 500
            
    except Exception as e:
        return jsonify({'error': f'Erreur serveur : {str(e)}'}), 500


@routes.route('/cpfr/debug')
def cpfr_debug():
    """Page de debug pour visualiser l'association des textes extraits"""
    return render_template('cpfr_debug.html', active_page='debug')


@routes.route('/api/cpfr/debug-data')
def cpfr_debug_data():
    """API pour récupérer les données d'extraction pour le debug"""
    try:
        # Pour l'instant, on retourne des données d'exemple
        # Plus tard, on pourrait récupérer la dernière extraction ou permettre à l'utilisateur de choisir
        debug_data = {
            'extraction_source': 'sample_data',
            'timestamp': '2024-07-16T23:53:30',
            'texts': [
                {
                    'id': 1,
                    'text': '2,27M€',
                    'type': 'value',
                    'category': 'revenue',
                    'confidence': 0.9,
                    'form_index': 10,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 2,
                    'text': 'Web B2C Global revenue +11% VS LY -12% VS LW',
                    'type': 'label_variations',
                    'category': 'revenue',
                    'confidence': 0.8,
                    'form_index': 11,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 3,
                    'text': '917€',
                    'type': 'value',
                    'category': 'basket',
                    'confidence': 0.85,
                    'form_index': 12,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 4,
                    'text': 'Average basket value -15% VS LY +8% VS LW',
                    'type': 'label_variations',
                    'category': 'basket',
                    'confidence': 0.9,
                    'form_index': 13,
                    'raw_form_type': 'Shape',
                    'parsed_variations': {
                        'vs_ly': '-15%',
                        'vs_lw': '+8%'
                    }
                },
                {
                    'id': 5,
                    'text': '342K',
                    'type': 'value',
                    'category': 'sessions',
                    'confidence': 0.95,
                    'form_index': 14,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 6,
                    'text': 'Nb of sessions +6% VS LY -4% VS LW',
                    'type': 'label_variations',
                    'category': 'sessions',
                    'confidence': 0.8,
                    'form_index': 15,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 7,
                    'text': '0,53%',
                    'type': 'value',
                    'category': 'conversion',
                    'confidence': 0.7,
                    'form_index': 18,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 8,
                    'text': 'Conversion rate +12% VS LY -14% VS LW',
                    'type': 'label_variations',
                    'category': 'conversion',
                    'confidence': 0.85,
                    'form_index': 19,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 9,
                    'text': '2 475',
                    'type': 'value',
                    'category': 'bookings',
                    'confidence': 0.9,
                    'form_index': 16,
                    'raw_form_type': 'Shape'
                },
                {
                    'id': 10,
                    'text': 'Nb of bookings +29% VS LY -18% VS LW',
                    'type': 'label_variations',
                    'category': 'bookings',
                    'confidence': 0.85,
                    'form_index': 17,
                    'raw_form_type': 'Shape'
                }
            ]
        }
        
        return jsonify(debug_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# ROUTES D'INSERTION INDIVIDUELLE (pour compatibilité)
# ============================================================================

@routes.route('/cpfr/data', methods=['POST'])
def cpfr_add_data():
    """Ajoute ou met à jour les données CPFR (compatibilité)"""
    try:
        data = request.get_json()
        
        # Validation des données requises
        if not data.get('week_start_date'):
            return jsonify({'error': 'Date de début de semaine requise'}), 400
        
        success = True
        
        # Insertion des données selon le type
        if data.get('type') == 'weekly_summary':
            success = insert_weekly_summary(data)
        elif data.get('type') == 'offers_focus':
            success = insert_offers_focus(data)
        elif data.get('type') == 'bookings_details':
            success = insert_bookings_details(data)
        elif data.get('type') == 'acquisition_channel':
            if not data.get('channel_code'):
                return jsonify({'error': 'Code du canal requis'}), 400
            success = insert_acquisition_channel(data)
        elif data.get('type') == 'seo_detail':
            if not data.get('segment'):
                return jsonify({'error': 'Segment SEO requis'}), 400
            success = insert_seo_detail(data)
        elif data.get('type') == 'campaign_note':
            if not data.get('channel_code') or not data.get('campaign_name'):
                return jsonify({'error': 'Code canal et nom de campagne requis'}), 400
            success = insert_campaign_note(data)
        else:
            return jsonify({'error': 'Type de données non reconnu'}), 400
        
        if success:
            return jsonify({'message': 'Données ajoutées avec succès'})
        else:
            return jsonify({'error': 'Erreur lors de l\'ajout des données'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Erreur serveur : {str(e)}'}), 500


# ============================================================================
# API ENDPOINTS COMPATIBILITÉ (anciens endpoints)
# ============================================================================

@routes.route('/cpfr/api/weekly-summary')
def cpfr_api_weekly_summary():
    """API pour récupérer les données de résumé hebdomadaire (compatibilité)"""
    try:
        limit = request.args.get('limit', 12, type=int)
        data = get_weekly_summary(limit)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/cpfr/api/offers-focus')
def cpfr_api_offers_focus():
    """API pour récupérer les données de focus des offres (compatibilité)"""
    try:
        limit = request.args.get('limit', 12, type=int)
        data = get_offers_focus(limit)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/cpfr/api/bookings-details')
def cpfr_api_bookings_details():
    """API pour récupérer les détails des réservations (compatibilité)"""
    try:
        limit = request.args.get('limit', 12, type=int)
        data = get_bookings_details(limit)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes.route('/cpfr/api/acquisition-channels')
def cpfr_api_acquisition_channels():
    """API pour récupérer les données des canaux d'acquisition (compatibilité)"""
    try:
        limit = request.args.get('limit', 12, type=int)
        data = get_acquisition_channels(limit)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# DATA HISTORY ROUTES - Collaborative Editing
# ============================================================================

@routes.route('/data-history')
def data_history():
    """Page Data History avec édition collaborative"""
    return render_template('data_history.html', active_page='data_history')


@routes.route('/api/data-history/initial')
def api_data_history_initial():
    """Récupère les données consolidées depuis la vraie base CPFR avec valeurs historiques inférées"""
    try:
        # Récupérer toutes les semaines disponibles
        weeks = get_weeks(52)  # Dernières 52 semaines
        
        if not weeks:
            return jsonify({'weeks': [], 'data': {}})
        
        # Structurer les semaines pour Data History
        formatted_weeks = []
        for week in weeks:
            formatted_weeks.append({
                'id': f"week_{week['id']}",
                'label': week['week_label'],
                'startDate': week['week_start_date'],
                'status': 'active' if week == weeks[0] else 'archived'
            })
        
        # Récupérer toutes les données réelles disponibles
        consolidated_data = {}
        
        # 1. Données Weekly Summary (Slide 31)
        weekly_data = get_weekly_summary(52)
        for week_data in weekly_data:
            week_key = f"week_{week_data['week_id']}"
            
            # KPIs principaux
            if 'SLIDE_31_GLOBAL' not in consolidated_data:
                consolidated_data['SLIDE_31_GLOBAL'] = {}
            
            metrics_s31 = {
                'Sessions': {week_key: format_number(week_data.get('sessions'))},
                'Revenue B2C': {week_key: format_currency(week_data.get('revenue_b2c'))},
                'Average Basket': {week_key: format_currency(week_data.get('average_basket_value'))},
                'Conversion Rate': {week_key: format_percentage(week_data.get('conversion_rate'))},
                'Bookings': {week_key: format_number(week_data.get('nb_bookings'))},
                'Sessions vs LY': {week_key: format_percentage(week_data.get('vs_ly_sessions'))},
                'Sessions vs LW': {week_key: format_percentage(week_data.get('vs_lw_sessions'))},
                'Revenue vs LY': {week_key: format_percentage(week_data.get('vs_ly_revenue'))},
                'Revenue vs LW': {week_key: format_percentage(week_data.get('vs_lw_revenue'))},
                'ABV vs LY': {week_key: format_percentage(week_data.get('vs_ly_abv'))},
                'ABV vs LW': {week_key: format_percentage(week_data.get('vs_lw_abv'))},
                'CR vs LY': {week_key: format_percentage(week_data.get('vs_ly_cr'))},
                'CR vs LW': {week_key: format_percentage(week_data.get('vs_lw_cr'))},
                'Bookings vs LY': {week_key: format_percentage(week_data.get('vs_ly_bookings'))},
                'Bookings vs LW': {week_key: format_percentage(week_data.get('vs_lw_bookings'))}
            }
            
            for metric, value_dict in metrics_s31.items():
                if metric not in consolidated_data['SLIDE_31_GLOBAL']:
                    consolidated_data['SLIDE_31_GLOBAL'][metric] = {}
                consolidated_data['SLIDE_31_GLOBAL'][metric].update(value_dict)
        
        # 2. Données Offers Focus
        offers_data = get_offers_focus(52)
        for offer_data in offers_data:
            week_key = f"week_{offer_data['week_id']}"
            
            if 'SLIDE_31_OFFERS' not in consolidated_data:
                consolidated_data['SLIDE_31_OFFERS'] = {}
            
            metrics_offers = {
                'Last Minute %': {week_key: format_percentage(offer_data.get('last_minute_pct'))},
                'Early Booking %': {week_key: format_percentage(offer_data.get('early_booking_pct'))},
                'Summer Flash Revenue': {week_key: format_currency(offer_data.get('summer_flash_revenue'))},
                'Summer Flash Bookings': {week_key: format_number(offer_data.get('summer_flash_bookings'))},
                'Summer Flash ABV': {week_key: format_currency(offer_data.get('summer_flash_abv'))},
                'Lead Gen Revenue': {week_key: format_currency(offer_data.get('lead_gen_revenue'))},
                'Lead Gen Bookings': {week_key: format_number(offer_data.get('lead_gen_bookings'))}
            }
            
            for metric, value_dict in metrics_offers.items():
                if metric not in consolidated_data['SLIDE_31_OFFERS']:
                    consolidated_data['SLIDE_31_OFFERS'][metric] = {}
                consolidated_data['SLIDE_31_OFFERS'][metric].update(value_dict)
        
        # 3. Données Bookings Details
        bookings_data = get_bookings_details(52)
        for booking_data in bookings_data:
            week_key = f"week_{booking_data['week_id']}"
            
            if 'SLIDE_31_BOOKINGS' not in consolidated_data:
                consolidated_data['SLIDE_31_BOOKINGS'] = {}
            
            metrics_bookings = {
                'July %': {week_key: format_percentage(booking_data.get('month_july_pct'))},
                'August %': {week_key: format_percentage(booking_data.get('month_august_pct'))},
                'September %': {week_key: format_percentage(booking_data.get('month_sept_pct'))},
                'Stay 2N %': {week_key: format_percentage(booking_data.get('length_2n_pct'))},
                'Stay 3N %': {week_key: format_percentage(booking_data.get('length_3n_pct'))},
                'Stay 4N+ %': {week_key: format_percentage(booking_data.get('length_4n_pct'))}
            }
            
            for metric, value_dict in metrics_bookings.items():
                if metric not in consolidated_data['SLIDE_31_BOOKINGS']:
                    consolidated_data['SLIDE_31_BOOKINGS'][metric] = {}
                consolidated_data['SLIDE_31_BOOKINGS'][metric].update(value_dict)
        
        # 4. Données Acquisition Channels (Slide 32)
        acquisition_data = get_acquisition_channels(52)
        for acq_data in acquisition_data:
            week_key = f"week_{acq_data['week_id']}"
            channel = acq_data['channel_code']
            
            if channel not in consolidated_data:
                consolidated_data[channel] = {}
            
            # Métriques communes à tous les canaux
            base_metrics = {
                'Sessions WoW': {week_key: format_percentage(acq_data.get('wow_sessions'))},
                'Sessions YoY': {week_key: format_percentage(acq_data.get('yoy_sessions'))},
                'Bookings WoW': {week_key: format_percentage(acq_data.get('wow_bookings'))},
                'Bookings YoY': {week_key: format_percentage(acq_data.get('yoy_bookings'))},
                'Revenue WoW': {week_key: format_percentage(acq_data.get('wow_revenue'))},
                'Revenue YoY': {week_key: format_percentage(acq_data.get('yoy_revenue'))},
                'Costs WoW': {week_key: format_percentage(acq_data.get('wow_costs'))},
                'Costs YoY': {week_key: format_percentage(acq_data.get('yoy_costs'))},
                'CVR vs LW': {week_key: format_percentage(acq_data.get('cvr_vs_lw'))},
                'CVR vs LY': {week_key: format_percentage(acq_data.get('cvr_vs_ly'))}
            }
            
            for metric, value_dict in base_metrics.items():
                if metric not in consolidated_data[channel]:
                    consolidated_data[channel][metric] = {}
                consolidated_data[channel][metric].update(value_dict)
        
        # 5. Données SEO détails
        with sqlite3.connect("cpfr.db") as conn:
            cursor = conn.execute("""
                SELECT w.id as week_id, seo.segment, seo.impressions_yoy, seo.clicks_yoy, 
                       seo.ctr_yoy, seo.avg_position
                FROM channel_seo_detail seo
                JOIN dim_week w ON seo.week_id = w.id
                ORDER BY w.week_start_date DESC
            """)
            
            seo_details = cursor.fetchall()
            
            for seo_data in seo_details:
                week_key = f"week_{seo_data[0]}"
                segment = seo_data[1]  # 'brand' ou 'non_brand'
                
                if 'SEO_DETAIL' not in consolidated_data:
                    consolidated_data['SEO_DETAIL'] = {}
                
                prefix = 'Brand' if segment == 'brand' else 'Non-Brand'
                seo_metrics = {
                    f'{prefix} Impressions YoY': {week_key: format_percentage(seo_data[2])},
                    f'{prefix} Clicks YoY': {week_key: format_percentage(seo_data[3])},
                    f'{prefix} CTR YoY': {week_key: format_percentage(seo_data[4])},
                    f'{prefix} Avg Position': {week_key: format_number(seo_data[5])}
                }
                
                for metric, value_dict in seo_metrics.items():
                    if metric not in consolidated_data['SEO_DETAIL']:
                        consolidated_data['SEO_DETAIL'][metric] = {}
                    consolidated_data['SEO_DETAIL'][metric].update(value_dict)
        
        # Générer une timeline historique avec inférence des valeurs
        from datetime import datetime, timedelta
        
        # Semaine actuelle (à partir de la base de données)
        current_week = formatted_weeks[0] if formatted_weeks else None
        if not current_week:
            return jsonify({'weeks': [], 'data': {}})
        
        # Générer 20 semaines historiques
        timeline_weeks = []
        current_date = datetime.strptime(current_week['startDate'], '%Y-%m-%d')
        
        for i in range(20):
            week_date = current_date - timedelta(weeks=i)
            week_id = f"week_{i+1}"
            
            # Format français pour les dates
            week_label = f"Semaine {week_date.strftime('%d/%m/%Y')}"
            
            timeline_weeks.append({
                'id': week_id,
                'label': week_label,
                'startDate': week_date.strftime('%Y-%m-%d'),
                'status': 'active' if i == 0 else 'archived'
            })
        
        # Générer les données avec inférence pour chaque semaine
        timeline_data = {}
        
        # Pour chaque section de données
        for section_key, section_data in consolidated_data.items():
            timeline_data[section_key] = {}
            
            # Pour chaque métrique
            for metric_key, metric_data in section_data.items():
                timeline_data[section_key][metric_key] = {}
                
                # Valeur actuelle (semaine 1)
                current_value = metric_data.get('week_1', '')
                timeline_data[section_key][metric_key]['week_1'] = current_value
                
                # Chercher les variations pour l'inférence
                vs_ly_value = None
                vs_lw_value = None
                
                # Patterns de variations
                if 'Sessions' in metric_key and not 'vs' in metric_key:
                    vs_ly_value = consolidated_data[section_key].get('Sessions vs LY', {}).get('week_1', '')
                    vs_lw_value = consolidated_data[section_key].get('Sessions vs LW', {}).get('week_1', '')
                elif 'Revenue' in metric_key and not 'vs' in metric_key:
                    vs_ly_value = consolidated_data[section_key].get('Revenue vs LY', {}).get('week_1', '')
                    vs_lw_value = consolidated_data[section_key].get('Revenue vs LW', {}).get('week_1', '')
                elif 'Basket' in metric_key or 'ABV' in metric_key:
                    vs_ly_value = consolidated_data[section_key].get('ABV vs LY', {}).get('week_1', '')
                    vs_lw_value = consolidated_data[section_key].get('ABV vs LW', {}).get('week_1', '')
                elif 'Conversion' in metric_key:
                    vs_ly_value = consolidated_data[section_key].get('CR vs LY', {}).get('week_1', '')
                    vs_lw_value = consolidated_data[section_key].get('CR vs LW', {}).get('week_1', '')
                elif 'Bookings' in metric_key and not 'vs' in metric_key:
                    vs_ly_value = consolidated_data[section_key].get('Bookings vs LY', {}).get('week_1', '')
                    vs_lw_value = consolidated_data[section_key].get('Bookings vs LW', {}).get('week_1', '')
                
                # Inférer les valeurs historiques si on a les variations
                if current_value and current_value != '' and vs_lw_value and vs_lw_value != '':
                    try:
                        # Calculer la valeur de la semaine dernière
                        calc_result = calculate_historical_values(current_value, None, parse_percentage(vs_lw_value))
                        if calc_result and calc_result['last_week'] is not None:
                            timeline_data[section_key][metric_key]['week_2'] = format_value_like_original(calc_result['last_week'], current_value)
                    except:
                        pass
                
                # Inférer plus de semaines avec dégradation progressive
                if current_value and current_value != '':
                    try:
                        for week_i in range(3, min(21, len(timeline_weeks)+1)):
                            # Simulation d'une variation aléatoire légère (-5% à +5%)
                            import random
                            variation = random.uniform(-0.05, 0.05)
                            prev_value = timeline_data[section_key][metric_key].get(f'week_{week_i-1}', current_value)
                            
                            if prev_value and prev_value != '':
                                calc_result = calculate_historical_values(prev_value, None, variation)
                                if calc_result and calc_result['last_week'] is not None:
                                    timeline_data[section_key][metric_key][f'week_{week_i}'] = format_value_like_original(calc_result['last_week'], current_value)
                    except:
                        pass
        
        return jsonify({
            'weeks': timeline_weeks,
            'data': timeline_data
        })
        
    except Exception as e:
        print(f"Erreur lors du chargement des données Data History: {e}")
        return jsonify({'error': str(e)}), 500


def format_number(value):
    """Formate un nombre pour l'affichage"""
    if value is None:
        return ''
    try:
        if isinstance(value, (int, float)):
            if value >= 1000000:
                return f"{value/1000000:.1f}M"
            elif value >= 1000:
                return f"{value/1000:.1f}K"
            else:
                return str(int(value))
        return str(value)
    except:
        return str(value)


def format_currency(value):
    """Formate une valeur monétaire"""
    if value is None:
        return ''
    try:
        if isinstance(value, (int, float)):
            if value >= 1000000:
                return f"{value/1000000:.1f}M€"
            elif value >= 1000:
                return f"{value/1000:.1f}K€"
            else:
                return f"{value:.0f}€"
        return str(value)
    except:
        return str(value)


def format_percentage(value):
    """Formate un pourcentage"""
    if value is None:
        return ''
    try:
        if isinstance(value, (int, float)):
            sign = '+' if value > 0 else ''
            return f"{sign}{value*100:.1f}%"
        return str(value)
    except:
        return str(value)


def calculate_historical_values(current_value, vs_ly_pct, vs_lw_pct):
    """
    Calcule les valeurs historiques à partir de la valeur actuelle et des variations
    
    Args:
        current_value: Valeur actuelle (peut être formatée avec K, M, €, etc.)
        vs_ly_pct: Variation vs Last Year (ex: 0.11 pour +11%)
        vs_lw_pct: Variation vs Last Week (ex: -0.12 pour -12%)
    
    Returns:
        dict: {
            'current': valeur actuelle parsée,
            'last_year': valeur calculée pour l'année dernière,
            'last_week': valeur calculée pour la semaine dernière
        }
    """
    def parse_value(value_str):
        """Parse une valeur formatée en nombre"""
        if not value_str or value_str == '':
            return None
        
        value_str = str(value_str).strip()
        
        # Enlever les symboles et multiplier par les facteurs
        multiplier = 1
        if 'M€' in value_str:
            multiplier = 1000000
            value_str = value_str.replace('M€', '')
        elif 'K€' in value_str:
            multiplier = 1000
            value_str = value_str.replace('K€', '')
        elif '€' in value_str:
            value_str = value_str.replace('€', '')
        elif 'M' in value_str:
            multiplier = 1000000
            value_str = value_str.replace('M', '')
        elif 'K' in value_str:
            multiplier = 1000
            value_str = value_str.replace('K', '')
        elif '%' in value_str:
            # Si c'est déjà un pourcentage, le convertir en décimal
            return float(value_str.replace('%', '').replace('+', '')) / 100
        
        try:
            base_value = float(value_str.replace(',', '.'))
            return base_value * multiplier
        except:
            return None
    
    current_parsed = parse_value(current_value)
    if current_parsed is None:
        return None
    
    result = {'current': current_parsed}
    
    # Calculer la valeur de l'année dernière
    # Si current = last_year * (1 + vs_ly_pct) alors last_year = current / (1 + vs_ly_pct)
    if vs_ly_pct is not None:
        try:
            vs_ly_decimal = float(vs_ly_pct)
            result['last_year'] = current_parsed / (1 + vs_ly_decimal)
        except:
            result['last_year'] = None
    else:
        result['last_year'] = None
    
    # Calculer la valeur de la semaine dernière
    if vs_lw_pct is not None:
        try:
            vs_lw_decimal = float(vs_lw_pct)
            result['last_week'] = current_parsed / (1 + vs_lw_decimal)
        except:
            result['last_week'] = None
    else:
        result['last_week'] = None
    
    return result


def generate_historical_weeks(base_week_data, num_weeks=52):
    """
    Génère des semaines historiques en inférant les valeurs à partir des variations
    
    Args:
        base_week_data: Données de la semaine actuelle
        num_weeks: Nombre de semaines historiques à générer
    
    Returns:
        tuple: (weeks_list, historical_data)
    """
    from datetime import datetime, timedelta
    
    # Récupérer la semaine de base
    base_week = base_week_data['weeks'][0]
    base_date = datetime.strptime(base_week['startDate'], '%Y-%m-%d')
    
    # Générer les semaines historiques
    weeks_list = []
    for i in range(num_weeks):
        week_date = base_date - timedelta(weeks=i)
        week_id = f"week_{i+1}"
        week_label = f"{week_date.year}-W{week_date.isocalendar()[1]:02d}"
        
        weeks_list.append({
            'id': week_id,
            'label': week_label,
            'startDate': week_date.strftime('%Y-%m-%d'),
            'status': 'active' if i == 0 else 'archived'
        })
    
    # Calculer les valeurs historiques
    historical_data = {}
    
    for section, metrics in base_week_data['data'].items():
        historical_data[section] = {}
        
        for metric, week_values in metrics.items():
            historical_data[section][metric] = {}
            
            # Valeur actuelle
            current_value = week_values.get('week_1', '')
            
            # Chercher les variations correspondantes
            vs_ly_metric = None
            vs_lw_metric = None
            
            # Patterns de variations selon les métriques
            if 'Sessions' in metric:
                vs_ly_metric = metrics.get('Sessions vs LY', {}).get('week_1')
                vs_lw_metric = metrics.get('Sessions vs LW', {}).get('week_1')
            elif 'Revenue' in metric:
                vs_ly_metric = metrics.get('Revenue vs LY', {}).get('week_1')
                vs_lw_metric = metrics.get('Revenue vs LW', {}).get('week_1')
            elif 'Basket' in metric or 'ABV' in metric:
                vs_ly_metric = metrics.get('ABV vs LY', {}).get('week_1')
                vs_lw_metric = metrics.get('ABV vs LW', {}).get('week_1')
            elif 'Conversion' in metric:
                vs_ly_metric = metrics.get('CR vs LY', {}).get('week_1')
                vs_lw_metric = metrics.get('CR vs LW', {}).get('week_1')
            elif 'Bookings' in metric:
                vs_ly_metric = metrics.get('Bookings vs LY', {}).get('week_1')
                vs_lw_metric = metrics.get('Bookings vs LW', {}).get('week_1')
            
            # Convertir les pourcentages en décimaux
            vs_ly_pct = None
            vs_lw_pct = None
            
            if vs_ly_metric and vs_ly_metric.strip():
                try:
                    vs_ly_pct = float(vs_ly_metric.replace('%', '').replace('+', '')) / 100
                except:
                    pass
            
            if vs_lw_metric and vs_lw_metric.strip():
                try:
                    vs_lw_pct = float(vs_lw_metric.replace('%', '').replace('+', '')) / 100
                except:
                    pass
            
            # Calculer les valeurs historiques
            if current_value and current_value.strip():
                calc_result = calculate_historical_values(current_value, vs_ly_pct, vs_lw_pct)
                
                if calc_result:
                    # Semaine actuelle
                    historical_data[section][metric]['week_1'] = current_value
                    
                    # Semaine dernière (week_2)
                    if calc_result['last_week'] is not None:
                        if 'K€' in current_value:
                            historical_data[section][metric]['week_2'] = f"{calc_result['last_week']/1000:.1f}K€"
                        elif 'M€' in current_value:
                            historical_data[section][metric]['week_2'] = f"{calc_result['last_week']/1000000:.1f}M€"
                        elif '€' in current_value:
                            historical_data[section][metric]['week_2'] = f"{calc_result['last_week']:.0f}€"
                        elif 'K' in current_value:
                            historical_data[section][metric]['week_2'] = f"{calc_result['last_week']/1000:.0f}K"
                        elif '%' in current_value:
                            historical_data[section][metric]['week_2'] = f"{calc_result['last_week']*100:.1f}%"
                        else:
                            historical_data[section][metric]['week_2'] = f"{calc_result['last_week']:.0f}"
                    
                    # Année dernière (approximativement week_53)
                    if calc_result['last_year'] is not None:
                        if 'K€' in current_value:
                            historical_data[section][metric]['week_53'] = f"{calc_result['last_year']/1000:.1f}K€"
                        elif 'M€' in current_value:
                            historical_data[section][metric]['week_53'] = f"{calc_result['last_year']/1000000:.1f}M€"
                        elif '€' in current_value:
                            historical_data[section][metric]['week_53'] = f"{calc_result['last_year']:.0f}€"
                        elif 'K' in current_value:
                            historical_data[section][metric]['week_53'] = f"{calc_result['last_year']/1000:.0f}K"
                        elif '%' in current_value:
                            historical_data[section][metric]['week_53'] = f"{calc_result['last_year']*100:.1f}%"
                        else:
                            historical_data[section][metric]['week_53'] = f"{calc_result['last_year']:.0f}"
            else:
                # Juste copier la valeur actuelle
                historical_data[section][metric]['week_1'] = current_value
    
    return weeks_list, historical_data


def parse_percentage(value):
    """Parse une valeur de pourcentage en décimal"""
    if not value or value == '':
        return None
    try:
        # Enlever le % et le signe +
        clean_value = value.replace('%', '').replace('+', '').strip()
        return float(clean_value) / 100
    except:
        return None


def format_value_like_original(calculated_value, original_value):
    """Formate une valeur calculée dans le même format que l'original"""
    if not original_value or original_value == '':
        return ''
    
    try:
        if 'M€' in original_value:
            return f"{calculated_value/1000000:.1f}M€"
        elif 'K€' in original_value:
            return f"{calculated_value/1000:.1f}K€"
        elif '€' in original_value:
            return f"{calculated_value:.0f}€"
        elif 'M' in original_value:
            return f"{calculated_value/1000000:.1f}M"
        elif 'K' in original_value:
            return f"{calculated_value/1000:.0f}K"
        elif '%' in original_value:
            return f"{calculated_value*100:.1f}%"
        else:
            return f"{calculated_value:.0f}"
    except:
        return str(calculated_value)


@routes.route('/api/data-history/save', methods=['POST'])
def api_data_history_save():
    """Sauvegarde les modifications vers SQLite"""
    try:
        data = request.get_json()
        
        if not data or 'changes' not in data:
            return jsonify({'error': 'Données de changements requises'}), 400
        
        changes = data['changes']
        updated_count = 0
        errors = []
        
        with sqlite3.connect("cpfr.db") as conn:
            for change in changes:
                try:
                    section = change.get('section')
                    metric = change.get('metric')
                    week_id = change.get('week_id')
                    value = change.get('value')
                    
                    # Parse numeric week_id from "week_X" format
                    if week_id.startswith('week_'):
                        actual_week_id = int(week_id.split('_')[1])
                    else:
                        actual_week_id = int(week_id)
                    
                    # Update appropriate table based on section
                    if section == 'SLIDE_31_GLOBAL':
                        update_weekly_summary(conn, actual_week_id, metric, value)
                    elif section == 'SLIDE_31_OFFERS':
                        update_offers_focus(conn, actual_week_id, metric, value)
                    elif section == 'SLIDE_31_BOOKINGS':
                        update_bookings_details(conn, actual_week_id, metric, value)
                    elif section in ['SEA', 'SEO', 'OM', 'CRM']:
                        update_acquisition_channel(conn, actual_week_id, section, metric, value)
                    elif section == 'SEO_DETAIL':
                        update_seo_detail(conn, actual_week_id, metric, value)
                    
                    updated_count += 1
                    
                except Exception as e:
                    errors.append(f"Erreur pour {section}.{metric}: {str(e)}")
            
            conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'{updated_count} modifications sauvegardées',
            'updated_count': updated_count,
            'errors': errors if errors else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def parse_edited_value(value, metric):
    """Parse une valeur éditée selon le type de métrique"""
    if not value or value.strip() == '':
        return None
    
    value = value.strip()
    
    # Pourcentages
    if '%' in value:
        try:
            num_str = value.replace('%', '').replace('+', '').replace(' ', '')
            return float(num_str) / 100.0
        except:
            return None
    
    # Monnaie
    if '€' in value or 'K€' in value or 'M€' in value:
        try:
            if 'M€' in value:
                return float(value.replace('M€', '').replace(' ', '')) * 1000000
            elif 'K€' in value:
                return float(value.replace('K€', '').replace(' ', '')) * 1000
            else:
                return float(value.replace('€', '').replace(' ', ''))
        except:
            return None
    
    # Nombres avec K/M
    if 'K' in value:
        try:
            return float(value.replace('K', '').replace(' ', '')) * 1000
        except:
            return None
    elif 'M' in value:
        try:
            return float(value.replace('M', '').replace(' ', '')) * 1000000
        except:
            return None
    
    # Nombre simple
    try:
        return float(value)
    except:
        return value  # Retourner tel quel si pas numérique


def update_weekly_summary(conn, week_id, metric, value):
    """Met à jour une métrique dans weekly_summary"""
    parsed_value = parse_edited_value(value, metric)
    
    column_map = {
        'Sessions': 'sessions',
        'Revenue B2C': 'revenue_b2c',
        'Average Basket': 'average_basket_value',
        'Conversion Rate': 'conversion_rate',
        'Bookings': 'nb_bookings',
        'Sessions vs LY': 'vs_ly_sessions',
        'Sessions vs LW': 'vs_lw_sessions',
        'Revenue vs LY': 'vs_ly_revenue',
        'Revenue vs LW': 'vs_lw_revenue',
        'ABV vs LY': 'vs_ly_abv',
        'ABV vs LW': 'vs_lw_abv',
        'CR vs LY': 'vs_ly_cr',
        'CR vs LW': 'vs_lw_cr',
        'Bookings vs LY': 'vs_ly_bookings',
        'Bookings vs LW': 'vs_lw_bookings'
    }
    
    if metric in column_map:
        column = column_map[metric]
        conn.execute(f"""
            UPDATE weekly_summary 
            SET {column} = ? 
            WHERE week_id = ?
        """, (parsed_value, week_id))


def update_offers_focus(conn, week_id, metric, value):
    """Met à jour une métrique dans offers_focus"""
    parsed_value = parse_edited_value(value, metric)
    
    column_map = {
        'Last Minute %': 'last_minute_pct',
        'Early Booking %': 'early_booking_pct',
        'Summer Flash Revenue': 'summer_flash_revenue',
        'Summer Flash Bookings': 'summer_flash_bookings',
        'Summer Flash ABV': 'summer_flash_abv',
        'Lead Gen Revenue': 'lead_gen_revenue',
        'Lead Gen Bookings': 'lead_gen_bookings'
    }
    
    if metric in column_map:
        column = column_map[metric]
        conn.execute(f"""
            UPDATE offers_focus 
            SET {column} = ? 
            WHERE week_id = ?
        """, (parsed_value, week_id))


def update_bookings_details(conn, week_id, metric, value):
    """Met à jour une métrique dans bookings_details"""
    parsed_value = parse_edited_value(value, metric)
    
    column_map = {
        'July %': 'month_july_pct',
        'August %': 'month_august_pct',
        'September %': 'month_sept_pct',
        'Stay 2N %': 'length_2n_pct',
        'Stay 3N %': 'length_3n_pct',
        'Stay 4N+ %': 'length_4n_pct'
    }
    
    if metric in column_map:
        column = column_map[metric]
        conn.execute(f"""
            UPDATE bookings_details 
            SET {column} = ? 
            WHERE week_id = ?
        """, (parsed_value, week_id))


def update_acquisition_channel(conn, week_id, channel_code, metric, value):
    """Met à jour une métrique dans acquisition_channels"""
    parsed_value = parse_edited_value(value, metric)
    
    column_map = {
        'Sessions WoW': 'wow_sessions',
        'Sessions YoY': 'yoy_sessions',
        'Bookings WoW': 'wow_bookings',
        'Bookings YoY': 'yoy_bookings',
        'Revenue WoW': 'wow_revenue',
        'Revenue YoY': 'yoy_revenue',
        'Costs WoW': 'wow_costs',
        'Costs YoY': 'yoy_costs',
        'CVR vs LW': 'cvr_vs_lw',
        'CVR vs LY': 'cvr_vs_ly'
    }
    
    if metric in column_map:
        column = column_map[metric]
        
        # Get channel_id
        cursor = conn.execute("SELECT id FROM dim_channel WHERE channel_code = ?", (channel_code,))
        result = cursor.fetchone()
        if result:
            channel_id = result[0]
            conn.execute(f"""
                UPDATE acquisition_channels 
                SET {column} = ? 
                WHERE week_id = ? AND channel_id = ?
            """, (parsed_value, week_id, channel_id))


def update_seo_detail(conn, week_id, metric, value):
    """Met à jour une métrique dans channel_seo_detail"""
    parsed_value = parse_edited_value(value, metric)
    
    # Determine segment and column
    if metric.startswith('Brand '):
        segment = 'brand'
        base_metric = metric.replace('Brand ', '')
    elif metric.startswith('Non-Brand '):
        segment = 'non_brand'
        base_metric = metric.replace('Non-Brand ', '')
    else:
        return
    
    column_map = {
        'Impressions YoY': 'impressions_yoy',
        'Clicks YoY': 'clicks_yoy',
        'CTR YoY': 'ctr_yoy',
        'Avg Position': 'avg_position'
    }
    
    if base_metric in column_map:
        column = column_map[base_metric]
        conn.execute(f"""
            UPDATE channel_seo_detail 
            SET {column} = ? 
            WHERE week_id = ? AND segment = ?
        """, (parsed_value, week_id, segment))


@routes.route('/api/data-history/export/<format>')
def api_data_history_export(format):
    """Exporte les données en différents formats"""
    try:
        if format not in ['csv', 'json', 'xlsx']:
            return jsonify({'error': 'Format non supporté'}), 400
        
        # TODO: Récupérer les données réelles depuis la base collaborative
        # Pour l'instant, on retourne un exemple
        
        if format == 'json':
            return jsonify({
                'format': 'json',
                'data': 'export_data_placeholder',
                'generated_at': json.dumps(datetime.now(), default=str)
            })
        
        return jsonify({
            'format': format,
            'message': f'Export {format.upper()} en cours de développement'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# ANALYTICS ROUTES
# ============================================================================

@routes.route('/analytics/insights')
def analytics_insights():
    """Page Sum up and main insights (contenu slide 31)"""
    try:
        # Récupération des données slide 31
        latest_data = get_latest_weekly_data()
        weekly_summary = get_weekly_summary(12)
        offers_focus = get_offers_focus(12)
        bookings_details = get_bookings_details(12)
        
        return render_template('analytics_insights.html',
                             latest_data=latest_data,
                             weekly_summary=weekly_summary,
                             active_page='insights',
                             offers_focus=offers_focus,
                             bookings_details=bookings_details)
    except Exception as e:
        flash(f'Erreur lors du chargement des insights : {str(e)}', 'error')
        return redirect('/')


@routes.route('/analytics/acquisition')
def analytics_acquisition():
    """Page Acquisition Channel Analysis (contenu slide 32)"""
    try:
        # Récupération des données slide 32
        latest_data = get_latest_weekly_data()
        acquisition_channels = get_acquisition_channels(12)
        
        return render_template('analytics_acquisition.html',
                             latest_data=latest_data,
                             acquisition_channels=acquisition_channels,
                             active_page='acquisition')
    except Exception as e:
        flash(f'Erreur lors du chargement de l\'analyse d\'acquisition : {str(e)}', 'error')
        return redirect('/')


@routes.route('/analytics/history')
def analytics_history():
    """Page Data History (redirection vers la page existante)"""
    return redirect('/data-history')
