# Security Policy

## Supported Versions

We actively support the following versions of VenomQA with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |
| < 0.1   | :x:                |

We recommend always using the latest version to ensure you have the most recent security fixes.

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue in VenomQA, please report it responsibly.

### How to Report

**Do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them using one of these methods:

1. **GitHub Security Advisories (Preferred)**
   
   Go to [Security Advisories](https://github.com/namanagarwal/venomqa/security/advisories/new) and submit a private vulnerability report.

2. **Email**
   
   Send details to: **security@venomqa.dev**
   
   Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
   - Your contact information

### What to Include

Please provide as much information as possible:

- **Type of vulnerability** (e.g., injection, authentication bypass, data exposure)
- **Affected versions** 
- **Attack vector** (how the vulnerability can be exploited)
- **Proof of concept** (minimal code to demonstrate the issue)
- **Impact assessment** (what an attacker could achieve)
- **Suggested remediation** (if you have ideas for fixing it)

### Response Timeline

| Stage | Timeline |
|-------|----------|
| Initial Response | Within 48 hours |
| Vulnerability Assessment | Within 7 days |
| Fix Development | Depends on severity |
| Security Advisory Published | After fix is released |

### What to Expect

1. **Acknowledgment**: We'll confirm receipt of your report within 48 hours
2. **Assessment**: We'll investigate and validate the vulnerability
3. **Updates**: We'll keep you informed of our progress
4. **Resolution**: We'll develop and test a fix
5. **Disclosure**: We'll coordinate disclosure with you

## Security Best Practices

When using VenomQA, follow these security practices:

### Database Credentials

Never hardcode database credentials in your journey files:

```python
# DON'T do this
db_url = "postgresql://user:password@host/db"

# DO this instead - use environment variables
import os
db_url = os.environ.get("VENOMQA_DB_URL")
```

### Configuration Files

Add `venomqa.yaml` to your `.gitignore` if it contains sensitive information:

```gitignore
# Sensitive configuration
venomqa.yaml
.env
.env.*
```

### Secrets Management

Use environment variables or a secrets manager:

```bash
# Set environment variables
export VENOMQA_DB_URL="postgresql://user:pass@host/db"
export VENOMQA_BASE_URL="https://api.example.com"
```

### Test Data

- Use dedicated test databases with isolated credentials
- Never use production credentials in tests
- Rotate test credentials regularly

### Network Security

When connecting to test environments:
- Use HTTPS for API connections
- Verify SSL certificates in production-like tests
- Use VPN or private networks when possible

## Known Security Considerations

### SQL Injection

VenomQA uses parameterized queries internally. However, be cautious when:
- Building dynamic SQL queries in your test actions
- Using raw SQL in state management

### Data Exposure

Test reports may contain sensitive data. Ensure:
- Reports are stored securely
- Reports are not committed to version control
- Sensitive data is masked in logs

## Security Updates

Security updates are announced through:
- [GitHub Security Advisories](https://github.com/namanagarwal/venomqa/security/advisories)
- [Release Notes](https://github.com/namanagarwal/venomqa/releases)
- PyPI package updates

Subscribe to releases to stay informed about security updates.

## Responsible Disclosure Policy

We follow responsible disclosure practices:
- We credit security researchers who report vulnerabilities responsibly
- We work with reporters to coordinate disclosure timing
- We publish security advisories after fixes are available

## Contact

For any security-related questions or concerns:
- **Security Reports**: security@venomqa.dev
- **General Inquiries**: https://github.com/namanagarwal/venomqa/discussions

Thank you for helping keep VenomQA and its users safe!
