# Multi-Agent POC on Bedrock AgentCore Runtime
### S3 Direct Code Deploy · Hardcoded Creds · Any Prompt · POC Quality

---

## What you're building

You give it **any natural language prompt** describing a workflow.  
It figures out how many agents are needed, generates their code, zips them, uploads to S3, and deploys each to AgentCore Runtime. The supervisor agent then calls sub-agents using `InvokeAgentRuntime` over HTTP.

```
Your prompt (any domain)
       │
       ▼
 schema_compiler.py          ← Claude API: prompt → list of agents
       │
       ▼
 agent code generator        ← writes agent_X.py for each agent
       │
       ▼
 zip + upload to S3          ← one zip per agent
       │
       ▼
 CreateAgentRuntime (S3 URI) ← one Runtime per agent, get ARNs back
       │
       ▼
 supervisor calls sub-agents ← InvokeAgentRuntime over A2A/HTTP
       │
       ▼
 Final merged answer
```

---

## Why S3 (direct code deploy) not ECR (Docker)

| | S3 / Direct code deploy | ECR / Docker |
|---|---|---|
| Docker needed? | ❌ No | ✅ Yes |
| Deploy speed | Fast (~1-2 min) | Slow (~5-10 min) |
| Session rate | 25/sec | 0.16/sec |
| Package limit | 250MB | 1GB |
| Good for POC? | ✅ Yes | Overkill |

For a POC, S3 wins every time. No Docker, no ECR, just zip your Python and point AgentCore at the S3 URI.

---

## Prerequisites

```bash
pip install anthropic boto3 requests

# AWS credentials — hardcoded for POC (never do this in prod)
export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
export AWS_DEFAULT_REGION="us-west-2"          # AgentCore Runtime is us-west-2
export ANTHROPIC_API_KEY="YOUR_ANTHROPIC_KEY"

# One S3 bucket for all agent zips
export S3_BUCKET="my-agentcore-poc-bucket"

# IAM role that AgentCore Runtime will use to run your agents
export AGENTCORE_ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT:role/AgentCoreRuntimeRole"
```

### IAM Role needed (AgentCoreRuntimeRole)

Create this role in IAM console with trust policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
```

Attach these managed policies to it:
- `AmazonBedrockFullAccess`
- `CloudWatchLogsFullAccess`
- `AmazonS3ReadOnlyAccess`

---

## Project structure

```
poc/
├── schema_compiler.py      # Step 1: prompt → agent definitions
├── agent_generator.py      # Step 2: agent definitions → Python files
├── deployer.py             # Step 3: zip → S3 → AgentCore Runtime
├── runner.py               # Step 4: invoke supervisor → get answer
├── main.py                 # Run everything end to end
└── generated/              # Auto-created, holds agent_*.py files
```

---

## Step 1 — schema_compiler.py

Takes any prompt, returns a list of agent definitions.

```python
# schema_compiler.py
import os
import json
import re
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM = """
You convert a user's workflow description into a JSON array of agent definitions.
Each agent has a specific job. Keep it minimal — 2 to 4 agents total for a POC.

Rules:
- Always include exactly ONE supervisor agent (mode: supervisor)
- All others are collaborator agents (mode: collaborator)
- Supervisor orchestrates the others in sequence
- Each collaborator does ONE specific job
- Keep instructions short and clear

Return ONLY a valid JSON array, no explanation, no markdown. Example:
[
  {
    "name": "supervisor",
    "mode": "supervisor",
    "instruction": "You orchestrate this workflow. Call each sub-agent in order and merge their outputs into a final answer.",
    "job": "Orchestrator"
  },
  {
    "name": "researcher",
    "mode": "collaborator",
    "instruction": "You research the given topic and return a concise summary of key facts.",
    "job": "Research"
  },
  {
    "name": "writer",
    "mode": "collaborator",
    "instruction": "You take research notes and write a clear, structured response.",
    "job": "Writing"
  }
]
"""

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()

def _safe_name(name: str, idx: int) -> str:
    n = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    return n or f"agent_{idx}"

def _default_supervisor() -> dict:
    return {
        "name": "supervisor",
        "mode": "supervisor",
        "instruction": "Orchestrate collaborators in order and return one final merged answer.",
        "job": "Orchestrator"
    }

