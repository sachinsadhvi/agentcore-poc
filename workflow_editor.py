"""
Workflow Editor
Allows editing, updating, and deleting components of a workflow
"""

from typing import Dict, List, Any
import copy
import json

class WorkflowEditor:
    """Edit workflow agents, tools, and structure"""

    def update_agent(
        self,
        workflow: Dict[str, Any],
        agent_name: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an agent in the workflow

        Args:
            workflow: Current workflow
            agent_name: Name of agent to update
            updates: Fields to update (name, role, tools, instructions, etc.)

        Returns:
            Updated workflow
        """
        workflow = copy.deepcopy(workflow)
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])

        # Find agent by name
        agent_found = False
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_found = True
                # Update fields
                if "name" in updates:
                    agent["name"] = updates["name"]
                if "role" in updates:
                    agent["role"] = updates["role"]
                if "tools" in updates:
                    agent["tools"] = updates["tools"]
                if "instructions" in updates:
                    agent["instructions"] = updates["instructions"]
                if "temperature" in updates:
                    agent["temperature"] = updates["temperature"]
                if "model" in updates:
                    agent["model"] = updates["model"]
                break

        if not agent_found:
            raise ValueError(f"Agent '{agent_name}' not found in workflow")

        return workflow

    def delete_agent(
        self,
        workflow: Dict[str, Any],
        agent_name: str
    ) -> Dict[str, Any]:
        """
        Delete an agent from the workflow

        Args:
            workflow: Current workflow
            agent_name: Name of agent to delete

        Returns:
            Updated workflow
        """
        workflow = copy.deepcopy(workflow)
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])

        # Find and remove agent
        agent_id = None
        new_agents = []
        for agent in agents:
            if agent.get("name") == agent_name:
                agent_id = agent.get("id")
            else:
                new_agents.append(agent)

        if agent_id is None:
            raise ValueError(f"Agent '{agent_name}' not found in workflow")

        schema["agents"] = new_agents

        # Remove nodes that reference this agent
        workflow_def = schema.get("workflow", {})
        nodes = workflow_def.get("nodes", [])
        new_nodes = [n for n in nodes if n.get("agent_id") != agent_id]
        workflow_def["nodes"] = new_nodes

        return workflow

    def add_tool(
        self,
        workflow: Dict[str, Any],
        tool_name: str,
        tool_source: str,
        tool_description: str,
        endpoint: str = None
    ) -> Dict[str, Any]:
        """
        Add a tool to the workflow's tool registry

        Args:
            workflow: Current workflow
            tool_name: Name of the tool
            tool_source: Source (aws-bedrock, mcp, custom)
            tool_description: Description of the tool
            endpoint: Endpoint for custom/MCP tools

        Returns:
            Updated workflow
        """
        workflow = copy.deepcopy(workflow)

        # Add to workflow tools
        if "tools" not in workflow:
            workflow["tools"] = {}

        workflow["tools"][tool_name] = {
            "name": tool_name,
            "source": tool_source,
            "description": tool_description,
            "endpoint": endpoint
        }

        return workflow

    def delete_tool(
        self,
        workflow: Dict[str, Any],
        tool_name: str
    ) -> Dict[str, Any]:
        """
        Delete a tool from the workflow

        Args:
            workflow: Current workflow
            tool_name: Name of tool to delete

        Returns:
            Updated workflow
        """
        workflow = copy.deepcopy(workflow)

        if "tools" not in workflow or tool_name not in workflow.get("tools", {}):
            raise ValueError(f"Tool '{tool_name}' not found in workflow")

        # Remove tool
        del workflow["tools"][tool_name]

        # Remove tool from all agents that use it
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])
        for agent in agents:
            if tool_name in agent.get("tools", []):
                agent["tools"].remove(tool_name)

        return workflow

    def add_agent(
        self,
        workflow: Dict[str, Any],
        agent_name: str,
        agent_role: str,
        tools: List[str] = None,
        instructions: str = None,
        model: str = "claude-opus-4-1",
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Add a new agent to the workflow

        Args:
            workflow: Current workflow
            agent_name: Name of the new agent
            agent_role: Role/responsibility of the agent
            tools: List of tools the agent can use
            instructions: System instructions for the agent
            model: Model to use for the agent
            temperature: Temperature for the model

        Returns:
            Updated workflow with new agent
        """
        workflow = copy.deepcopy(workflow)
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])

        # Check if agent already exists
        for agent in agents:
            if agent.get("name") == agent_name:
                raise ValueError(f"Agent '{agent_name}' already exists")

        # Create new agent
        import uuid
        new_agent = {
            "id": f"agent-{str(uuid.uuid4())[:8]}",
            "name": agent_name,
            "role": agent_role,
            "model": model,
            "temperature": temperature,
            "instructions": instructions or f"You are a {agent_role}",
            "tools": tools or []
        }

        agents.append(new_agent)
        schema["agents"] = agents

        return workflow

    def add_node(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        node_type: str,  # "task", "human-in-loop", "decision"
        agent_id: str = None,
        instruction: str = None,
        depends_on: List[str] = None,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Add a node to the workflow

        Args:
            workflow: Current workflow
            node_id: Unique node identifier
            node_type: Type of node (task, human-in-loop, decision)
            agent_id: Agent ID to use for task nodes
            instruction: Instruction for this node
            depends_on: List of node IDs this node depends on
            timeout: Timeout in seconds

        Returns:
            Updated workflow
        """
        workflow = copy.deepcopy(workflow)
        schema = workflow.get("schema", {})
        workflow_def = schema.get("workflow", {})
        nodes = workflow_def.get("nodes", [])

        # Check if node already exists
        if any(n.get("id") == node_id for n in nodes):
            raise ValueError(f"Node '{node_id}' already exists")

        # Create new node
        new_node = {
            "id": node_id,
            "type": node_type,
            "instruction": instruction or f"Execute {node_type} node",
            "depends_on": depends_on or [],
            "timeout": timeout
        }

        if agent_id:
            new_node["agent_id"] = agent_id

        nodes.append(new_node)
        workflow_def["nodes"] = nodes

        return workflow

    def delete_node(
        self,
        workflow: Dict[str, Any],
        node_id: str
    ) -> Dict[str, Any]:
        """
        Delete a node from the workflow

        Args:
            workflow: Current workflow
            node_id: ID of node to delete

        Returns:
            Updated workflow
        """
        workflow = copy.deepcopy(workflow)
        schema = workflow.get("schema", {})
        workflow_def = schema.get("workflow", {})
        nodes = workflow_def.get("nodes", [])

        # Find and remove node
        new_nodes = [n for n in nodes if n.get("id") != node_id]

        if len(new_nodes) == len(nodes):
            raise ValueError(f"Node '{node_id}' not found in workflow")

        workflow_def["nodes"] = new_nodes

        # Remove dependencies on this node
        for node in workflow_def["nodes"]:
            depends_on = node.get("depends_on", [])
            if node_id in depends_on:
                depends_on.remove(node_id)

        return workflow

    def reorder_nodes(
        self,
        workflow: Dict[str, Any],
        node_order: List[str]
    ) -> Dict[str, Any]:
        """
        Reorder nodes in the workflow (for serial execution)

        Args:
            workflow: Current workflow
            node_order: List of node IDs in desired order

        Returns:
            Updated workflow with new execution order
        """
        workflow = copy.deepcopy(workflow)
        schema = workflow.get("schema", {})
        workflow_def = schema.get("workflow", {})
        nodes = workflow_def.get("nodes", [])

        # Create a map of node_id to node
        node_map = {n.get("id"): n for n in nodes}

        # Rebuild nodes in specified order
        new_nodes = []
        for node_id in node_order:
            if node_id in node_map:
                node = copy.deepcopy(node_map[node_id])
                # Update dependencies
                prev_index = new_nodes.__len__() - 1
                if prev_index >= 0:
                    prev_node = new_nodes[prev_index]
                    node["depends_on"] = [prev_node["id"]]
                else:
                    node["depends_on"] = []
                new_nodes.append(node)

        workflow_def["nodes"] = new_nodes
        return workflow

    def export_workflow(self, workflow: Dict[str, Any]) -> str:
        """Export workflow as JSON string"""
        return json.dumps(workflow, indent=2)

    def validate_workflow(self, workflow: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate workflow structure

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Check required fields
        if "name" not in workflow:
            errors.append("Missing workflow name")

        if "schema" not in workflow:
            errors.append("Missing workflow schema")
            return (False, errors)

        schema = workflow.get("schema", {})

        # Check agents
        agents = schema.get("agents", [])
        if not agents:
            errors.append("Workflow must have at least one agent")

        agent_ids = {a.get("id") for a in agents}

        # Check nodes
        nodes = schema.get("workflow", {}).get("nodes", [])
        if not nodes:
            errors.append("Workflow must have at least one node")

        for node in nodes:
            agent_id = node.get("agent_id")
            if node.get("type") == "task" and agent_id and agent_id not in agent_ids:
                errors.append(f"Node '{node.get('id')}' references non-existent agent '{agent_id}'")

        return (len(errors) == 0, errors)
