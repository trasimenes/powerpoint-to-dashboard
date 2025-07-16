# powerpoint-to-dashboard

This project extracts KPI data and tables from PowerPoint files and displays them in a simple dashboard. It is structured as a Flask application that can be deployed to Vercel and includes unit tests.

## Project structure

```
flask-app-vercel
├── api                # Application code served by Vercel
│   ├── handlers       # HTTP request handlers
│   ├── modules        # Core modules
│   ├── static         # Static assets
│   ├── templates      # HTML templates
│   └── hello.py       # Flask entry point
├── tests              # Unit tests
├── requirements.txt   # Python dependencies
└── vercel.json        # Vercel configuration
```

The code lives inside the `api/` directory so that Vercel exposes the Flask app
as a serverless function. `vercel.json` configures the Python runtime and routes
all requests to `api/hello.py`.

Run the unit tests with `pytest`.