def normalize_agents(raw_agents: list) -> list:
    if not isinstance(raw_agents, list):
        raise ValueError("Model output must be a JSON array")

    supervisors = [a for a in raw_agents if isinstance(a, dict) and a.get("mode") == "supervisor"]
    collaborators = [a for a in raw_agents if isinstance(a, dict) and a.get("mode") == "collaborator"]

    # Keep exactly one supervisor.
    supervisor = supervisors[0] if supervisors else _default_supervisor()
    supervisor["name"] = "supervisor"
    supervisor["mode"] = "supervisor"
    supervisor["instruction"] = supervisor.get("instruction", _default_supervisor()["instruction"])
    supervisor["job"] = supervisor.get("job", "Orchestrator")

    # Keep up to 3 collaborators for predictable POC latency and cost.
    normalized_collabs = []
    for idx, agent in enumerate(collaborators[:3], start=1):
        normalized_collabs.append({
            "name": _safe_name(agent.get("name", f"agent_{idx}"), idx),
            "mode": "collaborator",
            "instruction": agent.get("instruction", "Complete your assigned step and return concise output."),
            "job": agent.get("job", f"Step {idx}")
        })

    # Any-prompt fallback: ensure at least one collaborator exists.
    if not normalized_collabs:
        normalized_collabs = [{
            "name": "worker",
            "mode": "collaborator",
            "instruction": "Analyze the user request and return a concise draft answer.",
            "job": "General task execution"
        }]

    return [supervisor] + normalized_collabs

def compile_prompt_to_agents(user_prompt: str) -> list:
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_prompt}]
    )
    raw = _strip_code_fences(response.content[0].text)
    parsed = json.loads(raw)
    agents = normalize_agents(parsed)
    print(f"[schema] Normalized {len(agents)} agents: {[a['name'] for a in agents]}")
    return agents
```

---

## Step 2 — agent_generator.py

Writes a `.py` file for each agent. Each file is a tiny FastAPI server that AgentCore Runtime can call.

```python
# agent_generator.py
import os
import json

os.makedirs("generated", exist_ok=True)

# This is the template every agent gets.
# AgentCore Runtime calls POST /invocations with {"prompt": "...", "context": "..."}
# The agent responds with {"response": "...", "agent": "...", "ok": true}
AGENT_TEMPLATE = '''
import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import anthropic
import uvicorn

app = FastAPI()
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

INSTRUCTION = """{instruction}"""

@app.get("/health")
def health():
    return {{"status": "ok", "agent": "{name}"}}

@app.post("/invocations")
async def invoke(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    context = body.get("context", "")
    user_input = context if context else prompt

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        system=INSTRUCTION,
        messages=[{{"role": "user", "content": user_input}}]
    )
    return JSONResponse({{
        "response": response.content[0].text,
        "agent": "{name}",
        "ok": True
    }})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
'''

# Supervisor is different — it calls the sub-agents by their ARNs
SUPERVISOR_TEMPLATE = '''
import os
import json
import boto3
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

INSTRUCTION = """{instruction}"""

# Sub-agent ARNs injected at deploy time
SUB_AGENT_ARNS = {sub_agent_arns_placeholder}

def _read_payload_body(response: dict) -> dict:
    body = response.get("body")
    if hasattr(body, "read"):
        raw = body.read()
    else:
        raw = body
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return json.loads(raw or "{}")

def invoke_sub_agent(arn: str, prompt: str, context: str) -> dict:
    """Call another AgentCore Runtime agent via InvokeAgentRuntime"""
    client = boto3.client(
        "bedrock-agentcore",
        region_name="us-west-2",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        payload=json.dumps({{"prompt": prompt, "context": context}}).encode()
    )
    return _read_payload_body(response)

@app.get("/health")
def health():
    return {{"status": "ok", "agent": "supervisor"}}

@app.post("/invocations")
async def invoke(request: Request):
    body = await request.json()
    user_prompt = body.get("prompt", "")

    # Call each sub-agent in fixed order from normalized schema.
    context = f"User request: {{user_prompt}}\\n\\n"
    for agent_name, arn in SUB_AGENT_ARNS.items():
        print(f"[supervisor] calling {{agent_name}}...")
        try:
            result = invoke_sub_agent(arn, user_prompt, context)
            text = result.get("response", "")
            ok = bool(result.get("ok", True))
        except Exception as e:
            text = f"[error] {{e}}"
            ok = False
        context += f"{{agent_name}} output (ok={{ok}}):\\n{{text}}\\n\\n"

    # Final synthesis
    import anthropic
    client_llm = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    final = client_llm.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2048,
        system=INSTRUCTION,
        messages=[{{"role": "user", "content": context}}]
    )
    return JSONResponse({{
        "response": final.content[0].text,
        "agent": "supervisor",
        "ok": True
    }})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
'''

REQUIREMENTS = """fastapi
uvicorn
anthropic
boto3
"""

