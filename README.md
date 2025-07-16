# powerpoint-to-dashboard

This project extracts KPI data and tables from PowerPoint files and displays them in a simple dashboard. It is structured as a Flask application that can be deployed to Vercel and includes unit tests.

## Project structure

```
flask-app-vercel
├── handlers       # HTTP request handlers
├── modules        # Core modules
├── static         # Static assets
│   ├── images
│   ├── scripts
│   └── styles
├── templates      # HTML templates
├── tests          # Unit tests
├── app.py         # Flask entry point
├── requirements.txt   # Python dependencies
└── flask.json     # Deployment configuration
```

`flask.json` tells Vercel to run `app.py` using the Python runtime and route all
requests to it.

Run the unit tests with `pytest`.
