"""Competition ingestion adapter: CSV exports or safe read-only MySQL table queries.

Never execute SQL dump text. Restore an authorized dump in an isolated database
and query its tables using a read-only account. No direct production access.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import os
import re
from pathlib import Path
from sqlalchemy import MetaData, Table, create_engine, select
from app.db import SessionLocal, Base, engine
from app.importers import REQUIRED, import_csv

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


def push_rows(kind, rows, batch_size=500):
    if kind not in REQUIRED:
        raise ValueError(f"Unsupported dataset: {kind}")
    if not 1 <= batch_size <= 2000:
        raise ValueError("batch_size must be 1..2000")
    batch, imported = [], 0
    def commit(records):
        fields = sorted(set().union(*(r.keys() for r in records)))
        if not REQUIRED[kind].issubset(fields):
            raise ValueError(f"Missing required fields: {sorted(REQUIRED[kind]-set(fields))}")
        data = io.StringIO()
        writer = csv.DictWriter(data, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
        # Normalizes and validates via existing application importer; no bypass.
        with SessionLocal() as db:
            return import_csv(db, kind, data.getvalue().encode('utf-8'))
    for row in rows:
        batch.append({str(k): '' if v is None else str(v) for k, v in row.items() if k is not None})
        if len(batch) == batch_size:
            imported += commit(batch)
            batch = []
    if batch:
        imported += commit(batch)
    return imported


def rows_csv(path: Path, column_map: dict[str, str]):
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            yield {column_map.get(k, k): v for k, v in row.items()}


def rows_mysql(url: str, table_name: str, column_map: dict[str, str]):
    if not IDENTIFIER.fullmatch(table_name):
        raise ValueError('MySQL table must be a simple identifier (no SQL expressions)')
    if not url.startswith('mysql+pymysql://'):
        raise ValueError('Source must be a MySQL read-only SQLAlchemy URL using pymysql')
    engine = create_engine(url, pool_pre_ping=True)
    try:
        metadata = MetaData()
        source = Table(table_name, metadata, autoload_with=engine)
        with engine.connect().execution_options(stream_results=True) as connection:
            for row in connection.execute(select(source)).mappings().yield_per(500):
                yield {column_map.get(k, k): v for k, v in row.items()}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description='Import authorized application/AD CSV exports or read-only MySQL tables')
    parser.add_argument('--kind', required=True, choices=sorted(REQUIRED))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--csv', type=Path)
    group.add_argument('--mysql-table')
    map_options = parser.add_mutually_exclusive_group()
    map_options.add_argument('--column-map', default=None, help='JSON {"source_column":"aegis_column"}')
    map_options.add_argument('--column-map-file', type=Path, help='JSON column mapping file for this connector')
    parser.add_argument('--batch-size', type=int, default=500)
    args = parser.parse_args()
    mapping = json.loads(args.column_map or (args.column_map_file.read_text(encoding='utf-8') if args.column_map_file else '{}'))
    if not isinstance(mapping, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in mapping.items()):
        parser.error('column-map must be a JSON object of strings')
    if args.csv:
        stream = rows_csv(args.csv, mapping)
    else:
        url = os.getenv('AEGIS_SOURCE_MYSQL_URL')
        if not url:
            parser.error('Set AEGIS_SOURCE_MYSQL_URL with read-only MySQL credentials')
        stream = rows_mysql(url, args.mysql_table, mapping)
    # Prototype convenience: creates missing tables, does NOT migrate changed existing schemas.
    Base.metadata.create_all(engine)
    number = push_rows(args.kind, stream, args.batch_size)
    print(f'Imported {number} {args.kind} rows. Source credentials and account data intentionally omitted.')

if __name__ == '__main__':
    main()