def generate_agent_files(agents: list) -> dict:
    """
    Write a .py file for each agent.
    Returns dict of {agent_name: file_path}
    """
    collaborators = [a for a in agents if a["mode"] == "collaborator"]
    files = {}

    # Write collaborator agents first
    for agent in collaborators:
        name = agent["name"]
        code = AGENT_TEMPLATE.format(
            name=name,
            instruction=agent["instruction"].replace('"', '\\"')
        )
        path = f"generated/agent_{name}.py"
        with open(path, "w") as f:
            f.write(code)

        req_path = f"generated/requirements_{name}.txt"
        with open(req_path, "w") as f:
            f.write(REQUIREMENTS)

        files[name] = path
        print(f"[generator] wrote {path}")

    # Write collaborator execution order for deterministic orchestration.
    order_path = "generated/collaborator_order.json"
    with open(order_path, "w") as f:
        json.dump([a["name"] for a in collaborators], f, indent=2)

    # Write supervisor — sub-agent ARNs will be filled in after deploy
    # For now write a placeholder; deployer.py patches it after getting ARNs
    supervisor = next(a for a in agents if a["mode"] == "supervisor")
    sup_code = SUPERVISOR_TEMPLATE.format(
        instruction=supervisor["instruction"].replace('"', '\\"'),
        sub_agent_arns_placeholder="{}"  # filled in by deployer after sub-agents deployed
    )
    sup_path = "generated/agent_supervisor.py"
    with open(sup_path, "w") as f:
        f.write(sup_code)

    req_path = "generated/requirements_supervisor.txt"
    with open(req_path, "w") as f:
        f.write(REQUIREMENTS)

    files["supervisor"] = sup_path
    print(f"[generator] wrote {sup_path}")
    return files
```

---

## Step 3 — deployer.py

Zips each agent, uploads to S3, calls `CreateAgentRuntime`.

```python
# deployer.py
import os
import json
import zipfile
import boto3
import time

S3_BUCKET = os.environ["S3_BUCKET"]
AGENTCORE_ROLE_ARN = os.environ["AGENTCORE_ROLE_ARN"]
AWS_REGION = "us-west-2"

def require_env(keys: list):
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

require_env([
    "S3_BUCKET",
    "AGENTCORE_ROLE_ARN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "ANTHROPIC_API_KEY"
])

s3 = boto3.client("s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"]
)

agentcore = boto3.client("bedrock-agentcore",
    region_name=AWS_REGION,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"]
)

def zip_and_upload(agent_name: str, agent_py: str, requirements_txt: str) -> str:
    """Zip agent file + requirements, upload to S3, return s3 URI"""
    zip_path = f"generated/{agent_name}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(agent_py, "main.py")            # AgentCore looks for main.py
        zf.write(requirements_txt, "requirements.txt")

    s3_key = f"agentcore-poc/{agent_name}.zip"
    s3.upload_file(zip_path, S3_BUCKET, s3_key)
    s3_uri = f"s3://{S3_BUCKET}/{s3_key}"
    print(f"[deployer] uploaded {agent_name} → {s3_uri}")
    return s3_uri

def create_runtime(agent_name: str, s3_uri: str) -> str:
    """Deploy agent to AgentCore Runtime, return ARN"""
    response = agentcore.create_agent_runtime(
        agentRuntimeName=f"poc-{agent_name}-{int(time.time())}",
        description=f"POC agent: {agent_name}",
        agentRuntimeArtifact={
            "codeArtifact": {
                "s3CodeArtifact": {
                    "s3Uri": s3_uri,
                    "runtimeEnvironment": {
                        "name": "PYTHON3_12"    # Python 3.12 managed runtime
                    }
                }
            }
        },
        networkConfiguration={"networkMode": "PUBLIC"},
        executionRoleArn=AGENTCORE_ROLE_ARN,
        environmentVariables={
            # Hardcoded for POC
            "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
            "AWS_ACCESS_KEY_ID": os.environ["AWS_ACCESS_KEY_ID"],
            "AWS_SECRET_ACCESS_KEY": os.environ["AWS_SECRET_ACCESS_KEY"]
        }
    )
    arn = response["agentRuntimeArn"]
    print(f"[deployer] created runtime for {agent_name}: {arn}")
    return arn

