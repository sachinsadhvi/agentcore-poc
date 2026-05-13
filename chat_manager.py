import boto3
import json
import uuid
from datetime import datetime
from typing import Optional
from collections import defaultdict

_sessions: dict = defaultdict(dict)

def get_or_create_session(agent_id: str, session_id: Optional[str] = None) -> str:
    """Return an existing session_id or mint a new one (must be 33+ chars per AWS docs)."""
    if session_id and session_id in _sessions[agent_id]:
        return session_id
    new_id = f"session-{agent_id[:8]}-{str(uuid.uuid4())}"
    _sessions[agent_id][new_id] = []
    return new_id

def add_to_history(agent_id, session_id, role, content):
    if session_id not in _sessions[agent_id]:
        _sessions[agent_id][session_id] = []
    _sessions[agent_id][session_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })

def get_history(agent_id, session_id) -> list:
    return _sessions.get(agent_id, {}).get(session_id, [])

def clear_session(agent_id, session_id):
    if agent_id in _sessions and session_id in _sessions[agent_id]:
        _sessions[agent_id][session_id] = []

def send_message(agent_arn, agent_id, session_id, user_message, region) -> str:
    """Invoke the AgentCore Runtime and return the agent's reply text."""
    add_to_history(agent_id, session_id, "user", user_message)

    history = get_history(agent_id, session_id)
    payload = json.dumps({
        "prompt": user_message,
        "history": history[:-1]
    }).encode("utf-8")

    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT"
    )

    raw = response["response"].read().decode("utf-8")

    try:
        result = json.loads(raw)
        # Prefer an explicit top-level "result" or "output" key (set by the handler)
        agent_reply = result.get("result") or result.get("output")
        if not agent_reply:
            # Fall back to collecting all *_result keys from the workflow state.
            # The generated invoke_workflow() stores each agent's output as
            # "<agent-id>_result" on the state dict.  Concatenate them in order
            # so the chat shows the final agent's summary rather than raw JSON.
            result_keys = sorted(k for k in result if k.endswith("_result"))
            if result_keys:
                # Return the last agent's result (typically the summary/writer agent)
                agent_reply = result[result_keys[-1]]
            else:
                agent_reply = raw
    except json.JSONDecodeError:
        agent_reply = raw

    add_to_history(agent_id, session_id, "assistant", str(agent_reply))
    return str(agent_reply)
