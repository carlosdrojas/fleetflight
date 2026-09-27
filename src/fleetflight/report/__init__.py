"""Markdown summaries and JUnit XML; no terminal dependencies."""
from __future__ import annotations

import json
from xml.etree.ElementTree import Element, SubElement, tostring


def _document(report):
    return report.to_json() if hasattr(report, "to_json") else report


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def to_markdown(check_report) -> str:
    report = _document(check_report)
    stats = report["stats"]
    lines = [f"## FleetFlight: {report['verdict']}", ""]
    if report.get("_fixture"):
        lines += ["**MOCK DATA — fixture values, not verification results.**", ""]
    lines += [f"Model: `{report['model']['name']}` · SUT: `{report['sut']['id']}`", "",
              f"{stats['states']:,} states · {stats['transitions']:,} transitions · "
              f"{stats['wall_s']:.3f} s · complete: {stats['complete']}", "",
              f"Bounds: `{json.dumps(report['bounds'], sort_keys=True)}`", "",
              "| Invariant | Result | Counterexample |", "| --- | --- | --- |"]
    for item in report["invariants"]:
        lines.append(f"| {_cell(item['id'] + ' ' + item['name'])} | {item['result']} | "
                     f"{_cell(item.get('counterexample') or '—')} |")
    lines += ["", "### Assumptions", ""]
    lines += [f"- {assumption}" for assumption in report["assumptions"]]
    lines += ["", "PASS applies only within the recorded model and bounds."]
    return "\n".join(lines) + "\n"


def to_junit(results) -> str:
    documents = [_document(results)] if isinstance(results, dict) or hasattr(results, "to_json") else [_document(item) for item in results]
    suites = Element("testsuites")
    total = failures = 0
    for report in documents:
        items = report["invariants"]
        failed = sum(item["result"] == "FAIL" for item in items)
        name = report.get("counterexample", report.get("run_id", "fleetflight"))
        suite = SubElement(suites, "testsuite", name=name, tests=str(len(items)), failures=str(failed), errors="0")
        if report.get("_fixture"):
            SubElement(suite, "system-out").text = "MOCK DATA: fixture values"
        for item in items:
            case = SubElement(suite, "testcase", classname=report["sut"]["id"], name=f"{item['id']} {item['name']}")
            if item["result"] == "FAIL":
                SubElement(case, "failure", message=f"{item['id']} violated").text = json.dumps(item, sort_keys=True)
        total += len(items)
        failures += failed
    suites.set("tests", str(total))
    suites.set("failures", str(failures))
    suites.set("errors", "0")
    return tostring(suites, encoding="unicode", xml_declaration=True) + "\n"
