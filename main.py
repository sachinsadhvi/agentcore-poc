"""
Blueprint POC - Main API Server
Converts natural language prompts into executable agentic workflows
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

from workflow_generator import WorkflowGenerator
from tool_registry import ToolRegistry
from workflow_editor import WorkflowEditor
from deployment_manager import DeploymentManager
from chat_manager import send_message, get_or_create_session, get_history, clear_session
from agent_store import list_agents, get_agent, save_agent

# Initialize FastAPI app
app = FastAPI(
    title="Blueprint POC API",
    description="Convert natural language to executable agentic workflows"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key authentication (set APP_API_KEY in .env; if unset, protected routes accept any key)
API_KEY = os.getenv("APP_API_KEY")

def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# Mount static files (serves static/index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Read configuration from environment
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Initialize services
tool_registry = ToolRegistry()
workflow_generator = WorkflowGenerator(tool_registry=tool_registry)
workflow_editor = WorkflowEditor()
deployment_manager = DeploymentManager(
    aws_region=AWS_REGION,
    aws_account_id=AWS_ACCOUNT_ID,
    aws_access_key=AWS_ACCESS_KEY,
    aws_secret_key=AWS_SECRET_KEY
)

# ============================================================================
# Data Models
# ============================================================================

class WorkflowGenerationRequest(BaseModel):
    """Request to generate a workflow from natural language"""
    prompt: str
    auto_suggest_tools: bool = True
    include_memory: bool = True
    include_knowledge_base: bool = True

class WorkflowGenerationResponse(BaseModel):
    """Generated workflow response"""
    workflow_id: str
    name: str
    description: str
    schema: Dict[str, Any]
    suggested_tools: List[str]
    created_at: str

class AgentUpdateRequest(BaseModel):
    """Update an agent in the workflow"""
    name: Optional[str] = None
    role: Optional[str] = None
    tools: Optional[List[str]] = None
    instructions: Optional[str] = None

class ToolUpdateRequest(BaseModel):
    """Add/update a tool in the workflow"""
    name: str
    source: str  # aws-bedrock, mcp, custom
    description: str
    endpoint: Optional[str] = None

class WorkflowDeploymentRequest(BaseModel):
    """Deploy workflow to AgentCore Runtime"""
    runtime: str = "agentcore"  # agentcore, flotorch, langgraph
    deployment_name: str
    aws_credentials: Optional[Dict[str, str]] = None

class WorkflowExecutionRequest(BaseModel):
    """Execute a deployed workflow"""
    deployment_id: str
    input_data: Dict[str, Any]

# ============================================================================
# Endpoints
# ============================================================================

@app.post("/workflows/generate", response_model=WorkflowGenerationResponse)
async def generate_workflow(request: WorkflowGenerationRequest):
    """
    Generate a workflow from natural language prompt

    Example:
    {
        "prompt": "Create a workflow that analyzes AWS architecture requirements, selects optimal services, and generates a cost estimate",
        "auto_suggest_tools": true,
        "include_memory": true,
        "include_knowledge_base": true
    }
    """
    try:
        # Generate workflow
        workflow = await workflow_generator.generate(
            prompt=request.prompt,
            auto_suggest_tools=request.auto_suggest_tools,
            include_memory=request.include_memory,
            include_knowledge_base=request.include_knowledge_base
        )

        # Store workflow
        workflow_id = str(uuid.uuid4())
        workflow["id"] = workflow_id
        workflow["created_at"] = datetime.now().isoformat()

        # Ensure suggested_tools is a list of strings
        suggested_tools_list = workflow.get("suggested_tools", [])
        if suggested_tools_list:
            if isinstance(suggested_tools_list, list) and len(suggested_tools_list) > 0:
                first_item = suggested_tools_list[0]
                if hasattr(first_item, 'name'):
                    suggested_tools_list = [t.name for t in suggested_tools_list]

        workflow["suggested_tools"] = suggested_tools_list

        # Save to memory (in POC, later use database)
        app.state.workflows = getattr(app.state, 'workflows', {})
        app.state.workflows[workflow_id] = workflow

        return WorkflowGenerationResponse(
            workflow_id=workflow_id,
            name=workflow.get("name", "Untitled Workflow"),
            description=workflow.get("description", ""),
            schema=workflow.get("schema", {}),
            suggested_tools=suggested_tools_list,
            created_at=workflow["created_at"]
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow details"""
    workflows = getattr(app.state, 'workflows', {})
    if workflow_id not in workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return workflows[workflow_id]

