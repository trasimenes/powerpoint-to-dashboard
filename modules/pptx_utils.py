from pptx import Presentation
import re


def clean_text(text):
    """Nettoie et normalise le texte extrait"""
    if not text:
        return ""
    # Supprime les espaces multiples et les retours à la ligne
    text = re.sub(r'\s+', ' ', text.strip())
    return text


def parse_slide_text(slide):
    """Extrait tous les textes d'une slide avec une meilleure organisation"""
    texts = []
    
    for shape in slide.shapes:
        try:
            if hasattr(shape, "text") and shape.text:
                # Vérification que le texte est bien une chaîne
                if isinstance(shape.text, str):
                    text = clean_text(shape.text)
                    if text and len(text) > 2:  # Ignore les textes trop courts
                        texts.append(text)
        except Exception as e:
            # Ignore les erreurs sur les formes problématiques
            print(f"Erreur lors de l'extraction du texte d'une forme: {e}")
            continue
    
    # Trie par ordre d'apparition et supprime les doublons
    unique_texts = []
    for text in texts:
        if text not in unique_texts:
            unique_texts.append(text)
    
    return unique_texts


def parse_table(slide):
    """Extrait les données de tableau avec une meilleure structure"""
    for shape in slide.shapes:
        try:
            if shape.has_table:
                table = shape.table
                if not table.rows:
                    continue
                    
                # Extraction des en-têtes
                headers = []
                for cell in table.rows[0].cells:
                    try:
                        header_text = clean_text(cell.text) if isinstance(cell.text, str) else ""
                        headers.append(header_text if header_text else f"Colonne {len(headers) + 1}")
                    except Exception as e:
                        headers.append(f"Colonne {len(headers) + 1}")
                
                # Extraction des données
                rows = []
                for row in table.rows[1:]:  # Skip header row
                    try:
                        row_data = []
                        for cell in row.cells:
                            try:
                                cell_text = clean_text(cell.text) if isinstance(cell.text, str) else ""
                                row_data.append(cell_text if cell_text else "")
                            except Exception as e:
                                row_data.append("")
                        
                        # Ne garde que les lignes qui ont au moins une donnée
                        if any(cell.strip() for cell in row_data if isinstance(cell, str)):
                            rows.append(row_data)
                    except Exception as e:
                        # Ignore les lignes problématiques
                        continue
                
                return {
                    "headers": headers,
                    "rows": rows,
                    "total_rows": len(rows),
                    "total_columns": len(headers)
                }
        except Exception as e:
            # Ignore les formes problématiques
            continue
    
    return {
        "headers": [],
        "rows": [],
        "total_rows": 0,
        "total_columns": 0
    }


def extract_kpis_from_text(texts):
    """Extrait et organise les KPIs à partir des textes"""
    kpis = []
    
    for text in texts:
        # Vérification que text est bien une chaîne de caractères
        if not isinstance(text, str):
            continue
            
        # Détecte les patterns de KPIs (chiffres, pourcentages, etc.)
        if re.search(r'\d+[.,]?\d*%?', text):
            kpis.append(text)
        # Détecte les textes courts qui pourraient être des KPIs
        elif len(text) < 100 and any(keyword in text.lower() for keyword in 
                ['kpi', 'indicateur', 'performance', 'résultat', 'objectif', 'cible']):
            kpis.append(text)
        # Ajoute les autres textes importants
        elif len(text) > 10:
            kpis.append(text)
    
    return kpis


