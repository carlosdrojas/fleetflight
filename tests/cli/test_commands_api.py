import http.client
import json
import threading
import pytest

from fleetflight import cli, models
from tests.cli.toy_model import ToyModel, make_cex
from tests.test_contract import load, validator


@pytest.fixture
def toy_loader(monkeypatch):
    def loader(name="toy", sut=None, bounds=None):
        return ToyModel(sut, bounds)

    monkeypatch.setattr(cli, "load_model", loader)
    monkeypatch.setattr(models, "load_model", loader, raising=False)


@pytest.fixture
def artifacts(tmp_path):
    cex = make_cex()
    cli.write_json(tmp_path / f"{cex['id']}.json", cex)
    report = load("check-report.json")
    cli.write_json(tmp_path / f"check-{report['run_id']}.json", report)
    return tmp_path, cex, report


def test_describe_json(toy_loader, capsys):
    assert cli.main(["describe", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    validator("describe.schema.json").validate(doc)


def test_exit_codes_and_replay_json(toy_loader, artifacts, capsys):
    root, cex, report = artifacts
    common = ["--counterexample", cex["id"], "--out", str(root)]
    destination = root / "replay.json"
    assert cli.main(["replay", *common, "--repeat", "100", "--json", str(destination)]) == 1
    output = capsys.readouterr().out
    assert "100 sha256:" in output
    validator("replay-result.schema.json").validate(json.loads(destination.read_text()))
    assert cli.main(["replay", *common, "--sut", "vfixed"]) == 0
    assert cli.main(["replay", *common, "--repeat", "0"]) == 2
    assert cli.main(["replay", *common, "--horizon-ms", "25"]) == 2
    assert cli.main(["replay", *common, "--sut", "unknown"]) == 2
    assert cli.main(["explain", cex["id"], "--out", str(root)]) == 1
    assert cli.main(["explain", str(root / "missing.json")]) == 2
    assert cli.main(["describe", "--nonsense"]) == 2
    assert cli.main([]) == 2
    assert cli.main(["--help"]) == 0
    empty = dict(cex, trace=[])
    cli.write_json(root / "empty.json", empty)
    assert cli.main(["explain", str(root / "empty.json")]) == 2


def test_missing_model_has_clear_error(monkeypatch, capsys):
    def missing(module):
        raise ImportError("missing stream")

    monkeypatch.setattr(cli.importlib, "import_module", missing)
    assert cli.main(["describe"]) == 2
    assert "integrate the model/checker stream" in capsys.readouterr().err


def test_sim_scenario_and_regress_commands(toy_loader, artifacts, tmp_path, monkeypatch):
    root, cex, report = artifacts
    assert cli.main(["sim", "--seed", "1", "--scenario", "bms-fault-basic", "--sut", "vfixed", "--horizon-ms", "200"]) == 0
    assert cli.main(["sim", "--seed", "1", "--scenario", "bms-fault-basic", "--sut", "vbug", "--horizon-ms", "200"]) == 1
    generated = root / "generated"
    assert cli.main(["regress", "--from", cex["id"], "--out", str(root), "--out-dir", str(generated)]) == 0
    monkeypatch.setenv("FLEETFLIGHT_SUT", "vbug")
    assert cli.main(["regress", "--all", "--out", str(root), "--out-dir", str(generated), "--junit", str(root / "regress.xml")]) == 1
    monkeypatch.setenv("FLEETFLIGHT_SUT", "vfixed")
    assert cli.main(["regress", "--all", "--out", str(root), "--out-dir", str(generated)]) == 0
    assert cli.main(["regress", "--all", "--out", str(root / "empty")]) == 2
    assert cli.main(["report", str(root / f"check-{report['run_id']}.json"), "--markdown"]) == 1


@pytest.fixture
def server(toy_loader, artifacts, tmp_path):
    root, cex, report = artifacts
    ui = root / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<h1>Toy UI</h1>")
    server = cli.create_server(root, port=0, ui_dir=ui)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, cex, report, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(server, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_all_success_api_documents_validate_and_post_is_read_only(server):
    server, cex, report, root = server
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert server.server_address[0] == "127.0.0.1"
    endpoints = {
        "/api/describe": "describe.schema.json", "/api/runs": "run-list.schema.json",
        f"/api/runs/{report['run_id']}": "check-report.schema.json",
        f"/api/cex/{cex['id']}": "counterexample.schema.json",
    }
    for path, schema in endpoints.items():
        status, payload = request(server, "GET", path)
        assert status == 200
        validator(schema).validate(json.loads(payload))
    for version in ("vbug", "vfixed"):
        status, payload = request(server, "POST", "/api/replay", json.dumps({"cex": cex["id"], "sut": version}))
        assert status == 200
        result = json.loads(payload)
        validator("replay-result.schema.json").validate(result)
        assert result["verdict"] == ("FAIL" if version == "vbug" else "PASS")
    after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert before == after
    assert request(server, "GET", "/")[1] == b"<h1>Toy UI</h1>"


def test_api_rejects_bad_input_and_traversal(server):
    server, cex, report, root = server
    for path in ("/api/cex/../../secret", "/%2e%2e/secret", "/api/runs/%2e%2e%2fsecret"):
        assert request(server, "GET", path)[0] == 400
    assert request(server, "GET", "/api/unknown")[0] == 404
    assert request(server, "GET", "/api/cex/cex-0000")[0] == 404
    for body in ("broken", "[]", '{"cex": 7}', '{"cex":"../../secret"}', '{"cex":"a", "sut":4}'):
        assert request(server, "POST", "/api/replay", body)[0] == 400
    assert request(server, "POST", "/api/replay", "{}", {"Origin": "http://elsewhere.invalid"})[0] == 403
    assert request(server, "POST", "/api/unknown", "{}")[0] == 404
    (root / "ui" / "escape").symlink_to(root / f"{cex['id']}.json")
    assert request(server, "GET", "/escape")[0] == 400


def test_run_list_sorting_and_mock_badge(artifacts):
    root, cex, report = artifacts
    newer = dict(report, run_id="newer", created_at="2099-01-01T00:00:00Z")
    cli.write_json(root / "check-newer.json", newer)
    document = cli.run_list(root)
    validator("run-list.schema.json").validate(document)
    assert document["runs"][0]["run_id"] == "newer"
    assert document["_fixture"] is True
