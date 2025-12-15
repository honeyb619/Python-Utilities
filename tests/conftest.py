from typing import Iterator
from pathlib import Path
from pytest import fixture


@fixture()
def client() -> Iterator:
    # Import the webapp package (more reliable than top-level app module)
    try:
        import webapp  # type: ignore
    except ModuleNotFoundError:
        import sys

        repo_root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(repo_root))
        import webapp  # type: ignore

    flask_app = getattr(webapp, "app")
    flask_app.testing = True
    with flask_app.test_client() as c:
        yield c
