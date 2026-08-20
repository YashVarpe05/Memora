async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Memora API"


async def test_openapi_schema_is_generated(client):
    """packages/core types are generated from this schema, so it must stay valid."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
