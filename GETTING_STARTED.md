# 🚀 Blueprint POC - Getting Started

Congratulations! You now have a complete **Proof of Concept** system for generating agentic workflows from natural language and deploying them to AWS AgentCore Runtime.

## 📦 What You Have

A production-ready POC with:
- ✅ **FastAPI Backend** - REST API with 13 endpoints
- ✅ **Workflow Generator** - LLM-powered workflow creation using Claude Opus
- ✅ **Tool Registry** - AWS Bedrock tools, custom tools, MCP servers
- ✅ **Workflow Editor** - Edit, update, delete agents and tools
- ✅ **Deployment Manager** - Convert to LangGraph, build Docker, push to ECR
- ✅ **Demo Client** - Complete end-to-end demonstration
- ✅ **Documentation** - README, QuickStart, API docs

## ⚡ Quick Start (5 Minutes)

### 1. Install
```bash
cd blueprint-poc
pip install -r requirements.txt
```

### 2. Set API Key
```bash
# macOS/Linux
export ANTHROPIC_API_KEY="sk-ant-YOUR_KEY_HERE"

# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-YOUR_KEY_HERE"
```

Get your key from: https://console.anthropic.com/api_keys

### 3. Start API (Terminal 1)
```bash
python main.py
```

Wait for:
```
✅ AWS Bedrock tools loaded
✅ Blueprint POC API ready!
```

### 4. Run Demo (Terminal 2)
```bash
python test_poc.py
```

Watch the magic happen! ✨

## 📖 Documentation

- **[README.md](README.md)** - Complete technical documentation
- **[QUICKSTART.md](QUICKSTART.md)** - 5-minute setup guide
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - What was built
- **.env.example** - Environment variables template

## 🧪 Test the API Yourself

### Generate a Workflow
```bash
curl -X POST http://localhost:8000/workflows/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a workflow that analyzes AWS architecture requirements and recommends services",
    "auto_suggest_tools": true
  }'
```

### Get Available Tools
```bash
curl http://localhost:8000/tools/available
```

### Update an Agent
```bash
curl -X PUT http://localhost:8000/workflows/{workflow_id}/agents/Analyzer \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Advanced Analyzer",
    "temperature": 0.3
  }'
```

### Add a Custom Tool
```bash
curl -X POST http://localhost:8000/workflows/{workflow_id}/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-custom-tool",
    "source": "custom",
    "description": "My custom tool",
    "endpoint": "https://api.example.com/tool"
  }'
```

### Deploy Workflow
```bash
curl -X POST http://localhost:8000/workflows/{workflow_id}/deploy \
  -H "Content-Type: application/json" \
  -d '{
    "deployment_name": "My Workflow",
    "runtime": "agentcore"
  }'
```

## 🎯 Key Features

### 🤖 Intelligent Workflow Generation
- **Input**: Natural language prompt
- **Process**: Claude Opus analyzes and creates structured workflow
- **Output**: JSON workflow schema with agents, tools, and execution flow

### 🛠️ Complete Workflow Editor
- Edit agent names, roles, instructions
- Add/remove agents
- Manage tools (AWS Bedrock, custom, MCP)
- Modify execution flow
- Real-time validation

### 🔧 AWS Bedrock Tool Integration
Out of the box, you get access to:
1. **aws-kb-server** - AWS knowledge base queries
2. **aws-pricing** - Service pricing information
3. **aws-compliance-checker** - Compliance validation
4. **aws-performance-analyzer** - Performance metrics
5. **web-search** - Web search capability

### 🚀 One-Click Deployment
- Converts workflow to LangGraph code
- Generates Dockerfile
- Builds Docker image
- Pushes to AWS ECR
- Ready for AgentCore Runtime

## 💡 Example Prompts

Try these natural language prompts:

### 1. AWS Architecture Design
```
Create a workflow that designs AWS architectures. 
The workflow should analyze requirements, select optimal AWS services, 
design the architecture, analyze costs, and generate an executive report.
```

### 2. Data Analysis Pipeline
```
Build a workflow that processes and analyzes customer data.
It should validate data quality, identify patterns, 
generate insights, and create summary reports.
```

### 3. Content Processing
```
Create a workflow that processes content.
It should extract information, perform sentiment analysis, 
categorize content, and generate summaries.
```

### 4. Code Review Assistant
```
Build a workflow that reviews code quality.
It should check for bugs, security issues, 
performance problems, and suggest improvements.
```

## 🔍 Understanding the Flow

