
from main import _load_env
_load_env()
from src.infrastructure.postgres.auth_db import verify_password, get_user_by_username
user = get_user_by_username('admin')
print(user)
print(verify_password('admin123', user['password_hash']))

