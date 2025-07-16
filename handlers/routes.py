import os
from tempfile import NamedTemporaryFile
from werkzeug.utils import secure_filename
import sqlite3
import re # Added for regex in convert_pptx_to_cpfr
import json # Added for json.dumps

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
            from modules.pptx_utils import get_slide_info, extract_pptx
            file_info = get_slide_info(tmp_path)
            
            # Extraction des données
            kpis, table_data = extract_pptx(tmp_path, slide_start, slide_end)
            
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
                                 file_info=file_info)
            
        except Exception as e:
            flash(f'Erreur lors du traitement du fichier : {str(e)}', 'error')
            return redirect(request.url)
        
        finally:
            # Nettoyage du fichier temporaire
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    # Affichage de la page d'upload
    stats = get_statistics()
    return render_template('upload.html', stats=stats)


@routes.route('/history')
def history():
    """Page d'historique des extractions"""
    try:
        history_data = get_history(limit=100)
        stats = get_statistics()
        return render_template('history.html', history=history_data, stats=stats)
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
    """Dashboard CPFR principal"""
    try:
        # Récupération des données
        latest_data = get_latest_weekly_data()
        weekly_summary = get_weekly_summary(12)
        offers_focus = get_offers_focus(12)
        bookings_details = get_bookings_details(12)
        acquisition_channels = get_acquisition_channels(12)
        
        return render_template('cpfr_dashboard.html', 
                             latest_data=latest_data,
                             weekly_summary=weekly_summary,
                             offers_focus=offers_focus,
                             bookings_details=bookings_details,
                             acquisition_channels=acquisition_channels)
    except Exception as e:
        flash(f'Erreur lors du chargement du dashboard CPFR : {str(e)}', 'error')
        return redirect('/')


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
    return render_template('cpfr_upload.html')


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
    return render_template('cpfr_import.html')


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
