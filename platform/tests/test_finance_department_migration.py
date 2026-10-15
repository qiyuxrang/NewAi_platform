"""Opt-in PostgreSQL migration checks in randomly named, disposable schemas.

Set FINANCE_MIGRATION_TEST_DATABASE_URL to an explicitly isolated
postgresql+asyncpg URL, then run unittest discover for this file.
No default platform URL is read and no database/server is created or removed.
"""

import importlib.util
import os
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, MetaData, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import User

path = Path(__file__).resolve().parents[1] / "alembic/versions/20261014_finance_department.py"
spec = importlib.util.spec_from_file_location("finance_department_migration", path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

TEST_URL = os.environ.get("FINANCE_MIGRATION_TEST_DATABASE_URL", "")


@unittest.skipUnless(TEST_URL, "Set FINANCE_MIGRATION_TEST_DATABASE_URL to an isolated PostgreSQL database")
class FinanceDepartmentMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if not TEST_URL.startswith("postgresql+asyncpg://"):
            self.fail("Migration test URL must use PostgreSQL with asyncpg")
        self.engine = create_async_engine(TEST_URL)
        self.schema = "codex_finance_test_" + uuid.uuid4().hex
        async with self.engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.users = User.__table__.to_metadata(MetaData())
        self.users.constraints.remove(next(c for c in self.users.constraints if c.name == migration.CONSTRAINT))
        self.users.append_constraint(CheckConstraint(migration.OLD_CHECK, name=migration.CONSTRAINT))

    async def asyncTearDown(self):
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        finally:
            await self.engine.dispose()

    async def run_in_schema(self, operation):
        async with self.engine.begin() as conn:
            await conn.execute(text(f'SET LOCAL search_path TO "{self.schema}"'))
            return await conn.run_sync(operation)

    @staticmethod
    def apply(conn, action):
        with Operations.context(MigrationContext.configure(conn)):
            action()

    async def test_upgrade_old_accounts_finance_and_safe_downgrade(self):
        def seed(conn):
            self.users.create(conn)
            for index, department in enumerate(("product", "hr", "engineering", None, None), 1):
                conn.execute(self.users.insert().values(id=str(index), username=f"old-{index}",
                    email=f"old-{index}@invalid.test", password_hash="preserved-password-hash",
                    business_role="general_manager" if index == 5 else "employee" if department else "unassigned",
                    department_code=department, portal_user_id=index, portal_session_enc="preserved-session"))
            return conn.execute(select(self.users).order_by(self.users.c.id)).all()

        original = await self.run_in_schema(seed)
        with self.assertRaises(IntegrityError):
            await self.run_in_schema(lambda conn: conn.execute(text("UPDATE users SET department_code = 'finance' WHERE id = '1'")))
        await self.run_in_schema(lambda conn: self.apply(conn, migration.upgrade))
        self.assertEqual(await self.run_in_schema(lambda conn: conn.execute(select(self.users).order_by(self.users.c.id)).all()), original)
        await self.run_in_schema(lambda conn: conn.execute(text("UPDATE users SET department_code = 'finance' WHERE id = '1'")))
        with self.assertRaisesRegex(RuntimeError, "existing finance assignments"):
            await self.run_in_schema(lambda conn: self.apply(conn, migration.downgrade))
        self.assertEqual(await self.run_in_schema(lambda conn: conn.execute(select(self.users.c.department_code).where(self.users.c.id == "1")).scalar_one()), "finance")
        with self.assertRaises(IntegrityError):
            await self.run_in_schema(lambda conn: conn.execute(text("UPDATE users SET department_code = 'unknown' WHERE id = '1'")))
        await self.run_in_schema(lambda conn: conn.execute(text("UPDATE users SET department_code = 'product' WHERE id = '1'")))
        await self.run_in_schema(lambda conn: self.apply(conn, migration.downgrade))
        self.assertEqual(await self.run_in_schema(lambda conn: conn.execute(select(self.users).order_by(self.users.c.id)).all()), original)
        with self.assertRaises(IntegrityError):
            await self.run_in_schema(lambda conn: conn.execute(text("UPDATE users SET department_code = 'finance' WHERE id = '1'")))
        checks = await self.run_in_schema(lambda conn: inspect(conn).get_check_constraints("users"))
        self.assertIn("ck_users_business_role", {check["name"] for check in checks})
        self.assertIn("ck_users_portal_user_id", {check["name"] for check in checks})

    async def test_missing_users_schema_fails_without_creating_tables(self):
        with self.assertRaisesRegex(RuntimeError, "existing users table"):
            await self.run_in_schema(lambda conn: self.apply(conn, migration.upgrade))
        self.assertEqual(await self.run_in_schema(lambda conn: inspect(conn).get_table_names()), [])
        await self.run_in_schema(lambda conn: conn.execute(text("CREATE TABLE users (id text PRIMARY KEY)")))
        with self.assertRaisesRegex(RuntimeError, "users.department_code"):
            await self.run_in_schema(lambda conn: self.apply(conn, migration.upgrade))

    async def test_missing_named_constraint_fails_without_changing_users(self):
        await self.run_in_schema(lambda conn: conn.execute(text("CREATE TABLE users (id text PRIMARY KEY, department_code text)")))
        with self.assertRaisesRegex(RuntimeError, "users.ck_users_department_code"):
            await self.run_in_schema(lambda conn: self.apply(conn, migration.upgrade))
        self.assertEqual(await self.run_in_schema(lambda conn: inspect(conn).get_check_constraints("users")), [])


if __name__ == "__main__":
    unittest.main()
