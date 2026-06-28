# Security

The pipeline requires no credentials or private API keys.

Controls include:

- pinned official HTTPS endpoints;
- bounded response size;
- timeouts and retries;
- atomic file writes;
- SHA-256 for every acquired and generated file;
- preserved raw responses;
- fail-closed economic gates;
- no execution of downloaded content;
- no use of secrets in workflow logs.

Report suspected vulnerabilities privately to the repository owner. Do not place credentials, tokens or personal data in issues or source files.
