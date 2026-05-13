# Blueprint POC — Project Overview

## What Is This?

**Blueprint POC** is a no-code multi-agent workflow builder. You describe a business process in plain English, and the system:

1. Uses Claude to design a multi-agent pipeline for that process
2. Generates executable LangGraph Python code for it
3. Packages and deploys that code to **AWS Bedrock AgentCore Runtime**
4. Gives you a chat UI to interact with the live deployed agent

The goal is to validate that a natural language prompt can be turned into a real, running, cloud-hosted agentic workflow with minimal human intervention.

---

## High-Level Flow

```
User types a prompt
        │
        ▼
  WorkflowGenerator              ← Claude Haiku converts prompt → JSON workflow schema
  (workflow_generator.py)           (agents, nodes, instructions, DAG order)
        │
        ▼
  ToolRegistry                   ← Keyword-matches relevant tools to the workflow domain
  (tool_registry.py)                (loan tools, fraud tools, AWS tools, etc.)
        │
        ▼
  DeploymentManager              ← Converts schema → LangGraph code → Docker image
  (deployment_manager.py)           → pushes to ECR → deploys to AgentCore Runtime
        │
        ▼
  AgentCore Runtime (AWS)        ← Isolated microVM per session, auto-scaling,
                                    CloudWatch tracing, up to 8h sessions
        │
        ▼
  Chat UI / REST API             ← User chats with the deployed agent via
  (static/index.html + main.py)     invoke_agent_runtime over HTTP
```

---

## Key Components

| File | Role |
|---|---|
| `main.py` | FastAPI server — exposes all REST endpoints, wires services together |
| `workflow_generator.py` | Calls Claude Haiku to convert a prompt into a validated JSON workflow schema |
| `tool_registry.py` | Catalog of available tools; auto-suggests domain-relevant tools via keyword matching |
| `mock_tools.py` | Mock implementations of all domain tools (loan, fraud, AWS); called by generated agent code at runtime |
| `deployment_manager.py` | Converts workflow schema → LangGraph code → Docker/S3 package → deploys to AWS AgentCore |
| `chat_manager.py` | Manages chat sessions: routes messages to deployed agents via `invoke_agent_runtime`, stores history |
| `static/index.html` | React chat UI — sidebar of deployed agents, chat window, build/deploy form |
| `agent_store.py` | In-memory store of deployed agent records (ARN, region, tools) |
| `workflow_editor.py` | CRUD helpers to update/delete agents and tools inside a workflow schema before deploy |

---

## Step-by-Step Technical Flow

### Step 1 — Prompt → Workflow Schema

**File:** `workflow_generator.py`

The user submits a natural language prompt like:

> "I need a loan underwriting workflow that analyses the applicant's financial profile, assesses risk, and writes a decision report."

`WorkflowGenerator.generate()` sends this to **Claude Haiku** (`claude-haiku-4-5-20251001`) with a structured system prompt that instructs it to output a strict JSON schema:

```json
{
  "name": "loan-underwriting",
  "description": "...",
  "schema": {
    "agents": [
      { "id": "intake-agent", "name": "Intake Agent", "role": "...", "instructions": "...", "model": "claude-haiku-4-5-20251001", "temperature": 0.1 },
      { "id": "risk-agent",   "name": "Risk Agent",   "role": "...", "instructions": "...", ... },
      { "id": "writer-agent", "name": "Writer Agent",  "role": "...", "instructions": "...", ... }
    ],
    "workflow": {
      "type": "dag",
      "execution_mode": "serial",
      "nodes": [
        { "id": "node-1", "agent_id": "intake-agent",  "depends_on": [] },
        { "id": "node-2", "agent_id": "risk-agent",    "depends_on": ["node-1"] },
        { "id": "node-3", "agent_id": "writer-agent",  "depends_on": ["node-2"] }
      ]
    }
  }
}
```

Rules enforced:
- 2–4 agents per workflow (keeps latency predictable)
- Serial pipeline: each agent's output feeds into the next as context
- Each agent has a narrow, specific role and a concrete instruction template

