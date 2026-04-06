# Healthcare Compliance Violation Scraper

A sales prospecting tool that pulls publicly available federal violation data and filters it to surface healthcare facilities with recent citations for bloodborne pathogens, sharps disposal, or hazardous waste handling.

## What This Does

Federal agencies publish inspection and violation records as open data. This project downloads those records, filters for the violations most relevant to compliance-focused sales (e.g., sharps disposal vendors, waste management services), and outputs a prioritized CSV you can import into a CRM.

## Data Sources

### OSHA Enforcement Data
OSHA publishes its full enforcement history as bulk data downloads at:
**https://enforcedata.dol.gov/views/data_summary.php**

The relevant tables are:
- **osha_inspection** — one row per inspection (facility name, address, NAICS code, inspection date, etc.)
- **osha_violation** — one row per citation issued during an inspection (violation standard, penalty, gravity)

These are linked by a shared `activity_nr` (inspection number) field.

Key fields you'll use:
| Field | What it means |
|---|---|
| `estab_name` | Employer / facility name |
| `site_address`, `site_city`, `site_state` | Location |
| `naics_code` | Industry code — filter to healthcare (62xxxx range) |
| `open_date` | Date inspection was opened |
| `issuance_dt` | Date citation was issued |
| `standard` | The CFR regulation violated (e.g., `1910.1030` = bloodborne pathogens) |
| `penalty` | Proposed penalty in dollars |

### CMS Data (future phase)
CMS publishes hospital and nursing home inspection data via the Care Compare datasets at data.cms.gov. These can be joined with OSHA data by facility name/address.

## Violation Standards to Target

| CFR Standard | Description |
|---|---|
| `1910.1030` | Bloodborne pathogens |
| `1910.1200` | Hazard communication (chemicals/hazardous waste) |
| `1910.132` | Personal protective equipment |
| `1910.141` | Sanitation / sharps disposal containers |

## Output

A CSV file with one row per cited facility, sorted by recency and penalty severity, ready to import into a CRM.

## Setup

```bash
pip install -r requirements.txt
```

## Project Structure

```
compliance-scraper/
├── requirements.txt   # Python dependencies
├── README.md          # This file
└── scraper.py         # Main script (coming next)
```
