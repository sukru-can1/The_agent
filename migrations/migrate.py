"""Simple asyncpg migration runner."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATIONS_DIR = Path(__file__).parent


async def run_migrations(dsn: str) -> None:
    """Run all pending SQL migrations in order."""
    conn = await asyncpg.connect(dsn)

    try:
        # Ensure migrations tracking table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id       SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Get already-applied migrations
        applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM _migrations")
        }

        # Find and sort SQL files
        sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        for sql_file in sql_files:
            if sql_file.name in applied:
                print(f"  [skip] {sql_file.name}")
                continue

            print(f"  [apply] {sql_file.name}")
            sql = sql_file.read_text(encoding="utf-8")

            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO _migrations (filename) VALUES ($1)",
                        sql_file.name,
                    )
            except Exception as exc:
                print(f"  [WARN] {sql_file.name} failed: {exc}")
                print(f"  Skipping — can be retried later.")

        print("Migrations complete.")
    finally:
        await conn.close()


def main() -> None:
    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://agent1:agent1@localhost:5432/agent1",
    )
    print(f"Running migrations against: {dsn[:30]}...")
    asyncio.run(run_migrations(dsn))


if __name__ == "__main__":
    main()
