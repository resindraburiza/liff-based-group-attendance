import logging
import sys
from flask import Flask
from database import init_db
from routes.api import api_bp
from routes.liff import liff_bp

logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
_log = logging.getLogger('toyonaka.app')

app = Flask(__name__)

app.register_blueprint(api_bp)
app.register_blueprint(liff_bp)
_log.debug('blueprints registered: %s', [str(r) for r in app.url_map.iter_rules()])

with app.app_context():
    init_db()
_log.debug('database initialised')

if __name__ == '__main__':
    app.run(debug=True)
