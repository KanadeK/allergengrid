# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` | Yes |
| Older | No |

## Report a vulnerability

Use GitHub's private vulnerability reporting / Security Advisory flow for this
repository. Do not open a public issue containing an exploit, private event
data, guest information, or a malicious archive.

Include:

- affected version and operating system;
- minimal synthetic reproduction;
- security impact;
- whether parsing, HTML/CSV output, archive verification, or packaging is
  involved;
- suggested remediation if known.

You should receive an acknowledgement through GitHub within seven days.

## Security boundaries

AllergenGrid:

- reads local JSON/CSV;
- writes local reports;
- creates and verifies bounded ZIP packages;
- performs no core network requests;
- does not execute input content.

HTML reports still open in a browser, and CSV files may open in spreadsheet
software. The implementation escapes HTML and neutralizes leading
formula-control characters, but security reports for bypasses are welcome.

Package verification does not extract entries and rejects path traversal,
duplicates, oversized packages, missing/unlisted entries, and hash/size
mismatches.

## Sensitive data

Guest constraints can be sensitive. Keep real cases private and access
controlled. Never attach a real case to a public issue.
