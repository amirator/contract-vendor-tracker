import json

from conftest import ROOT

FLOW = ROOT / "power_automate" / "ContractRenewalReminders.flow.json"


def walk(actions, found):
    for name, a in actions.items():
        found[name] = a
        for key in ("actions",):
            if key in a:
                walk(a[key], found)
        if "else" in a:
            walk(a["else"]["actions"], found)
    return found


def test_flow_is_labelled_not_deployed():
    d = json.loads(FLOW.read_text())
    assert d["_readme"].startswith("DESIGN EXPORT - NOT DEPLOYED")


def test_flow_structure():
    d = json.loads(FLOW.read_text())["properties"]["definition"]
    assert d["$schema"].endswith("2016-06-01/workflowdefinition.json#")
    trig = d["triggers"]["Weekly_Sunday_0800"]
    assert trig["type"] == "Recurrence" and trig["recurrence"]["timeZone"] == "Arab Standard Time"
    assert d["parameters"]["DryRun"]["defaultValue"] is True


def test_run_after_references_exist_and_send_is_behind_dry_run():
    d = json.loads(FLOW.read_text())["properties"]["definition"]
    found = walk(d["actions"], {})
    for name, a in found.items():
        for dep in a.get("runAfter", {}):
            assert dep in found, f"{name} runs after missing action {dep}"
    cond = found["If_dry_run"]
    assert cond["expression"] == {"equals": ["@parameters('DryRun')", True]}
    assert "Send_an_email_V2" in cond["else"]["actions"] and "Send_an_email_V2" not in cond["actions"]


def test_flow_reads_columns_that_exist_in_the_workbook():
    from cvtrack.workbook import CONTRACT_COLS
    headers = {h for h, *_ in CONTRACT_COLS}
    text = FLOW.read_text()
    import re
    used = set(re.findall(r"item\(\)\?\['([^']+)'\]", text))
    assert used <= headers, used - headers
