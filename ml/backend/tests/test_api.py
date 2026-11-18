from fastapi.testclient import TestClient


def test_health_is_alive_without_model_artifacts(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "load_model_registry", lambda: ({}, {"windows": "model_not_trained", "linux": "model_not_trained", "github": "model_not_trained"}))
    with TestClient(main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["models_loaded"] == 0


def test_score_endpoint_requires_shared_service_token(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "load_model_registry", lambda: ({}, {}))
    monkeypatch.setenv("ML_SERVICE_TOKEN", "A" * 40)
    with TestClient(main.app) as client:
        body = {"cycle_id": "cycle-1", "window_days": 90, "records": [
            {"account_id": "a-1", "platform": "GitLab", "features": {}}
        ]}
        no_auth = client.post("/v1/score/accounts", json=body)
        assert no_auth.status_code == 401
        auth = client.post("/v1/score/accounts", json=body, headers={"Authorization": f"Bearer {'A' * 40}"})
        assert auth.status_code == 200
        result = auth.json()["results"][0]
        assert result["status"] == "unscored"
        assert result["reason"] == "unsupported_platform:no_cross_platform_fallback"

        duplicate_body = {"cycle_id": "cycle-1", "window_days": 90, "records": [
            {"account_id": "same", "platform": "GitHub", "features": {}},
            {"account_id": "same", "platform": "Linux", "features": {}},
        ]}
        duplicate = client.post("/v1/score/accounts", headers={"Authorization": f"Bearer {'A' * 40}"}, json=duplicate_body)
        assert duplicate.status_code == 422
