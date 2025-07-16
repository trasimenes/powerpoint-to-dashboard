"""
cpfr_unified_parser.py

Parser unifié pour extraire les données CPFR des slides 31 (Summary) et 32 (Acquisition)
et les combiner en un payload structuré pour la base de données.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from .cpfr_pptx_parser import parse_cpfr_slide
from .cpfr_pptx_parser_acq import parse_acquisition_slide, build_acquisition_db_payload


def parse_cpfr_presentation(
    pptx_path: str,
    slide_31: int = 31,
    slide_32: int = 32,
    week_start_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parse les slides 31 et 32 d'une présentation CPFR et combine les données.
    
    Args:
        pptx_path: Chemin vers le fichier PowerPoint
        slide_31: Numéro de la slide de résumé (défaut: 31)
        slide_32: Numéro de la slide d'acquisition (défaut: 32)
        week_start_date: Date de début de semaine (YYYY-MM-DD)
    
    Returns:
        Dict structuré avec toutes les données CPFR
    """
    
    # Calculer la semaine courante si non fournie
    if not week_start_date:
        today = datetime.now()
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)
        week_start_date = monday.strftime('%Y-%m-%d')
    
    # Parser la slide 31 (Summary)
    print(f"Parsing slide {slide_31} (Summary)...")
    summary_data = parse_cpfr_slide(
        pptx_path, 
        slide_number=slide_31, 
        week_start_date=week_start_date
    )
    
    # Parser la slide 32 (Acquisition)
    print(f"Parsing slide {slide_32} (Acquisition)...")
    acquisition_data = parse_acquisition_slide(
        pptx_path, 
        slide_number=slide_32, 
        week_start_date=week_start_date
    )
    
    # Combiner les données
    combined_data = {
        "week_start_date": week_start_date,
        "summary": summary_data,
        "acquisition": acquisition_data,
        "parsed_at": datetime.now().isoformat()
    }
    
    return combined_data


def build_unified_db_payload(combined_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convertit les données combinées en payload pour la base de données.
    
    Args:
        combined_data: Données combinées de parse_cpfr_presentation()
    
    Returns:
        Payload structuré pour l'insertion en base
    """
    
    week_start_date = combined_data.get('week_start_date')
    summary = combined_data.get('summary', {})
    acquisition = combined_data.get('acquisition', {})
    
    # Extraire les données du résumé
    weekly_summary = summary.get('weekly_summary', {})
    offers_focus = summary.get('offers_focus', {})
    bookings_details = summary.get('bookings_details', {})
    
    # Traiter les données de réservation
    top_dates_booked = []
    if bookings_details.get('top_dates_booked'):
        if isinstance(bookings_details['top_dates_booked'], str):
            top_dates_booked = bookings_details['top_dates_booked'].split(',')
        else:
            top_dates_booked = bookings_details['top_dates_booked']
    
    top_dates_searched = []
    if bookings_details.get('top_dates_searched'):
        if isinstance(bookings_details['top_dates_searched'], str):
            top_dates_searched = bookings_details['top_dates_searched'].split(',')
        else:
            top_dates_searched = bookings_details['top_dates_searched']
    
    top_parks = []
    if bookings_details.get('top_parks_booked'):
        if isinstance(bookings_details['top_parks_booked'], str):
            top_parks = bookings_details['top_parks_booked'].split(',')
        else:
            top_parks = bookings_details['top_parks_booked']
    
    # Construire le payload unifié
    payload = {
        'week_start_date': week_start_date,
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
        }
    }
    
    # Ajouter les données d'acquisition si disponibles
    if acquisition and 'acquisition' in acquisition:
        acq_payload = build_acquisition_db_payload(acquisition)
        payload.update({
            'acquisition_channels': acq_payload.get('acquisition_channels', []),
            'channel_campaign_notes': acq_payload.get('channel_campaign_notes', []),
            'channel_seo_detail': acq_payload.get('channel_seo_detail', [])
        })
    else:
        payload.update({
            'acquisition_channels': [],
            'channel_campaign_notes': [],
            'channel_seo_detail': []
        })
    
    return payload


def parse_and_validate_cpfr(
    pptx_path: str,
    slide_31: int = 31,
    slide_32: int = 32,
    week_start_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parse et valide les données CPFR des deux slides.
    
    Returns:
        Dict avec les données parsées et les métadonnées de validation
    """
    
    try:
        # Parser les données
        combined_data = parse_cpfr_presentation(
            pptx_path, slide_31, slide_32, week_start_date
        )
        
        # Construire le payload pour la DB
        db_payload = build_unified_db_payload(combined_data)
        
        # Validation basique
        validation = {
            'summary_extracted': bool(combined_data.get('summary')),
            'acquisition_extracted': bool(combined_data.get('acquisition')),
            'has_kpis': bool(db_payload.get('weekly_summary', {}).get('sessions')),
            'has_acquisition': len(db_payload.get('acquisition_channels', [])) > 0,
            'errors': []
        }
        
        # Vérifier les données critiques
        weekly = db_payload.get('weekly_summary', {})
        if not weekly.get('sessions'):
            validation['errors'].append("Sessions non extraites")
        if not weekly.get('revenue_b2c'):
            validation['errors'].append("Revenue B2C non extraite")
        if not weekly.get('nb_bookings'):
            validation['errors'].append("Nombre de réservations non extrait")
        
        return {
            'success': True,
            'data': combined_data,
            'db_payload': db_payload,
            'validation': validation
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'data': None,
            'db_payload': None,
            'validation': {
                'summary_extracted': False,
                'acquisition_extracted': False,
                'has_kpis': False,
                'has_acquisition': False,
                'errors': [str(e)]
            }
        } 