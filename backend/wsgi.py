"""Gunicorn entry point: `gunicorn wsgi:app`."""
from app import create_app

app = create_app()