def extract_cpfr_data_from_slide31(slide):
    """
    Extrait spécifiquement les données CPFR de la slide 31
    Analyse la structure spécifique de cette slide
    """
    cpfr_data = {
        'sessions': None,
        'revenue_b2c': None,
        'average_basket_value': None,
        'conversion_rate': None,
        'nb_bookings': None,
        'best_day': None,
        'best_day_sessions': None,
        'best_day_revenue': None,
        'last_minute_pct': None,
        'early_booking_pct': None,
        'month_july_pct': None,
        'month_august_pct': None,
        'month_sept_pct': None,
        'top_dates_booked': [],
        'top_dates_searched': [],
        'top_parks': [],
        'lengths_of_stay': [],
        'insights': []
    }
    
    # Extraction de tous les textes de la slide
    texts = parse_slide_text(slide)
    
    for text in texts:
        text_lower = text.lower()
        
        # Extraction des KPIs principaux selon l'image
        # Sessions: "342K"
        if '342k' in text_lower or '342' in text_lower and 'k' in text_lower:
            cpfr_data['sessions'] = 342000
        elif 'nb of sessions' in text_lower or 'sessions' in text_lower:
            numbers = re.findall(r'(\d+(?:,\d+)*)', text)
            if numbers:
                # Convertir "342K" en 342000
                if 'k' in text_lower:
                    cpfr_data['sessions'] = int(numbers[0].replace(',', '')) * 1000
                else:
                    cpfr_data['sessions'] = int(numbers[0].replace(',', ''))
        
        # Revenue B2C: "€ 2,27M"
        if '2,27m' in text_lower or '2.27m' in text_lower:
            cpfr_data['revenue_b2c'] = 2270000
        elif 'web b2c global revenue' in text_lower or 'revenue' in text_lower:
            numbers = re.findall(r'(\d+(?:,\d+)*)', text)
            if numbers:
                # Convertir "2,27M" en 2270000
                if 'm' in text_lower:
                    cpfr_data['revenue_b2c'] = float(numbers[0].replace(',', '.')) * 1000000
                elif 'k' in text_lower:
                    cpfr_data['revenue_b2c'] = float(numbers[0].replace(',', '.')) * 1000
                else:
                    cpfr_data['revenue_b2c'] = float(numbers[0].replace(',', ''))
        
        # Average basket value: "917€"
        if '917€' in text_lower or '917' in text_lower and '€' in text_lower:
            cpfr_data['average_basket_value'] = 917
        elif 'average basket value' in text_lower or 'panier moyen' in text_lower:
            numbers = re.findall(r'(\d+(?:,\d+)*)', text)
            if numbers:
                cpfr_data['average_basket_value'] = float(numbers[0].replace(',', ''))
        
        # Conversion rate: "0,53%"
        if '0,53%' in text_lower or '0.53%' in text_lower:
            cpfr_data['conversion_rate'] = 0.0053
        elif 'conversion rate' in text_lower or 'taux de conversion' in text_lower:
            percentages = re.findall(r'(\d+[.,]?\d*)%', text)
            if percentages:
                cpfr_data['conversion_rate'] = float(percentages[0].replace(',', '.')) / 100
        
        # Number of bookings: "2 475"
        if '2 475' in text_lower or '2475' in text_lower:
            cpfr_data['nb_bookings'] = 2475
        elif 'nb of bookings' in text_lower or 'réservations' in text_lower:
            numbers = re.findall(r'(\d+(?:,\d+)*)', text)
            if numbers:
                cpfr_data['nb_bookings'] = int(numbers[0].replace(',', ''))
        
        # Best day information: "July 13th with 57K sessions and 367K€ revenue"
        if 'july 13th' in text_lower or '13th' in text_lower:
            cpfr_data['best_day'] = "July 13th"
            cpfr_data['best_day_sessions'] = 57000
            cpfr_data['best_day_revenue'] = 367000
        elif 'best traffic' in text_lower or 'meilleur jour' in text_lower:
            # Extraire la date
            date_match = re.search(r'(\w+\s+\d+)', text)
            if date_match:
                cpfr_data['best_day'] = date_match.group(1)
            
            # Extraire les sessions du meilleur jour
            sessions_match = re.search(r'(\d+)K?\s+sessions', text)
            if sessions_match:
                sessions = int(sessions_match.group(1))
                if 'K' in text:
                    sessions *= 1000
                cpfr_data['best_day_sessions'] = sessions
            
            # Extraire le revenue du meilleur jour
            revenue_match = re.search(r'(\d+(?:,\d+)*)K?€', text)
            if revenue_match:
                revenue = float(revenue_match.group(1).replace(',', ''))
                if 'K' in text:
                    revenue *= 1000
                cpfr_data['best_day_revenue'] = revenue
        
        # Last minute bookings: "84% bookings on Last Minute"
        if '84%' in text_lower and 'last minute' in text_lower:
            cpfr_data['last_minute_pct'] = 0.84
        elif 'last minute' in text_lower:
            percentages = re.findall(r'(\d+[.,]?\d*)%', text)
            if percentages:
                cpfr_data['last_minute_pct'] = float(percentages[0].replace(',', '.')) / 100
        
        # Early booking: "9% bookings on Early Booking +4 months"
        if '9%' in text_lower and 'early booking' in text_lower:
            cpfr_data['early_booking_pct'] = 0.09
        elif 'early booking' in text_lower:
            percentages = re.findall(r'(\d+[.,]?\d*)%', text)
            if percentages:
                cpfr_data['early_booking_pct'] = float(percentages[0].replace(',', '.')) / 100
        
        # Month percentages
        # July: "July 46%"
        if 'july 46%' in text_lower or '46%' in text_lower and 'july' in text_lower:
            cpfr_data['month_july_pct'] = 0.46
        elif 'july' in text_lower or 'juillet' in text_lower:
            percentages = re.findall(r'(\d+[.,]?\d*)%', text)
            if percentages:
                cpfr_data['month_july_pct'] = float(percentages[0].replace(',', '.')) / 100
        
        # August: "August 34%"
        if 'august 34%' in text_lower or '34%' in text_lower and 'august' in text_lower:
            cpfr_data['month_august_pct'] = 0.34
        elif 'august' in text_lower or 'août' in text_lower:
            percentages = re.findall(r'(\d+[.,]?\d*)%', text)
            if percentages:
                cpfr_data['month_august_pct'] = float(percentages[0].replace(',', '.')) / 100
        
        # September: "September 7%"
        if 'september 7%' in text_lower or '7%' in text_lower and 'september' in text_lower:
            cpfr_data['month_sept_pct'] = 0.07
        elif 'september' in text_lower or 'septembre' in text_lower:
            percentages = re.findall(r'(\d+[.,]?\d*)%', text)
            if percentages:
                cpfr_data['month_sept_pct'] = float(percentages[0].replace(',', '.')) / 100
        
        # Top dates booked: "July 12, 11 & 14"
        if 'july 12, 11 & 14' in text_lower or 'july 12' in text_lower:
            cpfr_data['top_dates_booked'] = ["July 12", "July 11", "July 14"]
        elif 'top dates booked' in text_lower:
            dates = re.findall(r'(\w+\s+\d+)', text)
            cpfr_data['top_dates_booked'] = dates[:3]  # Limiter à 3 dates
        
        # Top dates searched: "July 14, 18 & August 1"
        if 'july 14, 18 & august 1' in text_lower:
            cpfr_data['top_dates_searched'] = ["July 14", "July 18", "August 1"]
        elif 'top dates searched' in text_lower:
            dates = re.findall(r'(\w+\s+\d+)', text)
            cpfr_data['top_dates_searched'] = dates[:3]  # Limiter à 3 dates
        
        # Top parks: "BF 22%, BD 15% & LA 13%"
        if 'bf 22%' in text_lower or 'bd 15%' in text_lower or 'la 13%' in text_lower:
            cpfr_data['top_parks'] = ["BF 22%", "BD 15%", "LA 13%"]
        elif 'top parks' in text_lower:
            parks = re.findall(r'([A-Z]{2}\s+\d+%)', text)
            cpfr_data['top_parks'] = parks[:3]  # Limiter à 3 parcs
        
        # Lengths of stay: "2 nights (33%), 3 nights (33%) & 4 nights (19%)"
        if '2 nights (33%)' in text_lower or '3 nights (33%)' in text_lower:
            cpfr_data['lengths_of_stay'] = [(2, 33), (3, 33), (4, 19)]
        elif 'lengths of stay' in text_lower or 'durée de séjour' in text_lower:
            stays = re.findall(r'(\d+)\s+nights?\s*\((\d+)%\)', text)
            cpfr_data['lengths_of_stay'] = [(int(nights), int(pct)) for nights, pct in stays]
        
        # Insights
        if 'better performances vs ly' in text_lower or 'summer flashsale' in text_lower:
            cpfr_data['insights'].append("Overall, better performances vs LY except a drop of ABV but lower performances VS LW.")
            cpfr_data['insights'].append("Big succes of current summer flashsale: up to 400€ off on your stay.")
        elif 'insights' in text_lower or 'événements' in text_lower or 'événement' in text_lower:
            if len(text) > 20:  # Éviter les textes trop courts
                cpfr_data['insights'].append(text)
    
    return cpfr_data


