"""
Workflow Generator
Converts natural language prompts into workflow schemas using LLM
"""

import json
from typing import Dict, List, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class WorkflowGenerator:
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry
        self.client = OpenAI()
        self.model = "gpt-4o-mini"

    async def generate(
        self,
        prompt: str,
        auto_suggest_tools: bool = True,
        include_memory: bool = True,
        include_knowledge_base: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a workflow schema from natural language prompt

        Args:
            prompt: User's natural language description
            auto_suggest_tools: Automatically suggest tools based on prompt
            include_memory: Include memory/state management in workflow
            include_knowledge_base: Include knowledge base access

        Returns:
            Workflow schema with agents, tools, and execution flow
        """

        # Get available tools
        available_tools = self.tool_registry.list_all_tools()

        # Suggest tools based on prompt if enabled
        suggested_tool_names = []
        if auto_suggest_tools:
            suggested_tools = self.tool_registry.get_tools_for_task(prompt)
            suggested_tool_names = [t.name for t in suggested_tools]

        # Build the system prompt for workflow generation
        system_prompt = """You are an expert workflow architect specializing in agentic AI systems.

Your task is to convert natural language descriptions into structured multi-agent workflow schemas.
Each agent in the workflow reasons directly from the input data — no external tool calls are needed.

You MUST output a valid JSON workflow schema following this EXACT structure:
{
    "name": "workflow-name",
    "description": "Clear description of what the workflow does",
    "version": "1.0",
    "suggested_tools": [],
    "schema": {
        "agents": [
            {
                "id": "agent-unique-id",
                "name": "Agent Name",
                "role": "What this agent does in one sentence",
                "model": "gpt-4o-mini",
                "instructions": "Detailed system prompt — see INSTRUCTION RULES below",
                "tools": [],
                "temperature": 0.1
            }
        ],
        "workflow": {
            "type": "dag",
            "execution_mode": "serial",
            "nodes": [
                {
                    "id": "node-id",
                    "type": "task",
                    "agent_id": "agent-unique-id",
                    "instruction": "What this node does",
                    "depends_on": [],
                    "timeout": 300
                }
            ]
        }
    }
}

RULES:
1. "tools" MUST always be an empty list []. Never put tool names in it.
2. "suggested_tools" MUST always be an empty list [].
3. Create 2-4 agents with narrow, specific roles that together cover the full task.
4. Each agent's output feeds into the next — design them as an analysis pipeline.
5. Use meaningful IDs: "validate-input", "assess-risk", "generate-decision", etc.
6. Only output valid JSON — nothing else, no markdown fences.
7. temperature MUST be 0.1 for every agent.

AGENT INSTRUCTION RULES — every "instructions" field MUST follow this pattern:
- One sentence stating the agent's exact role.
- List the specific input fields the agent should read from the data (use field names).
- One sentence: "Base your analysis only on the input data provided; never invent or assume values not present."
- One sentence describing the exact output format (e.g. "Output a JSON object with fields: risk_level, reasons, recommendation").

VALIDATION / INTAKE / ANALYSIS — default to **best-effort analysis**, not all-or-nothing rejection:
- Prefer agents that **analyze and score** from whatever fields exist; list absent fields under `data_gaps` or `not_available` (array of strings) instead of failing the whole run.
- Only use strict `is_valid` / `missing_fields` when the USER explicitly asked for schema or compliance gatekeeping. Then: `missing_fields` must list only **blocking** required paths that are actually absent; never return empty `missing_fields` with `is_valid: false`.
- "If optional context is missing, continue with caveats (e.g. `confidence`: LOW) rather than declaring the order or transaction invalid."
- "Ignore any existing validation subtree in Input Data; do not copy validation.is_valid from Input Data into your output."

GOOD EXAMPLE (ecommerce fraud):
"You are a transaction risk evaluator. Read these fields from the input data: user.account_age_days, user.chargebacks, payment.address_mismatch, payment.is_first_time_card, payment.transaction_status. Base your analysis only on the input data provided; never invent or assume values not present. Output a JSON object with fields: risk_level (LOW/MEDIUM/HIGH), risk_factors (list of strings), and recommended_action (APPROVE/REVIEW/BLOCK)."

GOOD EXAMPLE (loan intake):
"You are a loan application intake agent. Read these fields when present: applicant.name, applicant.loan_amount, applicant.income, applicant.credit_score, applicant.employment_years. Base your analysis only on the input data provided; never invent or assume values not present. Output a JSON object with fields: fields_present (list), data_gaps (list of missing non-critical paths), completeness (COMPLETE if all listed fields exist else PARTIAL), dti_ratio (number or null if income/loan missing), and initial_assessment (one sentence summarizing what you could conclude from partial data)."
"""

        user_message = f"""Generate a workflow schema for the following request:

USER REQUEST:
{prompt}

REQUIREMENTS:
- Number of agents: 2-4 (based on task complexity)
- Workflow type: serial pipeline (each agent's output feeds the next)
- tools and suggested_tools MUST be empty lists []
- Follow the INSTRUCTION RULES exactly for every agent's instructions field
- Default to best-effort analysis from partial input; strict all-fields-required validation only if the user explicitly asks for it

Generate the workflow schema as valid JSON:"""

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )

            response_text = completion.choices[0].message.content or ""

            # Strip markdown fences if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.split("```")[0]
            response_text = response_text.strip()

            # Parse JSON
            workflow = json.loads(response_text)

            # Ensure suggested_tools is always a list of strings
            if "suggested_tools" not in workflow:
                workflow["suggested_tools"] = suggested_tool_names
            else:
                tool_list = workflow.get("suggested_tools", [])
                if tool_list and hasattr(tool_list[0], 'name'):
                    workflow["suggested_tools"] = [t.name for t in tool_list]

            # Validate workflow schema
            self.validate_workflow(workflow)

            return workflow

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse workflow schema: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error generating workflow: {str(e)}")

    def validate_workflow(self, workflow: Dict[str, Any]) -> bool:
        """
        Validate workflow schema structure

        Args:
            workflow: Workflow schema to validate

        Returns:
            True if valid, raises ValueError if invalid
        """
        required_fields = ["name", "description", "schema"]
        for field in required_fields:
            if field not in workflow:
                raise ValueError(f"Missing required field: {field}")

        schema = workflow.get("schema", {})
        required_schema_fields = ["agents", "workflow"]
        for field in required_schema_fields:
            if field not in schema:
                raise ValueError(f"Missing required schema field: {field}")

        # Validate agents
        agents = schema.get("agents", [])
        if not agents or len(agents) == 0:
            raise ValueError("Workflow must have at least one agent")

        agent_ids = {agent.get("id") for agent in agents}
        for agent in agents:
            if "id" not in agent or "name" not in agent:
                raise ValueError("Each agent must have 'id' and 'name'")

        # Validate workflow nodes
        workflow_def = schema.get("workflow", {})
        nodes = workflow_def.get("nodes", [])
        if not nodes:
            raise ValueError("Workflow must have at least one node")

        for node in nodes:
            agent_id = node.get("agent_id")
            if agent_id and agent_id not in agent_ids:
                raise ValueError(f"Node references non-existent agent: {agent_id}")

        return True
