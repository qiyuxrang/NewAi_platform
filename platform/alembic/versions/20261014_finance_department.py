"""Allow finance assignments on an existing platform users table.

This incremental migration does not bootstrap a database. Run online against
PostgreSQL after separately approving the target database migration.
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "20261014_finance_department"
down_revision = None
branch_labels = None
depends_on = None

CONSTRAINT = "ck_users_department_code"
OLD_CHECK = "department_code IS NULL OR department_code IN ('product', 'hr', 'engineering')"
NEW_CHECK = "department_code IS NULL OR department_code IN ('product', 'hr', 'engineering', 'finance')"


def _existing_users():
    if op.get_context().as_sql:
        raise RuntimeError("Finance department migration requires an online PostgreSQL schema check")
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Finance department migration requires PostgreSQL")
    schema = inspect(bind)
    if not schema.has_table("users"):
        raise RuntimeError("Finance department migration requires an existing users table")
    if "department_code" not in {column["name"] for column in schema.get_columns("users")}:
        raise RuntimeError("Finance department migration requires users.department_code")
    if CONSTRAINT not in {constraint["name"] for constraint in schema.get_check_constraints("users")}:
        raise RuntimeError("Finance department migration requires users.ck_users_department_code")
    # Serialize the assignment check and constraint change in the same transaction.
    bind.execute(text("LOCK TABLE users IN ACCESS EXCLUSIVE MODE"))
    return bind


def upgrade():
    _existing_users()
    op.drop_constraint(CONSTRAINT, "users", type_="check")
    op.create_check_constraint(CONSTRAINT, "users", NEW_CHECK)


def downgrade():
    bind = _existing_users()
    if bind.execute(text("SELECT 1 FROM users WHERE department_code = 'finance' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade finance department: existing finance assignments must be reassigned explicitly first")
    op.drop_constraint(CONSTRAINT, "users", type_="check")
    op.create_check_constraint(CONSTRAINT, "users", OLD_CHECK)
