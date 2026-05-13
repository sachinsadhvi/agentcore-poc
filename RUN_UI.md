# Running the Blueprint POC Streamlit UI

Complete web interface for the Blueprint workflow builder.

## Setup (First Time)

```bash
# Navigate to blueprint-poc directory
cd blueprint-poc

# Install dependencies (including new streamlit)
pip install -r requirements.txt

# Set your API key
# Windows PowerShell:
$env:ANTHROPIC_API_KEY = "sk-ant-YOUR_KEY_HERE"

# macOS/Linux:
export ANTHROPIC_API_KEY="sk-ant-YOUR_KEY_HERE"
```

Get your API key from: https://console.anthropic.com/api_keys

## Running the System

### Terminal 1 - Start the FastAPI Backend
```bash
cd blueprint-poc
python main.py
```

Wait for output:
```
✅ AWS Bedrock tools loaded
✅ Blueprint POC API ready!
```

### Terminal 2 - Start the Streamlit UI
```bash
cd blueprint-poc
streamlit run ui.py
```

The app will open automatically in your browser at: **http://localhost:8501**

## Using the UI

### 1. Home
Dashboard with feature overview and quick links to all capabilities.

### 2. Generate Workflow
- **Input**: Natural language description of your workflow
- **Options**: 
  - Auto-suggest tools (enabled by default)
  - Include memory (enabled by default)
  - Include knowledge base (enabled by default)
- **Output**: Full workflow schema with agents, tools, and execution flow

**Try this prompt:**
```
Create a workflow that analyzes AWS architecture requirements, 
selects optimal services, designs the architecture, analyzes costs, 
and generates an executive report. Include AWS Bedrock tools.
```

### 3. Edit Workflow
Two tabs:

**Agents Tab:**
- Modify agent name, role, instructions
- Adjust temperature (creativity level)
- View assigned tools
- Update agent configuration

**Tools Tab:**
- View available AWS Bedrock tools
- Add custom tools with endpoints
- Browse custom and MCP tools

### 4. Tools Browser
Browse all available tools organized by source:
- **AWS Bedrock**: aws-kb-server, aws-pricing, compliance checker, performance analyzer, web-search
- **Custom**: User-defined tools with custom endpoints
- **MCP**: Model Context Protocol servers

### 5. Deploy Workflow
- Enter deployment name
- Select target runtime (agentcore, flotorch, or langgraph)
- Get Docker image URI
- Ready to push to AWS ECR

### 6. Execute Workflow
- Enter user input
- Add optional JSON parameters
- Run the workflow
- View execution results and duration

## Complete Workflow Example

1. **Generate**: Paste natural language prompt → click "Generate Workflow"
2. **Review**: Check the generated schema and suggested tools
3. **Edit**: Modify agents, add/remove tools, adjust parameters
4. **Deploy**: Name your deployment and click "Deploy"
5. **Execute**: Provide input and run the workflow
6. **Results**: View execution output and duration

## Troubleshooting

### Can't connect to API
- Verify FastAPI backend is running on Terminal 1
- Check http://localhost:8000/health (should return 200)

### API key error
- Make sure `ANTHROPIC_API_KEY` environment variable is set
- Key should start with `sk-ant-`

### Streamlit won't start
- Make sure streamlit is installed: `pip install -r requirements.txt`
- Try: `streamlit run ui.py --logger.level=debug`

### Workflow generation is slow
- First generation takes longer (LLM processing)
- Subsequent operations are faster

## Architecture

```
Browser (Port 8501)
    ↓
Streamlit UI (ui.py)
    ↓
FastAPI Backend (Port 8000)
    ├─ Workflow Generator (Claude Haiku 4.5)
    ├─ Tool Registry (AWS Bedrock + Custom)
    ├─ Workflow Editor
    ├─ Deployment Manager
    └─ Execution Engine
```

## Files Used

- `ui.py` - Streamlit web interface
- `main.py` - FastAPI backend
- `workflow_generator.py` - LLM-powered generation
- `tool_registry.py` - Tool management
- `workflow_editor.py` - Edit workflows
- `deployment_manager.py` - Deploy to Docker/ECR
- `.env` - Your configuration (don't commit!)

---

**Start the backend and UI, then open http://localhost:8501 to begin building workflows!**