@app.put("/workflows/{workflow_id}/agents/{agent_name}")
async def update_agent(workflow_id: str, agent_name: str, request: AgentUpdateRequest):
    """Update an agent in the workflow"""
    try:
        workflows = getattr(app.state, 'workflows', {})
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow = workflows[workflow_id]
        updated_workflow = workflow_editor.update_agent(
            workflow=workflow,
            agent_name=agent_name,
            updates=request.dict(exclude_unset=True)
        )

        app.state.workflows[workflow_id] = updated_workflow
        return {"status": "success", "workflow": updated_workflow}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/workflows/{workflow_id}/agents/{agent_name}")
async def delete_agent(workflow_id: str, agent_name: str):
    """Delete an agent from the workflow"""
    try:
        workflows = getattr(app.state, 'workflows', {})
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow = workflows[workflow_id]
        updated_workflow = workflow_editor.delete_agent(
            workflow=workflow,
            agent_name=agent_name
        )

        app.state.workflows[workflow_id] = updated_workflow
        return {"status": "success", "workflow": updated_workflow}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/workflows/{workflow_id}/tools")
async def add_tool(workflow_id: str, request: ToolUpdateRequest):
    """Add a tool to the workflow"""
    try:
        workflows = getattr(app.state, 'workflows', {})
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow = workflows[workflow_id]
        updated_workflow = workflow_editor.add_tool(
            workflow=workflow,
            tool_name=request.name,
            tool_source=request.source,
            tool_description=request.description,
            endpoint=request.endpoint
        )

        app.state.workflows[workflow_id] = updated_workflow
        return {"status": "success", "workflow": updated_workflow}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/workflows/{workflow_id}/tools/{tool_name}")
async def delete_tool(workflow_id: str, tool_name: str):
    """Delete a tool from the workflow"""
    try:
        workflows = getattr(app.state, 'workflows', {})
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow = workflows[workflow_id]
        updated_workflow = workflow_editor.delete_tool(
            workflow=workflow,
            tool_name=tool_name
        )

        app.state.workflows[workflow_id] = updated_workflow
        return {"status": "success", "workflow": updated_workflow}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/tools/available")
async def get_available_tools():
    """Get all available tools from registries"""
    aws_tools = tool_registry.get_aws_bedrock_tools()
    custom_tools = tool_registry.get_custom_tools()

    return {
        "aws_bedrock": [
            {
                "name": t.get("name"),
                "description": t.get("description"),
                "tags": t.get("tags", [])
            } for t in aws_tools
        ],
        "custom": custom_tools
    }

