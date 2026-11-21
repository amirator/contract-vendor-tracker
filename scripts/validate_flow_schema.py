"""Validate the Power Automate flow definition against Microsoft's published Logic Apps schema.

Downloads https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json
(needs internet and `pip install jsonschema`). Power Automate adds its own action type
`OpenApiConnection`, which that schema does not list, so errors about that type are reported
separately rather than as failures.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import jsonschema

URL = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json"
FLOW = Path(__file__).resolve().parent.parent / "power_automate" / "ContractRenewalReminders.flow.json"


def main() -> int:
    schema = json.load(urllib.request.urlopen(URL, timeout=30))
    definition = json.loads(FLOW.read_text())["properties"]["definition"]
    errors = list(jsonschema.Draft4Validator(schema).iter_errors(definition))
    pa_only = [e for e in errors if "OpenApiConnection" in json.dumps(e.instance, default=str)]
    other = [e for e in errors if e not in pa_only]
    for e in other:
        print("ERROR", list(e.path), e.message[:200])
    print(f"{len(other)} schema error(s); {len(pa_only)} only about Power Automate's OpenApiConnection action type")
    return 1 if other else 0


if __name__ == "__main__":
    sys.exit(main())
