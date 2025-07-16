#!/usr/bin/env python3
"""
Script de test pour l'extraction CPFR
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.pptx_utils import extract_cpfr_pptx
import json

def test_cpfr_extraction(pptx_path):
    """Test l'extraction CPFR d'un fichier PowerPoint"""
    try:
        print(f"Test d'extraction CPFR pour: {pptx_path}")
        print("=" * 50)
        
        # Extraction des données CPFR
        cpfr_data, table_data = extract_cpfr_pptx(pptx_path, 31, 32)
        
        print("Données CPFR extraites:")
        print(json.dumps(cpfr_data, indent=2, default=str))
        
        print("\nDonnées du tableau:")
        print(json.dumps(table_data, indent=2, default=str))
        
        # Vérification des données clés
        print("\nVérification des données clés:")
        key_fields = ['sessions', 'revenue_b2c', 'average_basket_value', 'conversion_rate', 'nb_bookings']
        for field in key_fields:
            value = cpfr_data.get(field)
            print(f"  {field}: {value}")
        
        return cpfr_data
        
    except Exception as e:
        print(f"Erreur lors du test: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_cpfr_extraction.py <path_to_pptx>")
        sys.exit(1)
    
    pptx_path = sys.argv[1]
    if not os.path.exists(pptx_path):
        print(f"Fichier non trouvé: {pptx_path}")
        sys.exit(1)
    
    test_cpfr_extraction(pptx_path) 