```
1. User Input (Natural Language)
   ↓
2. Workflow Generator (Claude Opus)
   ↓
3. Workflow Schema (JSON)
   ↓
4. Workflow Editor (User makes changes)
   ↓
5. Deployment Manager
   ├─ Convert to LangGraph
   ├─ Generate Dockerfile
   ├─ Build Docker Image
   └─ Push to ECR
   ↓
6. AgentCore Runtime
   ↓
7. Execution & Results
```

## 📊 File Structure

```
blueprint-poc/
├── main.py                      # FastAPI REST API
├── workflow_generator.py        # LLM-based workflow generation
├── tool_registry.py            # Tool management
├── workflow_editor.py          # Edit/modify workflows
├── deployment_manager.py       # Deploy to ECR/AgentCore
├── test_poc.py                # Demo client
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── README.md                 # Technical docs
├── QUICKSTART.md            # Setup guide
├── GETTING_STARTED.md       # This file
└── IMPLEMENTATION_SUMMARY.md # What was built
```

## 🔐 Security Notes

This is a POC, so it has these security considerations:

**Current State:**
- No authentication on API endpoints
- Credentials in environment variables
- In-memory workflow storage
- Simulated ECR push

**For Production, Add:**
- API authentication (JWT/OAuth)
- Database encryption
- Secrets Manager
- VPC isolation
- CloudTrail logging
- Input validation

## 🎓 Learning Resources

### Understand the Components
1. Start with **QUICKSTART.md** (5 min setup)
2. Run **test_poc.py** (see it in action)
3. Read **README.md** (technical details)
4. Explore **main.py** (API implementation)
5. Check **workflow_generator.py** (LLM integration)

### Try Different Workflows
1. Generate a basic workflow
2. Edit the agents
3. Add custom tools
4. Deploy to Docker
5. Execute and see results

### Extend the System
1. Add your own tools
2. Customize prompts
3. Integrate with your APIs
4. Add database persistence
5. Build a frontend UI

## ❓ Common Questions

### Q: Why does it use Claude Haiku 4.5?
**A:** Claude Haiku 4.5 is used to intelligently generate workflows from natural language. It's fast, cost-effective, and understands context well enough to create multi-agent workflows automatically. For more complex workflows, you can switch to Claude Opus by updating the model parameter.

### Q: What are "tools"?
**A:** Tools are capabilities agents can use:
- **AWS Bedrock tools**: AWS knowledge, pricing, compliance info
- **Custom tools**: Your own APIs and services
- **MCP tools**: Model Context Protocol servers

### Q: Can I deploy to production?
**A:** Yes! The generated workflow can be deployed to:
- AWS AgentCore Runtime (primary target)
- Flotorch Runtime
- Standalone LangGraph

### Q: How do I add my own tools?
**A:** Use the API endpoint:
```bash
POST /workflows/{id}/tools
{
  "name": "my-tool",
  "source": "custom",
  "endpoint": "https://api.company.com/my-tool"
}
```

### Q: Can I edit workflows?
**A:** Yes! Full editing capabilities:
- Update agent properties
- Add/remove agents
- Add/remove tools
- Modify execution flow
- Validate changes

## 🚀 Next Steps

### Immediate (Today)
- [ ] Run the POC demo
- [ ] Try different prompts
- [ ] Edit a workflow
- [ ] Deploy to Docker

### Short Term (This Week)
- [ ] Integrate with your AWS account
- [ ] Add custom tools
- [ ] Test with real data
- [ ] Deploy to AgentCore Runtime

### Medium Term (This Month)
- [ ] Add database persistence
- [ ] Build a frontend
- [ ] Implement authentication
- [ ] Add workflow versioning
- [ ] Create workflow templates

### Long Term (Future)
- [ ] Workflow marketplace
- [ ] Advanced monitoring
- [ ] Multi-user collaboration
- [ ] Cost optimization
- [ ] Analytics dashboard

## 📞 Need Help?

1. **Setup Issues**: Check QUICKSTART.md
2. **API Questions**: See README.md
3. **Implementation Details**: Check IMPLEMENTATION_SUMMARY.md
4. **Code Examples**: Look at test_poc.py
5. **Troubleshooting**: See README.md Troubleshooting section

## 🎉 Success!

You now have a powerful system that can:
- ✅ Generate workflows from natural language
- ✅ Edit and customize workflows
- ✅ Deploy to AWS AgentCore Runtime
- ✅ Execute agentic workflows at scale

**Start with the demo, explore the API, and build your custom workflows!** 🚀

---

**Questions?** Check the documentation files or review the demo client code.

**Ready to build?** Let's go! 🎯
