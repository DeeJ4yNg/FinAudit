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
$env:USE_FULL_ARTICAL="false"
```

Only `OPENAI_API_KEY` is required. `OPENAI_MODEL` and `OPENAI_BASE_URL` are optional.
`OPENAI_API_KEY_EMBEDDING` and `OPENAI_API_BASE_EMBEDDING` default to the main API key/base URL if not set.
Set `USE_FULL_ARTICAL=true` to disable retrieval and pass all legal articles to the prompt.

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
  "summary": "一句话总结",
  "issues": [
    {
      "clause_excerpt": "合同原文摘录",
      "risk_level": "高/中/低",
      "risk_reason": "风险原因",
      "legal_citations": [
        {
          "source_path": "法律文件路径",
          "article_no": "第X条",
          "quote": "引用条文原文"
        }
      ],
      "suggestion": "修订建议"
    }
  ]
}
```

## Troubleshooting

- Embedding or OpenAI errors: confirm API keys and base URLs in environment variables
- Web UI shows empty legal files: check `--legal-workspace` path and supported formats
- Legal citation link shows not found: ensure file exists in the legal workspace
If it still happens, restart the web server to reload cached state
