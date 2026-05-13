# Blueprint POC - Workflow Generation & Deployment

A Proof of Concept system that converts natural language prompts into executable agentic workflows and deploys them to AWS AgentCore Runtime.

## Architecture Overview

```
User Input (Natural Language)
    ↓
[Workflow Generator Agent] (Claude Opus)
    ↓
[Workflow Schema] (JSON)
    ↓
[Workflow Editor] (Edit/Update/Delete agents & tools)
    ↓
[Deployment Manager]
    ├─ Convert to LangGraph code
    ├─ Create Docker image
    ├─ Push to ECR
    └─ Deploy to AgentCore Runtime
    ↓
[Execution] (Run workflow)
```

## Features

✅ **Natural Language to Workflow**: Convert user prompts to structured workflows  
✅ **Tool Registry**: AWS Bedrock tools, MCP servers, custom tools  
✅ **Workflow Editor**: Edit agents, add/delete tools, modify execution flow  
✅ **Auto Tool Suggestion**: LLM-powered tool recommendations  
✅ **Memory & Knowledge Base**: Built-in support for state and knowledge bases  
✅ **Docker Deployment**: Automated Docker image creation  
✅ **ECR Integration**: Push to AWS ECR for AgentCore Runtime  
✅ **Multi-Runtime Support**: Deploy to AgentCore, Flotorch, or LangGraph  

## Setup

### Prerequisites

- Python 3.11+
- Docker (for building/pushing images)
- AWS Account with ECR access
- Anthropic API key (Claude Haiku 4.5)

### Installation

1. **Clone/Create the Blueprint POC directory**:
```bash
mkdir blueprint-poc
cd blueprint-poc
```

2. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Set environment variables**:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
export AWS_DEFAULT_REGION="us-east-1"
export AWS_ACCOUNT_ID="677276078734"
```

## Running the POC

### Step 1: Start the Backend API

```bash
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
✅ Blueprint POC API ready!
```

### Step 2: Run the Demo Client

In another terminal:

```bash
python test_poc.py
```

This will:
1. **Generate** a workflow from natural language
2. **View** available AWS Bedrock tools
3. **Edit** the workflow (update agents, add tools)
4. **Deploy** to AgentCore Runtime (generates Docker image)
5. **Execute** the workflow

Expected output:
```
╔════════════════════════════════════════════════════════════════════════════╗
║                    BLUEPRINT POC - DEMO CLIENT                             ║
║                                                                            ║
║ This script demonstrates:                                                 ║
║ 1. Generate workflow from natural language                               ║
║ 2. View available tools (AWS Bedrock, custom, MCP)                       ║
║ 3. Edit workflow (update agents, add/delete tools)                       ║
║ 4. Deploy workflow to AgentCore Runtime                                  ║
║ 5. Execute deployed workflow                                             ║
╚════════════════════════════════════════════════════════════════════════════╝

⏳ Waiting for API to be ready...
✅ API is ready!

======================================================================
📝 GENERATING WORKFLOW
======================================================================
Prompt: Create an AWS architecture design workflow...

✅ Workflow generated successfully!
   Workflow ID: 9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d
   Name: AWS Architecture Design & TCO Workflow
   Description: A comprehensive workflow that analyzes requirements, selects optimal AWS services, designs architectures, analyzes costs, and generates executive reports.
   Suggested Tools: aws-kb-server, aws-pricing, web-search

... (workflow schema shown) ...

... (more steps) ...

✅ POC DEMO COMPLETED SUCCESSFULLY
```

## API Endpoints

### Workflow Generation

**POST `/workflows/generate`**
```bash
curl -X POST http://localhost:8000/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create an AWS architecture design workflow",
    "auto_suggest_tools": true,
    "include_memory": true,
    "include_knowledge_base": true
  }'
```

Response:
```json
{
  "workflow_id": "unique-id",
  "name": "Workflow Name",
  "description": "...",
  "schema": { ... },
  "suggested_tools": ["aws-kb-server", "aws-pricing"],
  "created_at": "2024-01-01T12:00:00"
}
```

### Get Available Tools

**GET `/tools/available`**
```bash
curl http://localhost:8000/tools/available
```

Response:
```json
{
  "aws_bedrock": [
    {
      "name": "aws-kb-server",
      "description": "Query AWS knowledge base...",
      "tags": ["aws", "knowledge", "architecture"]
    },
    ...
  ],
  "custom": [...]
}
```

### Update Agent

**PUT `/workflows/{workflow_id}/agents/{agent_name}`**
```bash
curl -X PUT http://localhost:8000/workflows/workflow-id/agents/RequirementsAnalyzer \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Enhanced Requirements Analyzer",
    "instructions": "New instructions...",
    "temperature": 0.5
  }'
```

### Add Tool

**POST `/workflows/{workflow_id}/tools`**
```bash
curl -X POST http://localhost:8000/workflows/workflow-id/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "custom-tool",
    "source": "custom",
    "description": "My custom tool",
    "endpoint": "https://api.example.com/tool"
  }'
```

### Deploy Workflow

**POST `/workflows/{workflow_id}/deploy`**
```bash
curl -X POST http://localhost:8000/workflows/workflow-id/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "My AWS Workflow",
    "runtime": "agentcore"
  }'
