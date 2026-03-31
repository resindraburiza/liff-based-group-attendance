import logging
import sys
from flask import Flask
from database import init_db
from routes.api import api_bp
from routes.liff import liff_bp

app = Flask(__name__)

app.register_blueprint(api_bp)
app.register_blueprint(liff_bp)
print('blueprints registered: ') 
print([str(r) for r in app.url_map.iter_rules()])

with app.app_context():
    init_db()
print('database initialised')

if __name__ == '__main__':
    app.run(debug=True)
