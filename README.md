# PowerPoint Dashboard

Une application web Flask élégante pour extraire et visualiser les données de fichiers PowerPoint (.pptx). L'application permet d'extraire automatiquement les KPIs et tableaux d'analyse des slides spécifiées et de les présenter dans un dashboard moderne.

## 🚀 Fonctionnalités

- **Upload de fichiers PowerPoint** : Interface moderne pour uploader des fichiers .pptx
- **Extraction intelligente** : Extraction automatique des KPIs et tableaux des slides 31-32 (configurable)
- **Dashboard élégant** : Présentation moderne des données extraites avec Bootstrap
- **Historique complet** : Sauvegarde et consultation de toutes les extractions
- **Base de données SQLite** : Stockage persistant des données extraites
- **Interface responsive** : Design adaptatif pour tous les appareils
- **Validation robuste** : Gestion d'erreurs et validation des données

## 📋 Prérequis

- Python 3.7+
- pip (gestionnaire de paquets Python)

## 🛠️ Installation

1. **Cloner le repository**
   ```bash
   git clone <url-du-repo>
   cd powerpoint-to-dashboard
   ```

2. **Créer un environnement virtuel (recommandé)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Sur Windows : venv\Scripts\activate
   ```

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Démarrage

1. **Lancer l'application**
   ```bash
   python app.py
   ```

2. **Accéder à l'application**
   Ouvrez votre navigateur et allez sur `http://localhost:5000`

## 📖 Utilisation

### 1. Upload d'un fichier PowerPoint
- Cliquez sur "Choisir un fichier" et sélectionnez votre fichier .pptx
- Par défaut, les slides 31 et 32 sont sélectionnées
- Vous pouvez modifier la plage de slides selon vos besoins
- Cliquez sur "Analyser le PowerPoint"

### 2. Visualisation des résultats
- **Slide KPI** : Affichage des KPIs et textes extraits de la première slide
- **Slide Tableau** : Affichage du tableau d'analyse de la seconde slide
- **Informations du fichier** : Métadonnées du PowerPoint (titre, auteur, etc.)
- **Statistiques** : Résumé de l'extraction

### 3. Historique
- Accédez à l'onglet "Historique" pour voir toutes les extractions
- Cliquez sur "Voir" pour consulter une extraction spécifique
- Statistiques globales de l'application

## 🏗️ Architecture

```
powerpoint-to-dashboard/
├── app.py                 # Point d'entrée de l'application
├── requirements.txt       # Dépendances Python
├── modules/
│   ├── database.py       # Gestion de la base de données SQLite
│   └── pptx_utils.py     # Extraction des données PowerPoint
├── handlers/
│   └── routes.py         # Routes Flask et logique métier
├── templates/
│   ├── base.html         # Template de base
│   ├── upload.html       # Page d'upload
│   ├── dashboard.html    # Dashboard des résultats
│   ├── history.html      # Page d'historique
│   └── 404.html          # Page d'erreur 404
└── static/               # Fichiers statiques (CSS, JS, images)
```

## 🔧 Configuration

### Variables d'environnement
- `FLASK_SECRET_KEY` : Clé secrète pour Flask (optionnel, une clé par défaut est fournie)

### Base de données
- La base de données SQLite est créée automatiquement dans `database.db`
- Structure de la table `extractions` :
  - `id` : Identifiant unique
  - `timestamp` : Date et heure de l'extraction
  - `filename` : Nom du fichier PowerPoint
  - `slide_start` : Numéro de la slide de début
  - `slide_end` : Numéro de la slide de fin
  - `kpi` : Données KPIs extraites (JSON)
  - `table_data` : Données du tableau (JSON)
  - `file_info` : Métadonnées du fichier (JSON)
  - `extraction_status` : Statut de l'extraction

## 📊 Extraction des données

### Slide KPI (par défaut : slide 31)
- Extraction de tous les textes et KPIs
- Détection automatique des indicateurs de performance
- Nettoyage et normalisation des données

### Slide Tableau (par défaut : slide 32)
- Extraction des en-têtes de colonnes
- Extraction des données de lignes
- Gestion des cellules vides
- Structure JSON pour faciliter l'utilisation

## 🎨 Interface utilisateur

- **Design moderne** : Interface Bootstrap 5 avec icônes
- **Responsive** : Adaptation automatique aux différentes tailles d'écran
- **Couleurs sobres** : Palette de couleurs professionnelle
- **Navigation intuitive** : Menu de navigation clair
- **Feedback utilisateur** : Messages d'information et d'erreur

## 🔒 Sécurité

- Validation des types de fichiers (.pptx uniquement)
- Limitation de la taille des fichiers (50MB max)
- Nettoyage des noms de fichiers
- Gestion sécurisée des fichiers temporaires

## 🧪 Tests

Pour exécuter les tests :
```bash
python -m pytest tests/
```

## 📝 API

L'application expose également des endpoints API :

- `GET /api/stats` : Statistiques de l'application
- `GET /api/history?limit=50` : Historique des extractions

## 🚀 Déploiement

### Déploiement local
L'application est prête pour un déploiement local avec Flask.

### Déploiement en production
Pour un déploiement en production, utilisez un serveur WSGI comme Gunicorn :

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 🤝 Contribution

1. Fork le projet
2. Créez une branche pour votre fonctionnalité (`git checkout -b feature/AmazingFeature`)
3. Committez vos changements (`git commit -m 'Add some AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrez une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 🆘 Support

Pour toute question ou problème :
1. Consultez la documentation
2. Vérifiez les issues existantes
3. Créez une nouvelle issue avec les détails du problème

## 🔄 Versions

- **v1.0.0** : Version initiale avec extraction de base
- **v1.1.0** : Amélioration de l'interface et ajout des statistiques
- **v1.2.0** : API REST et gestion d'erreurs améliorée

