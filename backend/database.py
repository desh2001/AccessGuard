"""PostgreSQL connection; no embedded credentials in source code."""
from pathlib import Path
from os import getenv
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).resolve().parent / '.env')
DATABASE_URL = getenv('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL missing. Copy backend/.env.example to backend/.env and configure PostgreSQL.')
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