---

### Step 2 — Tool Suggestion

**File:** `tool_registry.py`

The `ToolRegistry` does keyword matching on the original prompt to suggest domain-relevant tools:

| Domain keywords | Tools suggested |
|---|---|
| `loan`, `mortgage`, `credit`, `underwriting` | credit-bureau-lookup, income-document-retrieval, bank-statement-analysis, risk-score-calculator, exception-flagger, underwriter-summary-generator |
| `ecommerce`, `fraud`, `transaction`, `order` | fraud-score-checker, velocity-checker, order-risk-evaluator |
| `architecture`, `aws`, `cloud` | aws-kb-server, aws-pricing, aws-compliance-checker |

Tools are registered in three buckets: `aws_bedrock`, `mcp`, `custom`.

---

### Step 3 — Mock Tool Execution

**File:** `mock_tools.py`

All tools have mock implementations that produce realistic, **deterministically seeded** fake data. The seed is derived from the applicant's identifier (via MD5 hash), so the same applicant always gets the same simulated credit score, income, bank balance, etc. — preventing contradictions between agent steps.

Key mock tools:

| Tool | What it returns |
|---|---|
| `get_credit_bureau_data` | Credit score, payment history, delinquencies, open accounts |
| `get_income_documents` | Employment status, annual income, tenure months |
| `get_bank_statements` | Avg 3-month balance, monthly deposits, overdraft incidents |
| `score_risk` | Risk score (0–100), risk tier (LOW/MEDIUM/HIGH), DTI ratio |
| `flag_exceptions` | Exception flags, severity, requires_review boolean |
| `generate_underwriter_summary` | Full formatted underwriting report with recommendation |
| `get_fraud_score` | Fraud score, risk level, detected signals (address mismatch, first card, chargebacks) |
| `get_velocity_check` | Transaction count last 24h/7d, velocity flag |
| `get_order_risk_summary` | Aggregated ORDER risk combining fraud + velocity |

The `execute_tool(tool_name, state)` dispatcher is the single entry point used by the generated LangGraph code at runtime.

---

### Step 4 — Deploy: Schema → Running Agent

**File:** `deployment_manager.py`

Three deployment paths are supported:

#### A. `agentcore-docker` (default)

1. `_generate_langgraph_code(workflow)` — Writes a `main.py` that defines a LangGraph `StateGraph`. Each agent becomes a graph node that calls Claude with its system instruction and the accumulated state. Tool calls are injected via `execute_tool()` from `mock_tools.py`.
2. `_generate_handler(workflow)` — Writes a `handler.py` FastAPI app that AgentCore Runtime calls at `POST /invocations`.
3. A `Dockerfile` is generated and the image is built locally.
4. The image is pushed to **Amazon ECR**.
5. `CreateAgentRuntime` is called with the ECR image URI — AgentCore spins up a managed, isolated microVM.

#### B. `agentcore-runtime` (hosted / S3 ZIP)

1. Agent code is packaged as individual Python files (no Docker needed).
2. Files are uploaded individually to S3 under `agents/<deployment-name>/`.
3. `CreateAgentRuntime` is called pointing at the S3 path.
4. Python 3.12 managed runtime is used — no Docker, faster deploy (~1–2 min vs ~5–10 min).

#### C. `agentcore-native` (Bedrock Agent)

1. Workflow schema is converted to the Bedrock Agent action-group format.
2. A native Bedrock Agent is created with `CreateAgent` + `PrepareAgent`.
3. No container involved — fully managed by AWS.

After deployment, the agent's ARN is saved via `agent_store.save_agent()` so the chat UI can discover it.

---

### Step 5 — Chat with the Agent

**File:** `chat_manager.py`, `static/index.html`

After deployment, `invoke_agent_runtime` is called with:
```json
{
  "prompt": "user message here",
  "history": [ ... previous turns ... ]
}
```

The AgentCore Runtime runs the LangGraph workflow inside the microVM, executes all agents in serial order, and returns the final agent's output as the reply.

Session state is kept in memory (`_sessions` dict keyed by `agent_id → session_id → message list`).

