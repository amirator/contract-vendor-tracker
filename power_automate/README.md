# Power Automate flow: weekly contract-renewal reminders

> **Design export, not deployed.** This file was written by hand in the workflow definition
> language that Power Automate cloud flows use, in the shape of a solution export
> (`Workflows/*.json`). It has **not** been imported into or run in Power Automate. Connection
> references and the file location are placeholders. Sample data only.

## What the flow does

```
Recurrence: every Sunday 08:00 (Arab Standard Time)
  -> Excel Online (Business): List rows present in a table  [tblContracts, filter Decision eq 'Pending']
  -> Filter array: Status <> Terminated and Days to expiry <= AlertWindowDays (90)
  -> Apply to each contract (one at a time)
       -> Compose the HTML body
       -> Condition DryRun = true (default)
            yes: Compose a log entry of what would be sent
            no:  Office 365 Outlook: Send an email (V2) to the owner;
                 Cc the escalation contact and High importance when RAG = Red
```

The column names it reads (`Contract`, `Title`, `Vendor`, `Owner`, `Owner email`, `Days to
expiry`, `Notice deadline`, `Notice flag`, `RAG`, `Status`) match the `tblContracts` table in the
workbook; `tests/test_power_automate.py` checks this.

## Differences from the Python version

- The flow sends one email per contract; Python groups them into one digest per owner.
- The flow covers contract renewals only. Invoice and audit reminders would be two more flows with the same pattern.
- Excel Online returns formula results as text, so the filter converts `Days to expiry` with `int()`.

## To try it (needs a Microsoft 365 work account; not done here)

1. Save `contract_vendor_tracker.xlsx` to a SharePoint document library or OneDrive for Business.
2. Build the flow in Power Automate following the steps above (or put this definition into a solution's `Workflows` folder and import the solution), then point the Excel action at your file.
3. Run it with `DryRun = true` and check the logged emails before setting it to `false`.

## Validation

- `tests/test_power_automate.py`: JSON parses, the trigger is a weekly Recurrence, `DryRun` defaults to `true`, the send action sits only on the `false` branch, every `runAfter` points to an existing action, and every column it reads exists in the workbook.
- `scripts/validate_flow_schema.py`: validates against Microsoft's Logic Apps workflow definition schema (2016-06-01). Result: 0 errors apart from Power Automate's own `OpenApiConnection` action type, which that schema does not list.
