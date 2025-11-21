# FFC-Cloudflare-Automation-

Automation utilities for Cloudflare tasks supporting Free For Charity.

## One-Time DNS Update Tool

Script: `update_dns.py` updates or creates the `A` record for `staging.clarkemoyer.com`.

### Requirements

- Python 3.9+ (tested locally)
- Install dependencies:

```powershell
python -m venv .venv; .\.venv\Scripts\activate; pip install -r requirements.txt
```

### Usage

Provide a new IPv4 address for the staging subdomain. Supply the Cloudflare API token either via environment variable, command-line argument, or interactive prompt.

```powershell
# Option 1: Prompt for token
python update_dns.py --ip 203.0.113.42

# Option 2: Environment variable
$env:CLOUDFLARE_API_TOKEN = "cf_api_token_value"
python update_dns.py --ip 203.0.113.42

# Option 3: Explicit argument
python update_dns.py --ip 203.0.113.42 --token cf_api_token_value

# Enable Cloudflare proxy (orange cloud)
python update_dns.py --ip 203.0.113.42 --proxied

# Dry run (no changes, shows intended payload)
python update_dns.py --ip 203.0.113.42 --dry-run --proxied
```

### Behavior

Behavior (Python & PowerShell scripts):

- Finds zone ID for `clarkemoyer.com`.
- Fetches all existing `A` records for `staging.clarkemoyer.com` (supports multiple records).
	- Each record with differing IP or differing proxied status is updated.
	- Records already matching requested IP and proxied state are left unchanged.
	- If no records exist, one is created.
- TTL fixed at 120 seconds.
- Add `--proxied` (Python) or `-Proxied` (PowerShell) to turn on Cloudflare proxy (orange cloud).

### PowerShell Variant

Script: `Update-StagingDns.ps1` mirrors Python functionality (multi-record, dry-run, proxy flag).

```powershell
# Prompt for token
./Update-StagingDns.ps1 -NewIp 203.0.113.42

# With environment token & proxy
$env:CLOUDFLARE_API_TOKEN = "cf_api_token_value"
./Update-StagingDns.ps1 -NewIp 203.0.113.42 -Proxied

# Dry run
./Update-StagingDns.ps1 -NewIp 203.0.113.42 -DryRun -Proxied
```

### Token Scope Recommendation

Use a Cloudflare API Token with the minimal permissions (e.g. DNS:Edit for the target zone) rather than the global key.

### Safety

The token is never logged. Dry-run mode allows inspection before changes. All matching A records for the FQDN are processed.

