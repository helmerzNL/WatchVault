"""Run database migrations (called on container boot before serving)."""
from app.migrations_runner import run_migrations

if __name__ == "__main__":
    run_migrations()
