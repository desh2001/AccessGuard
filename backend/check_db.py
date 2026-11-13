"""Small no-secrets DB connectivity diagnostic for local Windows setup."""
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from database import DATABASE_URL, engine

if __name__=='__main__':
    url=make_url(DATABASE_URL)
    print(f'Attempting DB at {url.host}:{url.port} / {url.database} as {url.username} (password hidden)')
    try:
        with engine.connect() as conn:
            print('SUCCESS: PostgreSQL (or configured test DB) returned',conn.execute(text('SELECT 1')).scalar())
    except OperationalError as exc:
        print('FAILED: database connection could not be established.')
        print('Troubleshoot: docker compose ps; expected port mapping 127.0.0.1:5434->5432/tcp.')
        print('Verify backend/.env matches the new compose user/database/password; do not share passwords.')
        raise SystemExit(1) from None