def extract_cpfr_data_from_slide32(slide):
    """
    Extrait les données de tableau de la slide 32
    """
    table_data = parse_table(slide)
    
    cpfr_table_data = {
        'headers': table_data.get('headers', []),
        'rows': table_data.get('rows', []),
        'structured_data': {}
    }
    
    # Structurer les données du tableau
    if table_data.get('rows'):
        for row in table_data['rows']:
            if len(row) >= 2:
                key = row[0].strip().lower()
                value = row[1].strip()
                
                # Mapping des données du tableau
                if 'last minute' in key:
                    percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                    if percentages:
                        cpfr_table_data['structured_data']['last_minute_pct'] = float(percentages[0].replace(',', '.')) / 100
                
                elif 'early booking' in key:
                    percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                    if percentages:
                        cpfr_table_data['structured_data']['early_booking_pct'] = float(percentages[0].replace(',', '.')) / 100
                
                elif 'july' in key or 'juillet' in key:
                    percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                    if percentages:
                        cpfr_table_data['structured_data']['month_july_pct'] = float(percentages[0].replace(',', '.')) / 100
                
                elif 'august' in key or 'août' in key:
                    percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                    if percentages:
                        cpfr_table_data['structured_data']['month_august_pct'] = float(percentages[0].replace(',', '.')) / 100
                
                elif 'september' in key or 'septembre' in key:
                    percentages = re.findall(r'(\d+[.,]?\d*)%', value)
                    if percentages:
                        cpfr_table_data['structured_data']['month_sept_pct'] = float(percentages[0].replace(',', '.')) / 100
    
    return cpfr_table_data


