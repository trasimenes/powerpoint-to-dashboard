from flask import Flask

from modules.database import init_db
from handlers.routes import routes

app = Flask(__name__)
app.secret_key = "secret-key"  # In production, use env variable

app.register_blueprint(routes)

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
