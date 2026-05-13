"""
Blueprint POC Test Client
Demonstrates the workflow generation -> editing -> deployment flow
"""

import asyncio
import httpx
import json
import time
from typing import Dict, Any

API_BASE_URL = "http://localhost:8000"

class BlueprintPOCClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url)

    async def generate_workflow(
        self,
        prompt: str,
        auto_suggest_tools: bool = True,
        include_memory: bool = True,
        include_knowledge_base: bool = True
    ) -> Dict[str, Any]:
        """Generate a workflow from natural language prompt"""
        print(f"\n{'='*70}")
        print(f"📝 GENERATING WORKFLOW")
        print(f"{'='*70}")
        print(f"Prompt: {prompt}\n")

        response = await self.client.post(
            "/workflows/generate",
            json={
                "prompt": prompt,
                "auto_suggest_tools": auto_suggest_tools,
                "include_memory": include_memory,
                "include_knowledge_base": include_knowledge_base
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to generate workflow: {response.text}")

        workflow = response.json()
        print(f"✅ Workflow generated successfully!")
        print(f"   Workflow ID: {workflow['workflow_id']}")
        print(f"   Name: {workflow['name']}")
        print(f"   Description: {workflow['description']}")
        print(f"   Suggested Tools: {', '.join(workflow.get('suggested_tools', []))}")

        return workflow

    async def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Retrieve workflow details"""
        response = await self.client.get(f"/workflows/{workflow_id}")

        if response.status_code != 200:
            raise Exception(f"Failed to get workflow: {response.text}")

        return response.json()

    async def update_agent(
        self,
        workflow_id: str,
        agent_name: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an agent in the workflow"""
        print(f"\n{'='*70}")
        print(f"🔧 UPDATING AGENT: {agent_name}")
        print(f"{'='*70}")
        print(f"Updates: {json.dumps(updates, indent=2)}\n")

        response = await self.client.put(
            f"/workflows/{workflow_id}/agents/{agent_name}",
            json=updates
        )

        if response.status_code != 200:
            raise Exception(f"Failed to update agent: {response.text}")

        result = response.json()
        print(f"✅ Agent updated successfully!")

        return result

    async def delete_agent(
        self,
        workflow_id: str,
        agent_name: str
    ) -> Dict[str, Any]:
        """Delete an agent from the workflow"""
        print(f"\n{'='*70}")
        print(f"🗑️  DELETING AGENT: {agent_name}")
        print(f"{'='*70}\n")

        response = await self.client.delete(
            f"/workflows/{workflow_id}/agents/{agent_name}"
        )

        if response.status_code != 200:
            raise Exception(f"Failed to delete agent: {response.text}")

        result = response.json()
        print(f"✅ Agent deleted successfully!")

        return result

    async def add_tool(
        self,
        workflow_id: str,
        tool_name: str,
        tool_source: str,
        tool_description: str,
        endpoint: str = None
    ) -> Dict[str, Any]:
        """Add a tool to the workflow"""
        print(f"\n{'='*70}")
        print(f"🛠️  ADDING TOOL: {tool_name}")
        print(f"{'='*70}")
        print(f"Source: {tool_source}")
        print(f"Description: {tool_description}\n")

        response = await self.client.post(
            f"/workflows/{workflow_id}/tools",
            json={
                "name": tool_name,
                "source": tool_source,
                "description": tool_description,
                "endpoint": endpoint
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to add tool: {response.text}")

        result = response.json()
        print(f"✅ Tool added successfully!")

        return result

    async def delete_tool(
        self,
        workflow_id: str,
        tool_name: str
    ) -> Dict[str, Any]:
        """Delete a tool from the workflow"""
        print(f"\n{'='*70}")
        print(f"🗑️  DELETING TOOL: {tool_name}")
        print(f"{'='*70}\n")

        response = await self.client.delete(
            f"/workflows/{workflow_id}/tools/{tool_name}"
        )

        if response.status_code != 200:
            raise Exception(f"Failed to delete tool: {response.text}")

        result = response.json()
        print(f"✅ Tool deleted successfully!")

        return result

    async def get_available_tools(self) -> Dict[str, Any]:
        """Get all available tools"""
        response = await self.client.get("/tools/available")

        if response.status_code != 200:
            raise Exception(f"Failed to get tools: {response.text}")

        return response.json()

    async def deploy_workflow(
        self,
        workflow_id: str,
        deployment_name: str,
        runtime: str = "agentcore"
    ) -> Dict[str, Any]:
        """Deploy workflow to AgentCore Runtime"""
        print(f"\n{'='*70}")
        print(f"🚀 DEPLOYING WORKFLOW")
        print(f"{'='*70}")
        print(f"Workflow ID: {workflow_id}")
        print(f"Deployment Name: {deployment_name}")
        print(f"Runtime: {runtime}\n")

        response = await self.client.post(
            f"/workflows/{workflow_id}/deploy",
            json={
                "workflow_id": workflow_id,
                "deployment_name": deployment_name,
                "runtime": runtime
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to deploy workflow: {response.text}")

        result = response.json()
        print(f"✅ Workflow deployed successfully!")
        print(f"   Deployment ID: {result['deployment_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Image URI: {result.get('image_uri', 'N/A')}")

        return result

    async def get_deployment(self, deployment_id: str) -> Dict[str, Any]:
        """Get deployment details"""
        response = await self.client.get(f"/deployments/{deployment_id}")

        if response.status_code != 200:
            raise Exception(f"Failed to get deployment: {response.text}")

        return response.json()

    async def execute_workflow(
        self,
        deployment_id: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a deployed workflow"""
        print(f"\n{'='*70}")
        print(f"⚙️  EXECUTING WORKFLOW")
        print(f"{'='*70}")
        print(f"Deployment ID: {deployment_id}")
        print(f"Input Data: {json.dumps(input_data, indent=2)}\n")

        response = await self.client.post(
            f"/deployments/{deployment_id}/execute",
            json={
                "deployment_id": deployment_id,
                "input_data": input_data
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to execute workflow: {response.text}")

        result = response.json()
        print(f"✅ Workflow executed successfully!")
        print(f"   Execution ID: {result['execution_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Output: {json.dumps(result.get('output'), indent=2)}")

        return result

    async def close(self):
        """Close the client"""
        await self.client.aclose()

async def run_poc_demo():
    """Run the POC demo"""
    client = BlueprintPOCClient()

    try:
        # Wait for API to be ready
        print("\n⏳ Waiting for API to be ready...")
        for attempt in range(10):
            try:
                response = await client.client.get("/health")
                if response.status_code == 200:
                    print("✅ API is ready!\n")
                    break
            except:
                pass
            await asyncio.sleep(1)
        else:
            print("❌ API failed to start")
            return

        # ====================================================================
        # STEP 1: Generate Workflow from Natural Language
        # ====================================================================
        workflow = await client.generate_workflow(
            prompt="Create an AWS architecture design workflow that analyzes requirements, selects optimal services, designs the architecture, analyzes costs, and generates an executive report. The workflow should be able to handle large-scale applications with high availability and security requirements. Include AWS Bedrock tools for knowledge and pricing information.",
            auto_suggest_tools=True,
            include_memory=True,
            include_knowledge_base=True
        )

        workflow_id = workflow["workflow_id"]
        print(f"\n📋 Generated Workflow Schema:")
        print(json.dumps(workflow["schema"], indent=2)[:500] + "...")

        # ====================================================================
        # STEP 2: Get Available Tools
        # ====================================================================
        print(f"\n{'='*70}")
        print(f"🛠️  AVAILABLE TOOLS")
        print(f"{'='*70}")
        tools = await client.get_available_tools()
        print(f"AWS Bedrock Tools: {len(tools.get('aws_bedrock', []))}")
        for tool in tools.get('aws_bedrock', [])[:3]:
            print(f"  - {tool['name']}: {tool['description']}")

        # ====================================================================
        # STEP 3: Edit Workflow - Update an Agent
        # ====================================================================
        await client.update_agent(
            workflow_id=workflow_id,
            agent_name="Requirements Analyzer",
            updates={
                "role": "Enhanced Requirements Analyzer",
                "instructions": "Analyze requirements with improved error handling and validation",
                "temperature": 0.5
            }
        )

        # ====================================================================
        # STEP 4: Edit Workflow - Add a Custom Tool
        # ====================================================================
        await client.add_tool(
            workflow_id=workflow_id,
            tool_name="compliance-validator",
            tool_source="custom",
            tool_description="Validate architecture against compliance requirements",
            endpoint="https://internal-api/compliance-validator"
        )

        # ====================================================================
        # STEP 5: Get Updated Workflow
        # ====================================================================
        print(f"\n{'='*70}")
        print(f"📖 FETCHING UPDATED WORKFLOW")
        print(f"{'='*70}\n")
        updated_workflow = await client.get_workflow(workflow_id)
        print(f"Workflow Name: {updated_workflow.get('name')}")
        print(f"Agents: {len(updated_workflow.get('schema', {}).get('agents', []))}")
        print(f"Tools: {len(updated_workflow.get('schema', {}).get('workflow', {}).get('nodes', []))}")

        # ====================================================================
        # STEP 6: Deploy Workflow to AgentCore Runtime
        # ====================================================================
        deployment = await client.deploy_workflow(
            workflow_id=workflow_id,
            deployment_name="AWS Architecture Design Workflow v1",
            runtime="agentcore"
        )

        deployment_id = deployment["deployment_id"]

        # ====================================================================
        # STEP 7: Get Deployment Details
        # ====================================================================
        print(f"\n{'='*70}")
        print(f"📋 DEPLOYMENT DETAILS")
        print(f"{'='*70}\n")
        deployment_details = await client.get_deployment(deployment_id)
        print(f"Deployment Status: {deployment_details.get('status')}")
        print(f"Runtime: {deployment_details.get('runtime')}")

        # ====================================================================
        # STEP 8: Execute Deployed Workflow
        # ====================================================================
        execution_result = await client.execute_workflow(
            deployment_id=deployment_id,
            input_data={
                "user_input": "Design an e-commerce platform with high availability and PCI-DSS compliance",
                "max_budget": 50000
            }
        )

        # ====================================================================
        # SUMMARY
        # ====================================================================
        print(f"\n{'='*70}")
        print(f"✅ POC DEMO COMPLETED SUCCESSFULLY")
        print(f"{'='*70}")
        print(f"\n📊 Summary:")
        print(f"   ✓ Workflow Generated from Natural Language")
        print(f"   ✓ Agents and Tools Viewed")
        print(f"   ✓ Workflow Edited (agent updated, tool added)")
        print(f"   ✓ Workflow Deployed to AgentCore Runtime")
        print(f"   ✓ Workflow Executed")
        print(f"\n📦 Artifacts:")
        print(f"   Workflow ID: {workflow_id}")
        print(f"   Deployment ID: {deployment_id}")
        print(f"   Execution Status: {execution_result['status']}")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        await client.close()

if __name__ == "__main__":
    print("""
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
    """)

    asyncio.run(run_poc_demo())
