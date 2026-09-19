# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** create a public GitHub issue
2. Send details to the maintainers via:
   - Email: [pending]
   - Or contact through the website: https://jiangchenghehe.top

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

## Security Best Practices

When using Pristmax:

- Keep your installation updated to the latest version
- Use strong authentication for web console access
- Restrict network access to the API server in production
- Review file system permissions regularly
- For enterprise deployments, use isolated network environments

## Data Handling

- Pristmax runs locally — your data never leaves your infrastructure
- File metadata is stored in local SQLite databases
- No telemetry or analytics are collected by default
- Always backup your data before running cleanup operations
