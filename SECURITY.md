# Security policy

- Do not commit passwords, API keys, personal access tokens or private source credentials.
- The workflow uses the repository-scoped `GITHUB_TOKEN` only to replace the public rolling release.
- Source responses are bounded by a configured maximum size.
- Output filenames are validated to prevent path traversal.
- Raw responses are preserved and hashed before downstream use.
- A future production version should pin every GitHub Action to a reviewed commit SHA.