def wait_for_ready(arn: str, agent_name: str, timeout=120):
    """Poll until runtime is ACTIVE"""
    print(f"[deployer] waiting for {agent_name} to be ACTIVE...")
    for _ in range(timeout // 5):
        resp = agentcore.get_agent_runtime(agentRuntimeArn=arn)
        status = resp["status"]
        if status == "ACTIVE":
            print(f"[deployer] {agent_name} is ACTIVE")
            return
        if status == "FAILED":
            reason = resp.get("failureReason", "Unknown failure")
            raise Exception(f"{agent_name} runtime FAILED to start: {reason}")
        time.sleep(5)
    raise TimeoutError(f"{agent_name} did not become ACTIVE in {timeout}s")

def patch_supervisor_arns(supervisor_py: str, sub_arns: dict):
    """Inject real sub-agent ARNs into supervisor code"""
    with open(supervisor_py, "r") as f:
        code = f.read()
    arns_str = json.dumps(sub_arns, indent=4)
    code = code.replace("{}", arns_str, 1)
    with open(supervisor_py, "w") as f:
        f.write(code)
    print(f"[deployer] patched supervisor with ARNs: {list(sub_arns.keys())}")

def deploy_all(agents: list, files: dict) -> dict:
    """
    Deploy sub-agents first, then patch supervisor with their ARNs, then deploy supervisor.
    Returns dict of {agent_name: arn}
    """
    arns = {}
    collaborators = [a for a in agents if a["mode"] == "collaborator"]
    supervisor = next(a for a in agents if a["mode"] == "supervisor")

    # Deploy collaborators first
    for agent in collaborators:
        name = agent["name"]
        agent_py = f"generated/agent_{name}.py"
        req_txt = f"generated/requirements_{name}.txt"
        s3_uri = zip_and_upload(name, agent_py, req_txt)
        arn = create_runtime(name, s3_uri)
        arns[name] = arn

    # Wait for all collaborators to be ready
    for name, arn in arns.items():
        wait_for_ready(arn, name)

    # Patch supervisor with real ARNs, then deploy it
    patch_supervisor_arns(files["supervisor"], arns)
    sup_py = "generated/agent_supervisor.py"
    sup_req = "generated/requirements_supervisor.txt"
    sup_s3 = zip_and_upload("supervisor", sup_py, sup_req)
    sup_arn = create_runtime("supervisor", sup_s3)
    wait_for_ready(sup_arn, "supervisor")
    arns["supervisor"] = sup_arn

    # Save ARNs to disk so you can reuse without redeploying
    with open("generated/arns.json", "w") as f:
        json.dump(arns, f, indent=2)
    print(f"\n[deployer] all ARNs saved to generated/arns.json")
    return arns
```

---

## Step 4 — runner.py

Call the supervisor, get the answer.

```python
# runner.py
import os
import json
import boto3

AWS_REGION = "us-west-2"

def _read_payload_body(response: dict) -> dict:
    body = response.get("body")
    if hasattr(body, "read"):
        raw = body.read()
    else:
        raw = body
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    return json.loads(raw or "{}")

def run(user_prompt: str, supervisor_arn: str) -> str:
    client = boto3.client(
        "bedrock-agentcore",
        region_name=AWS_REGION,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"]
    )

    response = client.invoke_agent_runtime(
        agentRuntimeArn=supervisor_arn,
        payload=json.dumps({"prompt": user_prompt}).encode()
    )

    result = _read_payload_body(response)
    return result.get("response", "")
```

---

## Step 5 — main.py

Ties everything together. Run once to deploy. Run again to just invoke (skips deploy).

```python
# main.py
import os
import json
import sys
import hashlib
from schema_compiler import compile_prompt_to_agents
from agent_generator import generate_agent_files
from deployer import deploy_all
from runner import run

def schema_fingerprint(agents: list) -> str:
    canonical = json.dumps(agents, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()

def main():
    # -----------------------------------------------------------
    # YOUR PROMPT HERE — change this to anything
    # -----------------------------------------------------------
    workflow_prompt = """
    I need a loan underwriting workflow that:
    1. Analyses the applicant's financial profile
    2. Assesses risk
    3. Writes a decision report
    """
    # Try any domain:
    # "I need a customer support workflow that triages complaints, looks up orders, and drafts a response"
    # "I need a content pipeline that researches a topic, writes a blog post, and proofreads it"
    # -----------------------------------------------------------

    arns_file = "generated/arns.json"
    meta_file = "generated/deploy_meta.json"
    force_redeploy = False

    # Compile first so we can detect workflow changes.
    agents = compile_prompt_to_agents(workflow_prompt)
    fp = schema_fingerprint(agents)

    # If already deployed and schema unchanged, skip deployment.
    if os.path.exists(arns_file) and os.path.exists(meta_file) and not force_redeploy:
        with open(meta_file) as f:
            meta = json.load(f)
        same_schema = meta.get("workflow_fingerprint") == fp
        if same_schema:
            print("[main] Existing deployment matches workflow. Skipping deploy.")
            with open(arns_file) as f:
                arns = json.load(f)
        else:
            print("[main] Workflow changed. Redeploying runtimes...\n")
            files = generate_agent_files(agents)
            arns = deploy_all(agents, files)
            with open(meta_file, "w") as f:
                json.dump({"workflow_fingerprint": fp}, f, indent=2)
    elif os.path.exists(arns_file) and not force_redeploy:
        print("[main] Found existing deployment. Skipping deploy, going straight to invoke.")
        with open(arns_file) as f:
            arns = json.load(f)
    else:
        print("[main] No existing deployment found. Deploying now...\n")
        files = generate_agent_files(agents)
        arns = deploy_all(agents, files)
        with open(meta_file, "w") as f:
            json.dump({"workflow_fingerprint": fp}, f, indent=2)

    supervisor_arn = arns["supervisor"]

    # Step 4: Ask a question — change this freely
    user_question = sys.argv[1] if len(sys.argv) > 1 else \
        "Assess this loan application: John Doe, income $8000/month, credit score 720, requesting $250,000."

    print(f"\n[main] Sending to supervisor:\n{user_question}\n")
    print("=" * 60)

    answer = run(user_question, supervisor_arn)
    print(answer)
    print("=" * 60)

if __name__ == "__main__":
    main()
```

---

## How to run it

```bash
# 1. Clone / create the poc/ folder with the files above

# 2. Set env vars (hardcoded for POC)
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-west-2"
export ANTHROPIC_API_KEY="sk-ant-..."
export S3_BUCKET="my-poc-bucket"
export AGENTCORE_ROLE_ARN="arn:aws:iam::123456789:role/AgentCoreRuntimeRole"

# 3. Create the S3 bucket (one time)
aws s3 mb s3://$S3_BUCKET --region us-west-2

# 4. Install dependencies
pip install anthropic boto3 fastapi uvicorn requests

# 5. First run — deploys everything (~3-5 min)
python main.py

# 6. Second run — skips deploy, just invokes (fast)
python main.py "Assess this application: Jane Smith, income $12000/month, score 780"

# 7. Change the workflow_prompt in main.py for a different domain
#    Delete generated/arns.json to force a fresh deploy
```

### Quick validation matrix (POC)

Use these three prompts to validate any-prompt behavior:

1. Structured business workflow:
   `"Build a loan underwriting workflow with financial analysis, risk scoring, and final decision writing."`
2. Creative workflow:
   `"Build a content workflow to research an AI topic, draft a blog post, and proofread it."`
3. Ambiguous short prompt:
   `"Help me plan a product launch."`

Success criteria for each run:
- schema output includes exactly 1 supervisor and at least 1 collaborator
- all deployed runtimes reach `ACTIVE`
- invoking supervisor returns a non-empty `response`
- if prompt structure changes, fingerprint triggers redeploy automatically

---

## Is it one-time or recurring?

```
First run   →  deploys all agents to AgentCore Runtime (~3-5 min)
                arns.json saved to disk

Every run after that  →  reads arns.json, skips deploy, just invokes (~5 sec)

Change workflow_prompt  →  delete arns.json, run again → fresh deploy
Change a sub-agent's logic  →  delete arns.json, run again → redeploy that agent
```

The deploy is **not one-time forever** — it creates new Runtime instances each run if you delete arns.json. But for a POC you deploy once per workflow type and reuse it.

---

## What AgentCore Runtime actually does for you (why use it at all)

Without AgentCore Runtime you'd need to run your own servers. With it:

- Each session runs in an **isolated microVM** — no cross-session data leaks
- Scales automatically — zero to many sessions with no config
- Up to **8 hours** per session — important if your workflow is slow
- Built-in **CloudWatch tracing** — see every agent call in the console
- You only pay for **active CPU** — I/O wait (waiting for Claude) is free

For a POC this is genuinely useful because you skip all the server management.

---

## Things to watch out for (POC-level gotchas)

- `bedrock-agentcore` boto3 client — confirm exact service name in your boto3 version (`pip show boto3`)
- AgentCore Runtime is **us-west-2 only** right now — don't try other regions
- Direct code deploy (S3/ZIP) runtime name is `PYTHON3_12` — check AWS docs if it changes
- The `environmentVariables` field in `CreateAgentRuntime` is where you pass API keys — max 4KB total
- Delete `generated/arns.json` whenever you want a clean redeploy
- For the POC, hardcoded AWS keys in env vars is fine — just don't commit them to git