The React UI (`static/index.html`) shows:
- Left sidebar: list of deployed agents
- Main panel: chat window (Chat tab) and build/deploy form (Build tab)
- Supports new session, message history, and real-time replies

---

## Domain Use Cases Pre-Wired

### 1. Loan Underwriting

```
Intake Agent → Risk Assessment Agent → Exception Flagger → Report Writer
```
Tools: credit bureau, income docs, bank statements, risk scorer, exception flagger, underwriter summary

### 2. E-commerce Fraud Detection

```
Transaction Validator → Fraud Scorer → Velocity Checker → Order Risk Evaluator
```
Tools: fraud-score-checker, velocity-checker, order-risk-evaluator

### 3. AWS Architecture Design

```
Requirements Analyst → Service Selector → Cost Estimator → Architecture Writer
```
Tools: aws-kb-server, aws-pricing, aws-compliance-checker, aws-performance-analyzer

---

## REST API Summary

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/workflows/generate` | Prompt → workflow schema |
| `GET` | `/workflows/{id}` | Fetch a generated workflow |
| `PUT` | `/workflows/{id}/agents/{name}` | Edit an agent in the schema |
| `DELETE` | `/workflows/{id}/agents/{name}` | Remove an agent |
| `POST` | `/workflows/{id}/tools` | Add a tool |
| `DELETE` | `/workflows/{id}/tools/{name}` | Remove a tool |
| `GET` | `/tools/available` | List all registered tools |
| `POST` | `/workflows/{id}/deploy` | Deploy to AgentCore Runtime |
| `GET` | `/deployments/{id}` | Get deployment status |
| `POST` | `/deployments/{id}/execute` | Run a deployed workflow |
| `GET` | `/agents` | List deployed agents (requires API key) |
| `POST` | `/chat/{agent_id}/message` | Chat with a deployed agent |
| `GET` | `/chat/{agent_id}/history` | Get conversation history |
| `DELETE` | `/chat/{agent_id}/session` | Reset a session |
| `GET` | `/health` | Health check |

---

## Infrastructure Requirements

```
AWS Services Used:
  - Bedrock AgentCore Runtime   ← hosts and runs the agent microVMs
  - Amazon ECR                  ← Docker image registry (for docker deployment path)
  - Amazon S3                   ← Stores agent ZIP packages (for S3 deployment path)
  - Amazon Bedrock              ← Native agent option + model invocations
  - IAM                         ← Execution role for AgentCore

External APIs:
  - Anthropic API               ← Claude Haiku for schema generation + agents' LLM calls

Environment Variables (from .env):
  ANTHROPIC_API_KEY             ← Anthropic API key
  AWS_ACCOUNT_ID                ← Your AWS account
  AWS_DEFAULT_REGION            ← us-east-1 (note: AgentCore Runtime is us-west-2)
  AWS_ACCESS_KEY_ID             ← AWS credentials
  AWS_SECRET_ACCESS_KEY
  AGENTCORE_EXECUTION_ROLE_ARN  ← IAM role AgentCore assumes to run agents
  APP_API_KEY                   ← API key for chat endpoints
```

---

## Running It

```bash
# Install dependencies
pip install -r requirements.txt   # or use the .venv already present

# Start the API server
python main.py
# → http://localhost:8000  (serves the React UI)
# → http://localhost:8000/docs  (Swagger API docs)

# Or with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## What Is POC-Quality and What Is Not

| What works | What is hardcoded / simplified |
|---|---|
| NL prompt → workflow schema | Workflows stored in-memory (lost on restart) |
| Multi-agent LangGraph code gen | Mock tools (no real credit bureau / bank APIs) |
| Docker + ECR deploy path | AWS keys in `.env` (not secrets manager) |
| S3 ZIP deploy path | Single-region (us-east-1 / us-west-2 mix) |
| Chat with live AgentCore agents | No streaming responses yet |
| Session history per agent | No persistent agent store (DB) |
| Domain-aware tool suggestion | Tool suggestion is keyword-based, not semantic |
