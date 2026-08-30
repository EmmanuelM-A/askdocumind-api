import pytest


@pytest.fixture(autouse=True)
def reset_service_singletons():
    """Prevent DocumentConverter/DocumentProcessor state from leaking
    between tests, since get_upload_service() caches a module-level
    singleton for the life of the process."""
    import src.api.services.service_factory as factory

    yield
    factory._upload_service = None
