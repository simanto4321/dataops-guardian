# Security Policy

## Reporting a vulnerability

Please email **msimanto46@gmail.com** with details. Do not open a public issue
for security-sensitive reports. You'll get an acknowledgement within a few days.

## Design safeguards

- **No SQL injection surface:** identifiers are whitelisted (`^[A-Za-z0-9_]+$`)
  and quoted; all values are bound parameters.
- **Read-only warehouse access:** the rule engine only issues read queries. Grant
  the app a read-only database role in production.
- **Fail-safe checks:** a failing or malicious check config produces a structured
  `error` result rather than crashing the service or leaking stack traces.
- **Secrets:** configuration is environment-driven (`DATAOPS_*`); `.env` is
  git-ignored and only `.env.example` is committed.
