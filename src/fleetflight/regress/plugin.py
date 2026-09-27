"""Optional plugin: pytest -p fleetflight.regress.plugin --fleetflight-sut v0.3.3."""
import os


def pytest_addoption(parser):
    parser.addoption("--fleetflight-sut", default=None, help="SUT for generated regressions")


def pytest_configure(config):
    config.addinivalue_line("markers", "fleetflight: generated FleetFlight regression")
    config._fleetflight_previous_sut = os.environ.get("FLEETFLIGHT_SUT")
    selected = config.getoption("--fleetflight-sut")
    if selected:
        os.environ["FLEETFLIGHT_SUT"] = selected


def pytest_unconfigure(config):
    previous = getattr(config, "_fleetflight_previous_sut", None)
    if previous is None:
        os.environ.pop("FLEETFLIGHT_SUT", None)
    else:
        os.environ["FLEETFLIGHT_SUT"] = previous
