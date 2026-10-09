"""LAN and UDA prefix compatibility without changing schema data."""
from app import app

def test_prefix_pages():
    app.config["TESTING"] = True
    client = app.test_client()
    headers = {"X-Forwarded-Prefix":"/apps/querybridge",
               "X-Forwarded-Host":"tanyaanne.ddns.net",
               "X-Forwarded-Proto":"https"}
    for path in ("/", "/builder", "/knowledge", "/chat", "/ai-skills", "/llm"):
        proxied = client.get(path, headers=headers)
        assert proxied.status_code == 200, (path, proxied.status_code)
        html = proxied.get_data(as_text=True)
        assert '<base href="/apps/querybridge/">' in html
        assert '/apps/querybridge/static/uda-path.js' in html
    local = client.get("/")
    assert local.status_code == 200
    assert '<base href="/">' in local.get_data(as_text=True)
