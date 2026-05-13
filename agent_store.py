from typing import Optional
import uuid
from datetime import datetime

_agents: dict = {}

def save_agent(name, prompt, agent_arn, agent_runtime_endpoint, image_uri, region, tools) -> dict:
    agent_id = f"agent-{str(uuid.uuid4())[:8]}"
    record = {
        "agent_id": agent_id,
        "name": name,
        "prompt": prompt,
        "agent_arn": agent_arn,
        "agent_runtime_endpoint": agent_runtime_endpoint,
        "image_uri": image_uri,
        "region": region,
        "tools": tools,
        "status": "READY",
        "created_at": datetime.utcnow().isoformat(),
        "console_url": f"https://{region}.console.aws.amazon.com/bedrock-agentcore/agents?agentArn={agent_arn}"
    }
    _agents[agent_id] = record
    return record

def get_agent(agent_id: str) -> Optional[dict]:
    return _agents.get(agent_id)

def list_agents() -> list:
    return list(_agents.values())

def update_agent_status(agent_id: str, status: str):
    if agent_id in _agents:
        _agents[agent_id]["status"] = status
