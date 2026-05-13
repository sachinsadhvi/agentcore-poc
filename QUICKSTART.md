# Blueprint POC - Quick Start Guide

Get the POC running in 5 minutes!

## 1️⃣ Prerequisites

Ensure you have:
- ✅ Python 3.11+
- ✅ Anthropic API Key (Claude Opus)
- ✅ Docker (for final deployment step)
- ✅ AWS Account (for ECR - optional for this POC)

## 2️⃣ Install Dependencies

```bash
# Navigate to blueprint-poc directory
cd blueprint-poc

# Create virtual environment
python -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 3️⃣ Set Environment Variables

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional: Set AWS details (for ECR push)
export AWS_DEFAULT_REGION="us-east-1"
export AWS_ACCOUNT_ID="677276078734"
```

**On Windows PowerShell:**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:AWS_ACCOUNT_ID = "677276078734"
```

## 4️⃣ Start the Backend API

**Terminal 1:**
```bash
python main.py
```

You should see:
```
✅ AWS Bedrock tools loaded
✅ Blueprint POC API ready!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 5️⃣ Run the Demo

**Terminal 2:**
```bash
python test_poc.py
```

Watch the demo:
1. 📝 Generate workflow from natural language
2. 🛠️ View available tools (AWS Bedrock, custom, MCP)
3. 🔧 Edit workflow (update agents, add tools)
4. 🚀 Deploy to AgentCore Runtime
5. ⚙️ Execute the workflow

## 📊 What You'll See

```
╔════════════════════════════════════════════════════════════════════════════╗
║                    BLUEPRINT POC - DEMO CLIENT                             ║
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
   Suggested Tools: aws-kb-server, aws-pricing, web-search

======================================================================
🛠️  AVAILABLE TOOLS
======================================================================
AWS Bedrock Tools: 5
  - aws-kb-server: Query AWS knowledge base for service information...
  - aws-pricing: Get current AWS service pricing...
  - aws-compliance-checker: Check AWS services for compliance...

======================================================================
🔧 UPDATING AGENT: Requirements Analyzer
======================================================================
Updates: {
  "role": "Enhanced Requirements Analyzer",
  "instructions": "Analyze requirements with improved error handling...",
  "temperature": 0.5
}

✅ Agent updated successfully!

... (more steps) ...

✅ POC DEMO COMPLETED SUCCESSFULLY
```

## 🧪 Manual Testing

### Generate a Workflow

```bash
curl -X POST http://localhost:8000/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a workflow that analyzes customer feedback, identifies trends, and generates reports",
    "auto_suggest_tools": true,
    "include_memory": true,
    "include_knowledge_base": true
  }'
```

### Update an Agent

```bash
# First, get a workflow_id from the generate step above
export WORKFLOW_ID="your-workflow-id"

curl -X PUT http://localhost:8000/workflows/$WORKFLOW_ID/agents/Analyzer \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Advanced Analyzer",
    "temperature": 0.3
  }'
```

### Add a Custom Tool

```bash
curl -X POST http://localhost:8000/workflows/$WORKFLOW_ID/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sentiment-analyzer",
    "source": "custom",
    "description": "Analyze sentiment in customer feedback",
    "endpoint": "https://api.example.com/sentiment"
  }'
```

### Deploy Workflow

```bash
curl -X POST http://localhost:8000/workflows/$WORKFLOW_ID/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "Customer Feedback Analyzer",
    "runtime": "agentcore"
  }'
```

Response:
```json
{
  "status": "success",
  "deployment_id": "deploy-abc123",
  "image_uri": "677276078734.dkr.ecr.us-east-1.amazonaws.com/customer-feedback-analyzer:latest",
  ...
}
```

### Execute Workflow

```bash
export DEPLOYMENT_ID="deploy-abc123"

curl -X POST http://localhost:8000/deployments/$DEPLOYMENT_ID/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "feedback_text": "Great product but customer service was slow",
      "customer_id": "cust-123"
    }
  }'
```

## 📖 Example Prompts

Try these prompts in the demo or API:

### 1. AWS Architecture Design
```
Create a workflow that designs AWS architectures. 
The workflow should analyze requirements, select optimal AWS services, 
design the architecture, analyze costs, and generate an executive report. 
Use AWS Bedrock tools for knowledge and pricing.
```

### 2. Data Processing Pipeline
```
Build a workflow that processes customer data.
It should validate data quality, transform formats, 
enrich with external data, and output results.
Include quality metrics and error handling.
```

### 3. Content Analysis
```
Create a workflow that analyzes and classifies content.
The workflow should extract key information, 
perform sentiment analysis, tag with categories, 
and generate a summary report.
```

### 4. Code Review Assistant
```
Build a workflow that performs code reviews.
It should analyze code quality, check for security issues,
suggest optimizations, and generate a detailed report with recommendations.
```

## 🔧 Troubleshooting

### API Connection Error
```
Error: Failed to connect to http://localhost:8000
```
**Solution:** Make sure the API server is running in Terminal 1

### Anthropic API Error
```
Error: Anthropic API key not set
```
**Solution:** Check your ANTHROPIC_API_KEY environment variable:
```bash
echo $ANTHROPIC_API_KEY  # Should print your key
```

### Port Already in Use
```
ERROR: Application startup failed: Address already in use
```
**Solution:** Kill the process using port 8000:
```bash
# macOS/Linux
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Module Not Found
```
ModuleNotFoundError: No module named 'fastapi'
```
**Solution:** Reinstall dependencies:
```bash
pip install -r requirements.txt
```

## 📚 Next Steps

After running the POC:

1. **Explore the API** - Try different prompts and workflows
2. **Edit Workflows** - Modify agents, tools, and execution flow
3. **Deploy to AgentCore** - Push Docker image to ECR and deploy
4. **Add Custom Tools** - Integrate your own tools and APIs
5. **Build Frontend** - Create a UI for non-technical users

## 🚀 Advanced: Deploy to AgentCore Runtime

After generating and editing a workflow, deploy it:

```bash
# Deploy
curl -X POST http://localhost:8000/workflows/$WORKFLOW_ID/deploy \
  -H "Content-Type: application/json" \
  -d '{"deployment_name": "My Workflow", "runtime": "agentcore"}'

# Response includes:
# - deployment_id: Unique deployment ID
# - image_uri: Docker image location in ECR
# - Docker commands to push the image
```

**Push Docker Image to ECR:**

```bash
# Login to ECR (using your AWS credentials)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 677276078734.dkr.ecr.us-east-1.amazonaws.com

# Push the image
docker push 677276078734.dkr.ecr.us-east-1.amazonaws.com/my-workflow:latest
```

**Deploy to AgentCore Runtime** (via AWS Console or CLI):
- Use the image URI from the deployment response
- Configure runtime settings
- Deploy!

## 📞 Help & Support

- Check the [README.md](README.md) for detailed documentation
- Review the demo client in [test_poc.py](test_poc.py) for API usage examples
- Check CloudWatch logs for deployment/execution errors

## ✅ Success!

You've successfully:
- ✅ Generated workflows from natural language
- ✅ Edited and modified workflows
- ✅ Deployed workflows to Docker
- ✅ Prepared for AgentCore Runtime deployment

**Next:** Integrate with your own applications or deploy to production! 🚀
