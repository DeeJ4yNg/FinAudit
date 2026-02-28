# Financial Auditing Agent

AI agent for contract compliance review with legal rule grounding.

## Requirements

- Python 3.9+
- Virtual environment recommended

## Setup

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Alternative environments

Conda:

```bash
conda create -n fa-agent python=3.10
conda activate fa-agent
pip install -r requirements.txt
```

uv:

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Configure OpenAI API

Set environment variables before running:

macOS/Linux:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-4.1-mini"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
export OPENAI_API_KEY_EMBEDDING="your-embedding-api-key"
export OPENAI_API_BASE_EMBEDDING="https://api.openai.com/v1"
export USE_FULL_ARTICAL="false"
```

Windows (PowerShell):

```bash
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-4.1-mini"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
$env:OPENAI_API_KEY_EMBEDDING="your-embedding-api-key"
$env:OPENAI_API_BASE_EMBEDDING="https://api.openai.com/v1"
$env:LAW_RETRIEVAL="2"
```

Only `OPENAI_API_KEY` is required. `OPENAI_MODEL` and `OPENAI_BASE_URL` are optional.
`OPENAI_API_KEY_EMBEDDING` and `OPENAI_API_BASE_EMBEDDING` default to the main API key/base URL if not set.
Set `LAW_RETRIEVAL` to control how contract text and legal articles are attached:

- `1`: full contract + full laws (no retrieval)
- `2`: full contract + retrieved top-k laws
- `3`: chunked contract + retrieved top-k laws, then summarize

## .env Construction

Place `.env` at the project root. Use `KEY="VALUE"` per line. The app loads it on startup (existing system environment variables take precedence).

Minimal configuration:

```
OPENAI_API_KEY="your-api-key"
LAW_RETRIEVAL="3"
```

Common full configuration:

```
OPENAI_API_KEY="your-api-key"
OPENAI_MODEL="gpt-4.1-mini"
OPENAI_BASE_URL="https://api.openai.com/v1"

OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
OPENAI_API_KEY_EMBEDDING="your-embedding-api-key"
OPENAI_API_BASE_EMBEDDING="https://api.openai.com/v1"

LAW_RETRIEVAL="3"
CONTRACT_MAX_CHARS="2000"
MEMORY_LEN="1200"
```

Field descriptions:

- `OPENAI_API_KEY`: primary model API key, required
- `OPENAI_MODEL`: primary model name, default gpt-4.1-mini
- `OPENAI_BASE_URL`: primary model base URL, optional
- `OPENAI_EMBEDDING_MODEL`: embedding model name, default text-embedding-3-small
- `OPENAI_API_KEY_EMBEDDING`: embedding API key, defaults to `OPENAI_API_KEY`
- `OPENAI_API_BASE_EMBEDDING`: embedding base URL, defaults to `OPENAI_BASE_URL`
- `LAW_RETRIEVAL`: retrieval mode (1/2/3), recommended 3
- `CONTRACT_MAX_CHARS`: max contract chunk size, minimum 200, default 20000
- `MEMORY_LEN`: feedback memory length cap, minimum 200, default 1200

Notes:

- When `LAW_RETRIEVAL` is set, it overrides `USE_FULL_ARTICAL`
- Never commit real secrets in `.env`

## Run the audit

Provide a contract file and a legal workspace directory that contains law documents:

```bash
python -m Agent.app.cli --contract <contract-file> --legal-workspace <legal-workspace> --output <output-json>
```

Example:

```bash
python -m Agent.app.cli --contract .\data\contract.docx --legal-workspace .\data\legal --output .\output\audit.json
```

## Run the web UI

Start the web server with the legal workspace directory:

```bash
python -m Agent.app.web.server --legal-workspace .\data\legal --port 8000
```

Open the UI in the browser:

```
http://localhost:8000/
```

### Web UI features

- Upload contracts (PDF/DOCX) and run audit from the browser
- Manage legal files (list/upload/view/delete)
- Legal citations are clickable and open the source text with highlight
- Suggestions whose citations cannot be resolved are filtered out

## Deployment

Bind to all interfaces on a server:

```bash
python -m Agent.app.web.server --legal-workspace /path/to/legal --host 0.0.0.0 --port 8000
```

Run behind a reverse proxy or a process manager as needed.

## Deployment Steps

1. Prepare runtime and dependencies

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Prepare the legal workspace directory (.txt/.md/.pdf/.docx)

```
mkdir -p /data/legal
```

3. Configure `.env` and set parameters like `LAW_RETRIEVAL` and `CONTRACT_MAX_CHARS`

4. Start the service (use 0.0.0.0 for public binding)

```
python -m Agent.app.web.server --legal-workspace /data/legal --host 0.0.0.0 --port 8000
```

5. Run behind a reverse proxy or process manager (optional)

- Use Nginx/Apache for HTTPS and rate limiting
- Use systemd/supervisor/pm2 for process supervision

## Legal workspace rules

The `legal-workspace` directory is the only location the agent can read legal rules from. Supported formats:

- .txt
- .md
- .pdf
- .docx

## Output format

The audit output is JSON with risk score, summary, issues, and legal citations:

```json
{
  "overall_risk_score": 0,
  "summary": "one-line summary",
  "issues": [
    {
      "clause_excerpt": "contract excerpt",
      "risk_level": "high/medium/low",
      "risk_reason": "risk rationale",
      "legal_citations": [
        {
          "source_path": "legal file path",
          "article_no": "Article X",
          "quote": "quoted text"
        }
      ],
      "suggestion": "revision suggestion"
    }
  ]
}
```

## Troubleshooting

- Embedding or OpenAI errors: confirm API keys and base URLs in environment variables
- Web UI shows empty legal files: check `--legal-workspace` path and supported formats
- Legal citation link shows not found: ensure file exists in the legal workspace
If it still happens, restart the web server to reload cached state
