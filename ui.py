"""
Blueprint POC - Streamlit Web UI
Interactive workflow builder with visual interface
"""

import streamlit as st
import httpx
import json
import time
from datetime import datetime

# Configure Streamlit
st.set_page_config(
    page_title="Blueprint POC - Workflow Builder",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE_URL = "http://localhost:8000"
TIMEOUT = 30.0

# ============================================================================
# Helper Functions
# ============================================================================

async def call_api(endpoint: str, method: str = "GET", data: dict = None):
    """Call the Blueprint API"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"{API_BASE_URL}{endpoint}"

            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=data)
            elif method == "PUT":
                response = await client.put(url, json=data)
            elif method == "DELETE":
                response = await client.delete(url)

            if response.status_code in [200, 201]:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# Page: Home/Dashboard
# ============================================================================

def page_home():
    st.title("🚀 Blueprint POC - Workflow Builder")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Generated Workflows", "0", "+0")
    with col2:
        st.metric("Deployed", "0", "+0")
    with col3:
        st.metric("Executed", "0", "+0")

    st.divider()

    st.header("Welcome to Blueprint POC!")

    st.markdown("""
    This is an interactive workflow builder that converts natural language prompts
    into executable agentic workflows.

    ### Quick Start:
    1. **Generate** - Enter a natural language prompt and AI will create a workflow
    2. **Edit** - Modify agents, add tools, adjust execution flow
    3. **Deploy** - Convert to Docker and deploy to AWS AgentCore Runtime
    4. **Execute** - Run your workflow and see results

    ### Features:
    ✅ **Natural Language to Workflow** - AI-powered workflow generation
    ✅ **AWS Bedrock Tools** - aws-kb-server, aws-pricing, compliance checking
    ✅ **Workflow Editing** - Full agent and tool management
    ✅ **Docker Deployment** - One-click deployment to AWS
    ✅ **Multi-Agent Support** - Create complex workflows with multiple agents
    """)

# ============================================================================
# Page: Generate Workflow
# ============================================================================

def page_generate():
    st.title("📝 Generate Workflow")

    st.markdown("Enter a natural language description of the workflow you want to create.")

    col1, col2 = st.columns([3, 1])

    with col1:
        prompt = st.text_area(
            "Describe your workflow",
            placeholder="""Example: Create a workflow that analyzes AWS architecture requirements,
selects optimal services, and generates a cost estimate. Include AWS Bedrock tools.""",
            height=150
        )

    with col2:
        st.markdown("### Options")
        auto_suggest = st.checkbox("Auto-suggest tools", value=True)
        include_memory = st.checkbox("Include memory", value=True)
        include_kb = st.checkbox("Include knowledge base", value=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        generate_btn = st.button("🚀 Generate Workflow", type="primary", use_container_width=True)

    if generate_btn:
        if not prompt.strip():
            st.error("Please enter a workflow description")
            return

        with st.spinner("Generating workflow... This may take a minute"):
            import asyncio

            try:
                result = asyncio.run(call_api(
                    "/workflows/generate",
                    method="POST",
                    data={
                        "prompt": prompt,
                        "auto_suggest_tools": auto_suggest,
                        "include_memory": include_memory,
                        "include_knowledge_base": include_kb
                    }
                ))

                if result["success"]:
                    workflow = result["data"]

                    # Store in session
                    st.session_state.generated_workflow = workflow
                    st.session_state.workflow_id = workflow["workflow_id"]

                    st.success("✅ Workflow generated successfully!")

                    # Display workflow details
                    st.divider()

                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader(workflow["name"])
                        st.write(workflow["description"])

                    with col2:
                        st.subheader("Suggested Tools")
                        for tool in workflow.get("suggested_tools", []):
                            st.write(f"• {tool}")

                    # Display workflow schema
                    st.subheader("Workflow Schema")
                    with st.expander("View Full Schema"):
                        st.json(workflow["schema"])

                    # Store workflow ID
                    st.session_state.workflow_id = workflow["workflow_id"]

                    st.info(f"✅ Workflow ID: `{workflow['workflow_id']}`\n\nYou can now edit this workflow or deploy it!")

                else:
                    st.error(f"Error: {result['error']}")

            except Exception as e:
                st.error(f"Error: {str(e)}")

# ============================================================================
# Page: Edit Workflow
# ============================================================================

def page_edit():
    st.title("🔧 Edit Workflow")

    if "workflow_id" not in st.session_state:
        st.warning("No workflow loaded. Please generate one first!")
        return

    workflow_id = st.session_state.workflow_id

    # Load current workflow
    import asyncio
    result = asyncio.run(call_api(f"/workflows/{workflow_id}"))

    if not result["success"]:
        st.error("Could not load workflow")
        return

    workflow = result["data"]
    schema = workflow.get("schema", {})
    agents = schema.get("agents", [])

    st.markdown(f"Editing workflow: **{workflow.get('name')}**")

    # Tabs for different editing options
    tab1, tab2, tab3 = st.tabs(["Agents", "Tools", "Preview"])

    with tab1:
        st.subheader("Agents")

        for i, agent in enumerate(agents):
            with st.expander(f"🤖 {agent.get('name')} - {agent.get('role')}", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    new_name = st.text_input(
                        f"Agent name (#{i})",
                        value=agent.get("name"),
                        key=f"agent_name_{i}"
                    )
                    new_role = st.text_area(
                        f"Role (#{i})",
                        value=agent.get("role"),
                        height=60,
                        key=f"agent_role_{i}"
                    )

                with col2:
                    new_temp = st.slider(
                        f"Temperature (#{i})",
                        0.0, 1.0,
                        value=agent.get("temperature", 0.7),
                        step=0.1,
                        key=f"agent_temp_{i}"
                    )

                    current_tools = agent.get("tools", [])
                    st.write(f"**Current Tools:** {', '.join(current_tools) if current_tools else 'None'}")

                if st.button(f"Update Agent (#{i})", key=f"update_agent_{i}"):
                    # Call API to update agent
                    update_result = asyncio.run(call_api(
                        f"/workflows/{workflow_id}/agents/{agent.get('name')}",
                        method="PUT",
                        data={
                            "name": new_name,
                            "role": new_role,
                            "temperature": new_temp
                        }
                    ))

                    if update_result["success"]:
                        st.success(f"✅ Updated agent: {new_name}")
                    else:
                        st.error(f"Error: {update_result['error']}")

    with tab2:
        st.subheader("Tools")

        col1, col2 = st.columns(2)

        with col1:
            st.write("**Add Custom Tool**")
            tool_name = st.text_input("Tool name", placeholder="my-custom-tool")
            tool_source = st.selectbox("Source", ["aws-bedrock", "custom", "mcp"])
            tool_desc = st.text_area("Description", placeholder="What does this tool do?")
            tool_endpoint = st.text_input(
                "Endpoint (for custom tools)",
                placeholder="https://api.example.com/tool"
            )

            if st.button("➕ Add Tool"):
                add_result = asyncio.run(call_api(
                    f"/workflows/{workflow_id}/tools",
                    method="POST",
                    data={
                        "name": tool_name,
                        "source": tool_source,
                        "description": tool_desc,
                        "endpoint": tool_endpoint if tool_source == "custom" else None
                    }
                ))

                if add_result["success"]:
                    st.success(f"✅ Added tool: {tool_name}")
                else:
                    st.error(f"Error: {add_result['error']}")

        with col2:
            st.write("**Available Tools**")
            tools_result = asyncio.run(call_api("/tools/available"))

            if tools_result["success"]:
                tools = tools_result["data"]

                st.markdown("**AWS Bedrock Tools**")
                for tool in tools.get("aws_bedrock", [])[:5]:
                    st.write(f"• **{tool['name']}** - {tool['description'][:50]}...")

                st.markdown("**Custom Tools**")
                for tool in tools.get("custom", [])[:3]:
                    st.write(f"• **{tool['name']}** - {tool.get('description', 'N/A')[:50]}...")

    with tab3:
        st.subheader("Workflow Preview")
        st.json(workflow)

# ============================================================================
# Page: Deploy Workflow
# ============================================================================

def page_deploy():
    st.title("🚀 Deploy Workflow")

    if "workflow_id" not in st.session_state:
        st.warning("No workflow loaded. Please generate one first!")
        return

    workflow_id = st.session_state.workflow_id

    # Load workflow details to get the name
    import asyncio
    workflow_details = asyncio.run(call_api(f"/workflows/{workflow_id}"))

    if workflow_details["success"]:
        workflow = workflow_details["data"]
        workflow_name = workflow.get("name", "Untitled Workflow")
    else:
        workflow_name = "Untitled Workflow"

    st.markdown(f"Deploying workflow: **{workflow_name}** (ID: {workflow_id[:8]}...)")

    col1, col2 = st.columns(2)

    with col1:
        deployment_name = st.text_input(
            "Deployment name",
            value=workflow_name,
            placeholder="Name for this deployment"
        )

        deployment_mode = st.radio(
            "Deployment approach",
            ["Native Bedrock Agent", "AgentCore Runtime Hosted", "Docker Container"],
            help="Native: Fast (2 min). AgentCore: Hosted (5 min). Docker: Portable (15 min)."
        )

        runtime_map = {
            "Native Bedrock Agent": "agentcore-native",
            "AgentCore Runtime Hosted": "agentcore-runtime",
            "Docker Container": "agentcore-docker"
        }
        runtime = runtime_map[deployment_mode]

        if deployment_mode == "Docker Container":
            st.selectbox(
                "Container runtime (optional)",
                ["agentcore-docker", "flotorch", "langgraph"],
                index=0,
                help="Which container orchestration platform"
            )

    with col2:
        st.markdown("### Deployment Info")
        if deployment_mode == "Native Bedrock Agent":
            st.write("""
            **Native Bedrock Agent:**
            1. Convert workflow to AgentCore schema
            2. Create Bedrock Agent directly
            3. Add action groups for tools
            4. No infrastructure needed

            **Time:** ~2 minutes
            **Cost:** Per invocation
            """)
        elif deployment_mode == "AgentCore Runtime Hosted":
            st.write("""
            **AgentCore Runtime Hosted:**
            1. Package agent code for AgentCore
            2. Upload to S3 bucket
            3. Create hosted agent in AgentCore
            4. Enterprise-grade security & scalability

            **Time:** ~5 minutes
            **Cost:** Hosting + invocation
            **Best for:** Production deployments
            """)
        else:
            st.write("""
            **Docker Container:**
            1. Convert workflow to LangGraph code
            2. Generate Dockerfile
            3. Build Docker image (arm64)
            4. Push to AWS ECR
            5. Deploy to container platform

            **Time:** ~15 minutes
            **Cost:** Container hosting
            **Best for:** Multi-cloud portability
            """)


    if st.button("🚀 Deploy Workflow", type="primary", use_container_width=True):
        with st.spinner("Deploying... This may take 2-3 minutes"):
            import asyncio

            result = asyncio.run(call_api(
                f"/workflows/{workflow_id}/deploy",
                method="POST",
                data={
                    "deployment_name": deployment_name,
                    "runtime": runtime
                }
            ))

            if result["success"]:
                deployment = result["data"]
                deployment_id = deployment.get("deployment_id", "unknown")
                st.session_state.deployment_id = deployment_id

                st.success("✅ Deployment successful!")

                st.divider()

                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("Deployment Details")
                    st.write(f"**Deployment ID:** `{deployment_id}`")
                    st.write(f"**Status:** {deployment.get('status', 'unknown')}")
                    if 'runtime' in deployment:
                        st.write(f"**Runtime:** {deployment['runtime']}")
                    if 'agent_id' in deployment:
                        st.write(f"**Agent ID:** {deployment['agent_id']}")
                    if 'aws_region' in deployment:
                        st.write(f"**Region:** {deployment['aws_region']}")

                with col2:
                    deployment_method = deployment.get("deployment_method", "unknown")

                    if deployment_method == "docker":
                        st.subheader("Docker Image")
                        image_uri = deployment.get("image_uri", "N/A")
                        if image_uri != "N/A":
                            st.code(image_uri)
                            st.markdown("**✅ Image pushed to ECR!**")
                    elif deployment_method == "agentcore-runtime":
                        st.subheader("AgentCore Runtime Setup")
                        s3_bucket = deployment.get("s3_bucket", "N/A")
                        s3_prefix = deployment.get("s3_prefix", "N/A")
                        s3_files = deployment.get("s3_files", [])

                        if s3_bucket != "N/A":
                            st.success("✅ Agent files uploaded to S3!")
                            st.write(f"**S3 Bucket:** `{s3_bucket}`")
                            st.write(f"**S3 Prefix:** `{s3_prefix}`")

                            with st.expander("View uploaded files"):
                                st.write("**Files in S3:**")
                                for file in s3_files:
                                    st.code(file)

                            st.divider()
                            st.warning("**⚠️ Manual Configuration Required in AWS Console**")
                            st.markdown(f"""
                            ### Step-by-Step Setup in AWS AgentCore Runtime:

                            #### 1. Open AgentCore Runtime Console
                            Go to: https://console.aws.amazon.com/bedrock-agentcore/agents/create

                            #### 2. Create New Agent
                            - Click **"Create Agent"** button

                            #### 3. Configure Agent
                            - **Agent Name:** `{deployment_name}`
                            - **Source Type:** Select **"S3 Source"** (NOT ECR)

                            #### 4. Select Files from S3
                            - **S3 Bucket:** Choose `{s3_bucket}`
                            - **Navigate to:** `{s3_prefix}/`
                            - **Select file:** `agent.yaml` ⭐ (NOT a ZIP file!)

                            #### 5. Complete Configuration
                            - Configure other agent settings as needed
                            - Click **"Create Agent"**
                            - ⏳ Wait 2-3 minutes for deployment

                            #### 6. Get Agent ID
                            - After deployment, copy the **Agent ID**
                            - Format: `agentcore-xxxxx` or similar

                            ### Then Test:
                            - **Option A:** Test in [AgentCore Runtime Console](https://console.aws.amazon.com/bedrock-agentcore/)
                            - **Option B:** Use **🧪 Test Agents** page in Streamlit (enter Agent ID)
                            """)

                            st.info("""
                            **Key Points:**
                            - Select `agent.yaml` (the configuration file)
                            - Do NOT try to select a ZIP file
                            - All agent files are already in S3
                            - AgentCore Runtime will read them automatically
                            """)
                    else:
                        st.subheader("Bedrock Agent")
                        st.write(f"**✅ Agent created and prepared!**")

                    if 'agent_id' in deployment:
                        st.divider()
                        st.subheader("Next Steps")
                        st.write("1. Go to **⚙️ Execute** page to test your agent")
                        st.write("2. Or go to **🧪 Test Agents** page for quick testing")
                        st.write("3. Check AWS console to view deployment details")

            else:
                st.error(f"Deployment failed: {result['error']}")

# ============================================================================
# Page: Execute Workflow
# ============================================================================

def page_execute():
    st.title("⚙️ Execute Workflow")

    if "deployment_id" not in st.session_state:
        st.warning("No deployment loaded. Please deploy a workflow first!")
        return

    deployment_id = st.session_state.deployment_id

    st.markdown(f"Executing deployment: **{deployment_id}**")

    # Input form
    st.subheader("Input Parameters")

    col1, col2 = st.columns(2)

    with col1:
        user_input = st.text_area(
            "User input",
            placeholder="Enter the input for your workflow",
            height=150
        )

    with col2:
        additional_params = st.text_area(
            "Additional parameters (JSON)",
            placeholder='{"key": "value"}',
            height=150
        )

    if st.button("▶️ Execute Workflow", type="primary", use_container_width=True):
        with st.spinner("Executing workflow..."):
            import asyncio

            try:
                input_data = {"user_input": user_input}

                if additional_params.strip():
                    input_data.update(json.loads(additional_params))

                result = asyncio.run(call_api(
                    f"/deployments/{deployment_id}/execute",
                    method="POST",
                    data={
                        "deployment_id": deployment_id,
                        "input_data": input_data
                    }
                ))

                if result["success"]:
                    execution = result["data"]

                    st.success("✅ Workflow executed successfully!")

                    st.divider()

                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("Execution Details")
                        st.write(f"**Execution ID:** `{execution['execution_id']}`")
                        st.write(f"**Status:** {execution['status']}")
                        st.write(f"**Duration:** {execution.get('execution_time_ms', 'N/A')} ms")

                    with col2:
                        st.subheader("Results")
                        st.json(execution.get("output", {}))

                else:
                    st.error(f"Execution failed: {result['error']}")

            except json.JSONDecodeError:
                st.error("Invalid JSON in additional parameters")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ============================================================================
# Page: Tools Browser
# ============================================================================

def page_tools():
    st.title("🛠️ Tools Browser")

    st.markdown("Browse all available tools from AWS Bedrock, custom, and MCP sources.")

    import asyncio
    result = asyncio.run(call_api("/tools/available"))

    if result["success"]:
        tools = result["data"]

        # Tabs for different tool sources
        tab1, tab2, tab3 = st.tabs(["AWS Bedrock", "Custom", "MCP"])

        with tab1:
            st.subheader("AWS Bedrock Tools")
            aws_tools = tools.get("aws_bedrock", [])

            if aws_tools:
                for tool in aws_tools:
                    with st.expander(f"📘 {tool['name']}"):
                        st.write(f"**Description:** {tool['description']}")
                        st.write(f"**Tags:** {', '.join(tool.get('tags', []))}")
            else:
                st.info("No AWS Bedrock tools available")

        with tab2:
            st.subheader("Custom Tools")
            custom_tools = tools.get("custom", [])

            if custom_tools:
                for tool in custom_tools:
                    with st.expander(f"⚙️ {tool['name']}"):
                        st.write(f"**Description:** {tool.get('description', 'N/A')}")
                        st.write(f"**Endpoint:** {tool.get('endpoint', 'N/A')}")
            else:
                st.info("No custom tools available")

        with tab3:
            st.subheader("MCP Tools")
            mcp_tools = tools.get("mcp", [])

            if mcp_tools:
                for tool in mcp_tools:
                    with st.expander(f"🔌 {tool['name']}"):
                        st.write(f"**Description:** {tool['description']}")
            else:
                st.info("No MCP tools available")

    else:
        st.error("Could not load tools")

# ============================================================================
# Page: Test Deployed Agents
# ============================================================================

def page_test_agents():
    st.title("🧪 Test Deployed Agents")

    st.markdown("""
    Test agents that have been deployed to AWS Bedrock.
    This connects to your AWS account and invokes real agents.
    """)

    # Predefined agents (the ones we deployed)
    deployed_agents = {
        "customer-support-v1": {
            "agent_id": "RRI1DLHWT2",
            "description": "Customer support ticket routing and resolution agent"
        },
        "email-router-v1": {
            "agent_id": "CWIOBMGNPO",
            "description": "Email routing and response system"
        }
    }

    st.subheader("Available Agents")

    col1, col2 = st.columns(2)

    with col1:
        agent_name = st.selectbox(
            "Select an agent to test",
            list(deployed_agents.keys())
        )

        selected_agent = deployed_agents[agent_name]
        agent_id = selected_agent["agent_id"]

        st.info(f"""
        **Agent ID:** {agent_id}

        **Description:** {selected_agent["description"]}
        """)

    with col2:
        st.subheader("Test Input")
        user_input = st.text_area(
            "Message to send to agent",
            placeholder="e.g., I need help with my billing question",
            height=150
        )

    st.divider()

    if st.button("🚀 Send Message to Agent", type="primary", use_container_width=True):
        if not user_input.strip():
            st.error("Please enter a message")
            return

        with st.spinner(f"Invoking {agent_name}..."):
            import asyncio

            async def test_agent():
                async with httpx.AsyncClient(timeout=120) as client:
                    try:
                        # Call deployment manager to invoke the agent
                        result = await call_api(
                            f"/deployments/test",
                            method="POST",
                            data={
                                "agent_id": agent_id,
                                "user_input": user_input,
                                "agent_name": agent_name
                            }
                        )
                        return result
                    except Exception as e:
                        return {"success": False, "error": str(e)}

            try:
                result = asyncio.run(test_agent())

                if result["success"]:
                    output = result["data"]

                    st.success("✅ Agent responded successfully!")

                    st.divider()

                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("Request")
                        st.write(f"**Agent:** {agent_name}")
                        st.write(f"**Message:** {user_input}")

                    with col2:
                        st.subheader("Response")
                        status = output.get("status", "unknown")
                        st.write(f"**Status:** {status}")

                        if status == "completed":
                            st.success("Execution completed!")
                            response_output = output.get("output", "No output")
                            st.write(response_output)
                        elif status == "failed":
                            st.error(f"Execution failed: {output.get('error', 'Unknown error')}")
                        else:
                            st.info(f"Status: {status}")
                            st.json(output)

                else:
                    st.error(f"Error: {result.get('error', 'Unknown error')}")

            except Exception as e:
                st.error(f"Error invoking agent: {str(e)}")

# ============================================================================
# Main App
# ============================================================================

def main():
    # Sidebar navigation
    st.sidebar.title("🚀 Blueprint POC")

    page = st.sidebar.radio(
        "Navigate",
        ["🏠 Home", "📝 Generate", "🔧 Edit", "🛠️ Tools", "🚀 Deploy", "⚙️ Execute", "🧪 Test Agents"]
    )

    st.sidebar.divider()

    # Session state info
    if "workflow_id" in st.session_state:
        st.sidebar.info(f"📋 Workflow: `{st.session_state.workflow_id[:8]}...`")

    if "deployment_id" in st.session_state:
        st.sidebar.info(f"🚀 Deployment: `{st.session_state.deployment_id[:8]}...`")

    st.sidebar.divider()

    st.sidebar.markdown("""
    ### About
    Blueprint POC converts natural language prompts into executable agentic workflows.

    **Stack:**
    - FastAPI backend
    - Claude Haiku 4.5 LLM
    - LangGraph orchestration
    - AWS AgentCore Runtime

    **Docs:** See README.md
    """)

    # Route to pages
    if "Home" in page:
        page_home()
    elif "Generate" in page:
        page_generate()
    elif "Edit" in page:
        page_edit()
    elif "Tools" in page:
        page_tools()
    elif "Deploy" in page:
        page_deploy()
    elif "Execute" in page:
        page_execute()
    elif "Test Agents" in page:
        page_test_agents()

if __name__ == "__main__":
    main()