@app.post("/workflows/{workflow_id}/deploy", response_model=Dict[str, Any])
async def deploy_workflow(workflow_id: str, request: WorkflowDeploymentRequest):
    """
    Deploy workflow to AgentCore Runtime

    Steps:
    1. Convert workflow schema to LangGraph code
    2. Create Docker image
    3. Push to ECR
    4. Deploy to AgentCore Runtime
    """
    try:
        workflows = getattr(app.state, 'workflows', {})
        if workflow_id not in workflows:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow = workflows[workflow_id]

        # Deploy workflow
        deployment_result = await deployment_manager.deploy(
            workflow=workflow,
            deployment_name=request.deployment_name,
            runtime=request.runtime,
            credentials=request.aws_credentials
        )

        # Store deployment
        app.state.deployments = getattr(app.state, 'deployments', {})
        deployment_id = deployment_result.get("deployment_id")
        app.state.deployments[deployment_id] = deployment_result

        # Wire save_agent() into the deploy endpoint for V3 chat UI
        agent_runtime_arn = deployment_result.get("agentRuntimeArn")
        if agent_runtime_arn:
            agent_record = save_agent(
                name=request.deployment_name,
                prompt=workflow.get("description", workflow.get("name", "")),
                agent_arn=agent_runtime_arn,
                agent_runtime_endpoint=deployment_result.get("agentRuntimeEndpoint", ""),
                image_uri=deployment_result.get("imageUri", ""),
                region=AWS_REGION,
                tools=workflow.get("suggested_tools", [])
            )
            deployment_result["agent_id"] = agent_record["agent_id"]

        return {
            "status": "success",
            "deployment_id": deployment_id,
            "agentRuntimeArn": agent_runtime_arn,
            "agent_id": deployment_result.get("agent_id"),
            "message": f"Workflow deployed to {request.runtime} runtime",
            "details": deployment_result
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/deployments/{deployment_id}")
async def get_deployment(deployment_id: str):
    """Get deployment status"""
    deployments = getattr(app.state, 'deployments', {})
    if deployment_id not in deployments:
        raise HTTPException(status_code=404, detail="Deployment not found")

    return deployments[deployment_id]

@app.post("/deployments/{deployment_id}/execute")
async def execute_workflow(deployment_id: str, request: WorkflowExecutionRequest):
    """Execute a deployed workflow"""
    try:
        deployments = getattr(app.state, 'deployments', {})
        if deployment_id not in deployments:
            raise HTTPException(status_code=404, detail="Deployment not found")

        deployment = deployments[deployment_id]

        # Execute workflow
        execution_result = await deployment_manager.execute(
            deployment_id=deployment_id,
            input_data=request.input_data
        )

        return {
            "status": "success",
            "execution_id": str(uuid.uuid4()),
            "result": execution_result
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/deployments/test")
async def test_deployed_agent(request: Dict[str, Any]):
    """Test a deployed agent in AWS Bedrock"""
    try:
        agent_id = request.get("agent_id")
        user_input = request.get("user_input")
        agent_name = request.get("agent_name", "Unknown")

        if not agent_id or not user_input:
            raise HTTPException(status_code=400, detail="agent_id and user_input are required")

        # Create a temporary deployment entry
        temp_deployment_id = f"test-{str(uuid.uuid4())[:8]}"
        temp_deployment = {
            "agent_id": agent_id,
            "deployment_id": temp_deployment_id,
            "deployment_name": agent_name
        }

        # Store temporarily
        app.state.deployments = getattr(app.state, 'deployments', {})
        app.state.deployments[temp_deployment_id] = temp_deployment

        # Execute the agent
        execution_result = await deployment_manager.execute(
            deployment_id=temp_deployment_id,
            input_data={"user_input": user_input}
        )

        return {
            "status": "success",
            "data": execution_result
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Blueprint POC API",
        "version": "0.1.0"
    }

# ============================================================================
# V3 Chat & Agent UI Endpoints
# ============================================================================

@app.get("/app-api-config.js")
def app_api_config_js():
    """Expose APP_API_KEY to the same-origin UI without hardcoding it in static files."""
    key = os.getenv("APP_API_KEY") or ""
    return PlainTextResponse(
        f"window.__APP_API_KEY__ = {json.dumps(key)};",
        media_type="application/javascript",
    )

@app.get("/")
def serve_ui():
    """Serve the React UI"""
    return FileResponse("static/index.html")

@app.get("/agents", dependencies=[Depends(verify_api_key)])
def get_agents():
    """List all deployed agents"""
    return {"agents": list_agents()}

class ChatMessage(BaseModel):
    """Chat message request"""
    message: str
    session_id: Optional[str] = None

@app.post("/chat/{agent_id}/message", dependencies=[Depends(verify_api_key)])
def chat(agent_id: str, body: ChatMessage):
    """Send a message to an agent and get a reply"""
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    session_id = get_or_create_session(agent_id, body.session_id)
    reply = send_message(
        agent_arn=agent["agent_arn"],
        agent_id=agent_id,
        session_id=session_id,
        user_message=body.message,
        region=agent["region"]
    )
    return {"reply": reply, "session_id": session_id}

@app.get("/chat/{agent_id}/history", dependencies=[Depends(verify_api_key)])
def history(agent_id: str, session_id: str):
    """Get conversation history for a session"""
    return {"history": get_history(agent_id, session_id)}

@app.delete("/chat/{agent_id}/session", dependencies=[Depends(verify_api_key)])
def reset_session(agent_id: str, session_id: str):
    """Clear/reset a conversation session"""
    clear_session(agent_id, session_id)
    return {"status": "cleared"}

# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    if not os.getenv("APP_API_KEY"):
        print("[WARN] APP_API_KEY is not set; /agents and /chat/* accept requests without a valid key.")
    await tool_registry.init_aws_bedrock_tools(
        region=AWS_REGION,
        account_id=AWS_ACCOUNT_ID
    )
    print("[OK] AWS Bedrock tools loaded")

    # Initialize state
    app.state.workflows = {}
    app.state.deployments = {}

    print("[OK] Blueprint POC API ready!")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
