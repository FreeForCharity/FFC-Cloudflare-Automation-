# FFC-Cloudflare-Automation

Automation utilities for Cloudflare tasks supporting Free For Charity.

## Quick Start: Update Staging DNS

The simplest way to update DNS records for `staging.clarkemoyer.com`:

```bash
# Install dependencies (first time only)
pip install -r requirements.txt

# Update staging subdomain IP address
python update_dns.py --name staging --type A --ip 203.0.113.42
```

You'll be prompted for your Cloudflare API token, or you can set it as an environment variable:

```bash
export CLOUDFLARE_API_TOKEN="your_token_here"
python update_dns.py --name staging --type A --ip 203.0.113.42
```

**👉 [See detailed staging subdomain guide →](STAGING_README.md)**

## DNS Management Tool

The `update_dns.py` script provides flexible DNS record management for the `clarkemoyer.com` zone.

### Features

- **Create, update, search, and delete** DNS records
- **Supports A and CNAME** record types
- **Dry-run mode** to preview changes
- **Cloudflare proxy** (orange cloud) support
- **Secure token handling** via environment variable, argument, or prompt

### Requirements

- Python 3.9+
- Install dependencies: `pip install -r requirements.txt`

### Basic Examples

**Update or create an A record:**
```bash
python update_dns.py --name staging --type A --ip 203.0.113.42
```

**Update or create a CNAME record:**
```bash
python update_dns.py --name www --type CNAME --target example.com
```

**Search for existing records:**
```bash
python update_dns.py --name staging --type A --search
```

**Delete a specific record:**
```bash
python update_dns.py --record-id abc123xyz --delete
```

**Enable Cloudflare proxy (orange cloud):**
```bash
python update_dns.py --name staging --type A --ip 203.0.113.42 --proxied
```

**Dry run (preview changes without applying):**
```bash
python update_dns.py --name staging --type A --ip 203.0.113.42 --dry-run
```

### Full Usage

```
python update_dns.py [options]

Options:
  --name NAME           Subdomain name (e.g., 'staging' for staging.clarkemoyer.com)
  --type {A,CNAME}      DNS record type
  --ip IP               New IPv4 address for A records
  --target TARGET       Target domain for CNAME records
  --record-id ID        Specific record ID for deletion
  --search              Search and display existing records
  --delete              Delete the specified record
  --token TOKEN         Cloudflare API token
  --dry-run             Show intended changes without applying
  --proxied             Enable Cloudflare proxy (orange cloud)
```

### Token Security

- API tokens are never logged
- Use environment variables to avoid command-line exposure:
  ```bash
  export CLOUDFLARE_API_TOKEN="your_token_here"
  ```
- Use Cloudflare API tokens with minimal permissions (DNS:Edit for the target zone)
- Dry-run mode allows inspection before making changes

## PowerShell Alternative

For staging subdomain updates only, a PowerShell script is available:

```powershell
./Update-StagingDns.ps1 -NewIp 203.0.113.42
```

**👉 [See PowerShell details in staging guide →](STAGING_README.md)**

## Additional Resources

- **[Staging Subdomain Guide](STAGING_README.md)** - Detailed guide for managing staging.clarkemoyer.com
- **[verify_old_token.json.README.md](verify_old_token.json.README.md)** - Information about the test token response file

