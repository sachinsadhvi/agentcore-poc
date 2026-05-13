"""
End-to-end test for a deployed AgentCore Runtime.

Proves the deployed workflow is multi-agent by:
  1. Invoking the runtime via boto3 invoke_agent_runtime
  2. Parsing the returned state and counting per-agent _result keys
  3. Optionally tailing CloudWatch logs for the runtime to show each Claude call

Usage:
    .venv/bin/python test_runtime.py
    .venv/bin/python test_runtime.py --logs            # also tail CloudWatch
    .venv/bin/python test_runtime.py --agent-id <id>   # pick a specific agent
"""
import argparse
import json
import os
import sys
import time
import uuid

import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = f"http://localhost:{os.getenv('API_PORT', '8000')}"
API_KEY = os.getenv("APP_API_KEY")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

if not API_KEY:
    sys.exit("APP_API_KEY is not set. Add it to your environment or .env file.")


SAMPLE_LOAN_APPLICATION = {
    "user_input": "Please process this loan application end-to-end.",
    "application": {
        "applicant_name": "Jane Doe",
        "ssn_last4": "1234",
        "requested_amount_usd": 250000,
        "purpose": "home purchase",
        "credit_score": 712,
        "annual_income_usd": 96000,
        "monthly_debt_payments_usd": 1450,
        "employer": "Acme Corp",
        "years_at_employer": 4,
        "documents": ["paystub_2026_04.pdf", "w2_2025.pdf", "bank_stmt_apr_2026.pdf"],
    },
}


def pick_agent(preferred_id: str | None = None) -> dict:
    r = requests.get(f"{API_BASE}/agents", headers={"x-api-key": API_KEY}, timeout=10)
    r.raise_for_status()
    agents = r.json().get("agents", [])
    if not agents:
        sys.exit("No deployed agents found. Deploy one first via /workflows/{id}/deploy.")
    if preferred_id:
        for a in agents:
            if a["agent_id"] == preferred_id:
                return a
        sys.exit(f"agent_id {preferred_id} not found.")
    return agents[-1]


def invoke_runtime(agent_arn: str, payload: dict) -> dict:
    client = boto3.client("bedrock-agentcore", region_name=REGION)
    session_id = f"test-session-{uuid.uuid4()}"  # must be >=33 chars
    print(f"[*] Invoking agentRuntimeArn={agent_arn}")
    print(f"    runtimeSessionId={session_id}\n")
    t0 = time.time()
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=json.dumps(payload).encode("utf-8"),
        qualifier="DEFAULT",
    )
    raw = resp["response"].read().decode("utf-8")
    elapsed = time.time() - t0
    print(f"[OK] Runtime responded in {elapsed:.1f}s, {len(raw)} bytes\n")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def report_multi_agent(parsed: dict) -> int:
    output = parsed.get("output", parsed)
    if not isinstance(output, dict):
        print("[WARN] Unexpected output shape:")
        print(json.dumps(parsed, indent=2)[:2000])
        return 0

    agent_keys = [k for k in output.keys() if k.endswith("_result")]
    error_keys = [k for k in output.keys() if k.endswith("_error")]

    print("=" * 70)
    print("MULTI-AGENT EXECUTION REPORT")
    print("=" * 70)
    print(f"workflow_name : {output.get('workflow_name')}")
    print(f"status        : {output.get('status')}")
    print(f"agents that produced results : {len(agent_keys)}")
    print(f"agents that errored          : {len(error_keys)}")
    print()
    for k in agent_keys:
        agent_id = k[: -len("_result")]
        text = str(output[k])
        preview = text[:280].replace("\n", " ")
        print(f"  -> {agent_id}")
        print(f"     {preview}{'...' if len(text) > 280 else ''}\n")
    for k in error_keys:
        print(f"  !! {k}: {output[k]}")

    verdict = "MULTI-AGENT" if len(agent_keys) >= 2 else "SINGLE-AGENT"
    print("=" * 70)
    print(f"VERDICT: {verdict} ({len(agent_keys)} distinct agents fired)")
    print("=" * 70)
    return len(agent_keys)


def tail_logs(runtime_arn: str, seconds: int = 90):
    """Tail CloudWatch log group /aws/bedrock-agentcore/runtimes/<runtimeId>."""
    runtime_id = runtime_arn.split("/")[-1]
    log_group = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"
    print(f"\n[*] Tailing CloudWatch log group: {log_group}")
    logs = boto3.client("logs", region_name=REGION)
    start = int((time.time() - seconds) * 1000)
    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy="LastEventTime",
            descending=True,
            limit=5,
        )["logStreams"]
    except logs.exceptions.ResourceNotFoundException:
        print(f"    Log group not found yet (it appears on first invocation).")
        return
    for s in streams:
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=s["logStreamName"],
            startTime=start,
            limit=200,
        )["events"]
        for e in events:
            print(f"    {e['message'].rstrip()}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", default=None, help="Specific agent_id to test")
    p.add_argument("--logs", action="store_true", help="Also tail CloudWatch logs")
    p.add_argument("--prompt", default=None, help="Override prompt (otherwise uses loan-app sample)")
    args = p.parse_args()

    agent = pick_agent(args.agent_id)
    print(f"[*] Testing agent: {agent['name']} ({agent['agent_id']})")
    print(f"    arn: {agent['agent_arn']}\n")

    payload = SAMPLE_LOAN_APPLICATION.copy()
    if args.prompt:
        payload["user_input"] = args.prompt

    parsed = invoke_runtime(agent["agent_arn"], payload)

    agents_fired = report_multi_agent(parsed)

    if args.logs:
        tail_logs(agent["agent_arn"])

    sys.exit(0 if agents_fired >= 2 else 2)


if __name__ == "__main__":
    main()
