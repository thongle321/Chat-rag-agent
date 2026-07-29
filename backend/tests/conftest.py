import logfire
import pytest

logfire.configure(
    send_to_logfire='if-token-present',
    service_name='rag-evals',
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