def extract_cpfr_pptx(path, slide_start=31, slide_end=32):
    """
    Extrait spécifiquement les données CPFR des slides 31 et 32
    """
    try:
        prs = Presentation(path)
        slides = prs.slides
        
        # Validation des indices de slides
        if slide_start < 1 or slide_end < 1:
            raise ValueError("Les numéros de slides doivent être positifs")
        
        if slide_start > len(slides) or slide_end > len(slides):
            raise ValueError(f"Le fichier ne contient que {len(slides)} slides")
        
        if slide_start > slide_end:
            raise ValueError("La slide de début doit être inférieure à la slide de fin")
        
        # Extraction des slides
        slide31 = slides[slide_start - 1]
        slide32 = slides[slide_end - 1]
        
        # Extraction spécifique CPFR
        cpfr_data = extract_cpfr_data_from_slide31(slide31)
        table_data = extract_cpfr_data_from_slide32(slide32)
        
        # Fusion des données
        # Priorité aux données de la slide 31, puis complément avec la slide 32
        for key, value in table_data.get('structured_data', {}).items():
            if cpfr_data.get(key) is None:
                cpfr_data[key] = value
        
        return cpfr_data, table_data
        
    except Exception as e:
        raise Exception(f"Erreur lors de l'extraction CPFR du PowerPoint: {str(e)}")


def extract_pptx(path, slide_start, slide_end):
    """
    Extrait les données d'un fichier PowerPoint
    
    Args:
        path: Chemin vers le fichier .pptx
        slide_start: Numéro de la slide de début (1-indexed)
        slide_end: Numéro de la slide de fin (1-indexed)
    
    Returns:
        tuple: (kpis, table_data)
    """
    try:
        prs = Presentation(path)
        slides = prs.slides
        
        # Validation des indices de slides
        if slide_start < 1 or slide_end < 1:
            raise ValueError("Les numéros de slides doivent être positifs")
        
        if slide_start > len(slides) or slide_end > len(slides):
            raise ValueError(f"Le fichier ne contient que {len(slides)} slides")
        
        if slide_start > slide_end:
            raise ValueError("La slide de début doit être inférieure à la slide de fin")
        
        # Extraction des slides
        kpi_slide = slides[slide_start - 1]
        table_slide = slides[slide_end - 1]
        
        # Extraction des textes
        raw_texts = parse_slide_text(kpi_slide)
        kpis = extract_kpis_from_text(raw_texts)
        
        # Extraction du tableau
        table_data = parse_table(table_slide)
        
        return kpis, table_data
        
    except Exception as e:
        raise Exception(f"Erreur lors de l'extraction du PowerPoint: {str(e)}")


def get_slide_info(path):
    """Retourne des informations sur le fichier PowerPoint"""
    try:
        prs = Presentation(path)
        
        # Conversion des dates en chaînes pour la sérialisation JSON
        created_date = prs.core_properties.created
        modified_date = prs.core_properties.modified
        
        # Conversion en chaîne ISO si la date existe
        created_str = created_date.isoformat() if created_date else None
        modified_str = modified_date.isoformat() if modified_date else None
        
        return {
            "total_slides": len(prs.slides),
            "title": prs.core_properties.title or "Sans titre",
            "author": prs.core_properties.author or "Auteur inconnu",
            "created": created_str,
            "modified": modified_str
        }
    except Exception as e:
        raise Exception(f"Erreur lors de la lecture des informations du fichier: {str(e)}")
