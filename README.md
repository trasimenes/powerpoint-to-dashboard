# powerpoint-to-dashboard

This project extracts KPI data and tables from PowerPoint files and displays them in a simple dashboard. It is structured as a Flask application that can be deployed to Vercel and includes unit tests.

## Project structure

```
flask-app-vercel
├── .github            # GitHub workflows
├── handlers           # HTTP request handlers
├── modules            # Core application modules
├── static             # Static assets
│   ├── images
│   ├── scripts
│   └── styles
├── templates          # HTML templates
├── tests              # Unit tests
├── app.py             # Application entry point
├── requirements.txt   # Python dependencies
└── vercel.json        # Vercel configuration
```

The `vercel.json` file configures the Python runtime and also serves files from
the `static/` directory using `@vercel/static`.

Run the unit tests with `pytest`.