```

Response:
```json
{
  "status": "success",
  "deployment_id": "deploy-12345",
  "message": "Workflow deployed to agentcore runtime",
  "details": {
    "image_uri": "677276078734.dkr.ecr.us-east-1.amazonaws.com/my-aws-workflow:latest",
    ...
  }
}
```

### Execute Workflow

**POST `/deployments/{deployment_id}/execute`**
```bash
curl -X POST http://localhost:8000/deployments/deploy-12345/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "user_input": "Design an e-commerce platform",
      "max_budget": 50000
    }
  }'
```

## File Structure

```
blueprint-poc/
├── main.py                    # FastAPI server
├── workflow_generator.py       # LLM-powered workflow generation
├── tool_registry.py           # Tool management (AWS, MCP, custom)
├── workflow_editor.py         # Edit/update workflows
├── deployment_manager.py      # Docker build & AgentCore deployment
├── test_poc.py               # Demo client
├── requirements.txt          # Python dependencies
└── README.md                # This file
```

## Workflow Schema Example

```json
{
  "name": "AWS Architecture Design Workflow",
  "description": "Design AWS architectures with service selection and cost analysis",
  "version": "1.0",
  "suggested_tools": ["aws-kb-server", "aws-pricing"],
  "schema": {
    "memory": {
      "type": "short-term",
      "storage": "in-memory",
      "ttl": 3600
    },
    "knowledge_base": {
      "enabled": true,
      "sources": ["aws-bedrock"]
    },
    "agents": [
      {
        "id": "agent-analyzer",
        "name": "Requirements Analyzer",
        "role": "Analyze user requirements",
        "model": "claude-opus-4-1",
        "instructions": "Parse and structure user requirements...",
        "tools": ["aws-kb-server"],
        "temperature": 0.7
      },
      {
        "id": "agent-selector",
        "name": "Service Selector",
        "role": "Select optimal AWS services",
        "model": "claude-opus-4-1",
        "instructions": "Map requirements to AWS services...",
        "tools": ["aws-kb-server", "aws-pricing"],
        "temperature": 0.5
      }
    ],
    "workflow": {
      "type": "dag",
      "execution_mode": "serial",
      "nodes": [
        {
          "id": "analyze-requirements",
          "type": "task",
          "agent_id": "agent-analyzer",
          "instruction": "Analyze and structure requirements",
          "depends_on": [],
          "timeout": 300
        },
        {
          "id": "select-services",
          "type": "task",
          "agent_id": "agent-selector",
          "instruction": "Select optimal services",
          "depends_on": ["analyze-requirements"],
          "timeout": 300
        },
        {
          "id": "human-review",
          "type": "human-in-loop",
          "instruction": "Review architecture design",
          "depends_on": ["select-services"],
          "timeout": 3600
        }
      ]
    },
    "state": {
      "user_input": "string",
      "requirements": "object",
      "selected_services": "array",
      "human_approval": "boolean"
    }
  }
}
```

## Deployment to AgentCore Runtime

When you deploy a workflow:

1. **LangGraph Code Generated**: The workflow schema is converted to LangGraph Python code
2. **Docker Image Created**: A Docker image is built with all dependencies
3. **Dockerfile Generated**: Uses AWS Lambda Python 3.12 base image
4. **ECR Push**: Image is pushed to your AWS ECR registry
5. **AgentCore Runtime**: The workflow is registered as an AgentCore Runtime endpoint

### Manual ECR Push (if needed)

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 677276078734.dkr.ecr.us-east-1.amazonaws.com

# Push image
docker push 677276078734.dkr.ecr.us-east-1.amazonaws.com/my-workflow:latest

# View in console
aws ecr describe-images --repository-name my-workflow
```

## Advanced Features

### Parallel Execution

Define parallel nodes in the workflow schema:
```json
{
  "parallel_groups": [
    ["analyze-requirements"],
    ["select-services", "estimate-cost"],  // Run in parallel
    ["generate-report"]
  ]
}
```

### Conditional Logic

```json
{
  "conditions": [
    {
      "id": "check-approval",
      "type": "if-then-else",
      "condition": "human_review.approved == true",
      "then": ["cost-analysis"],
      "else": ["design-revision"]
    }
  ]
}
```

### Human-in-the-Loop

```json
{
  "id": "human-review",
  "type": "human-in-loop",
  "prompt": "Do you approve this design?",
  "required": true,
  "timeout": 3600
}
```

### Custom Tools

Register custom tools via API:
```bash
curl -X POST http://localhost:8000/workflows/workflow-id/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-compliance-checker",
    "source": "custom",
    "description": "Validate compliance requirements",
    "endpoint": "https://internal-api/compliance"
  }'
```

## Troubleshooting

### API Won't Start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill the process if needed
kill -9 <PID>
```

### Workflow Generation Fails
- Check ANTHROPIC_API_KEY is set
- Verify Claude Opus model is available
- Check API rate limits

### Docker Build Fails
- Ensure Docker daemon is running
- Check disk space
- Verify Dockerfile syntax

## Future Enhancements

- [ ] Frontend UI for workflow builder
- [ ] Database persistence (PostgreSQL, DynamoDB)
- [ ] Workflow versioning and rollback
- [ ] Real AgentCore Runtime API integration
- [ ] Flotorch deployment support
- [ ] MCP server discovery
- [ ] Workflow marketplace/sharing
- [ ] Advanced monitoring & observability
- [ ] Cost optimization recommendations
- [ ] A/B testing support

## License

MIT

## Support

For issues or questions, please reach out to the development team.
