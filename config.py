import os
from dotenv import load_dotenv

# Use an absolute path so dotenv is found regardless of the process working directory
_dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=_dotenv_path)

LIFF_ID_ADMIN       = os.getenv('LIFF_ID_ADMIN', '')
LIFF_ID_REGISTER    = os.getenv('LIFF_ID_REGISTER', '')
ADMIN_SECRET        = os.getenv('ADMIN_SECRET', 'toyonaka-admin').strip()  # .strip() guards against accidental whitespace
BASE_URL            = os.getenv('BASE_URL', 'https://yourhost.com')
DATABASE_PATH       = os.getenv('DATABASE_PATH', 'badminton.db')
