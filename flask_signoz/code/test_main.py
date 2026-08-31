from main import app


def test_root_endpoint_returns_200():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Flask + Signoz" in response.data
