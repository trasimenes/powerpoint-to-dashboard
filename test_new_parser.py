#!/usr/bin/env python3
"""
Script de test pour le nouveau parser CPFR sophistiqué
"""

import sys
import os
import json
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_cpfr_parser(pptx_path):
    """Test le nouveau parser CPFR"""
    try:
        print(f"Test du nouveau parser CPFR pour: {pptx_path}")
        print("=" * 60)
        
        # Calculer la semaine courante
        today = datetime.now()
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)
        week_start_date = monday.strftime('%Y-%m-%d')
        
        # Importer et utiliser le nouveau parser
        from modules.cpfr_pptx_parser import parse_cpfr_slide
        
        # Extraction avec le nouveau parser
        cpfr_data = parse_cpfr_slide(pptx_path, slide_number=31, week_start_date=week_start_date)
        
        print("Données extraites par le nouveau parser:")
        print(json.dumps(cpfr_data, indent=2, default=str))
        
        # Test de conversion vers la base de données
        from handlers.routes import convert_cpfr_parser_to_database
        db_payload = convert_cpfr_parser_to_database(cpfr_data, "test.pptx")
        
        print("\nPayload pour la base de données:")
        print(json.dumps(db_payload, indent=2, default=str))
        
        # Vérification des données clés
        print("\nVérification des données clés:")
        weekly = cpfr_data.get('weekly_summary', {})
        key_fields = ['sessions', 'revenue_b2c', 'average_basket_value', 'conversion_rate', 'nb_bookings']
        for field in key_fields:
            value = weekly.get(field)
            print(f"  {field}: {value}")
        
        # Vérification des variations
        print("\nVariations détectées:")
        variation_fields = [k for k in weekly.keys() if k.startswith('vs_')]
        for field in variation_fields:
            value = weekly.get(field)
            if value is not None:
                print(f"  {field}: {value:.4f} ({value*100:.1f}%)")
        
        return cpfr_data
        
    except Exception as e:
        print(f"Erreur lors du test: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_new_parser.py <path_to_pptx>")
        sys.exit(1)
    
    pptx_path = sys.argv[1]
    if not os.path.exists(pptx_path):
        print(f"Fichier non trouvé: {pptx_path}")
        sys.exit(1)
    
    test_cpfr_parser(pptx_path) 