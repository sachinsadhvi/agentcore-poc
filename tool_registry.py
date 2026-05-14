"""
Tool Registry
Manages AWS Bedrock tools, MCP servers, and custom tools
"""

from typing import Dict, List, Any
from dataclasses import dataclass, asdict
import json
from mock_tools import (
    get_credit_bureau_data,
    get_income_documents,
    get_bank_statements,
    score_risk,
    flag_exceptions,
    generate_underwriter_summary
)

@dataclass
class Tool:
    name: str
    source: str
    description: str
    input_schema: Dict[str, Any] = None
    output_schema: Dict[str, Any] = None
    tags: List[str] = None
    endpoint: str = None

    def to_dict(self):
        return asdict(self)

class ToolRegistry:
    def __init__(self):
        self.aws_bedrock_tools: Dict[str, Tool] = {}
        self.mcp_tools: Dict[str, Tool] = {}
        self.custom_tools: Dict[str, Tool] = {}

    async def init_aws_bedrock_tools(self, region: str = "us-east-1", account_id: str = None):
        """Initialize AWS Bedrock tools and loan underwriting tools"""
        tools = [
            Tool(
                name="aws-kb-server",
                source="aws-bedrock",
                description="Query AWS knowledge base for service information, capabilities, and best practices",
                input_schema={
                    "query": "string",
                    "service": "string (optional)"
                },
                output_schema={
                    "results": "array",
                    "confidence": "number"
                },
                tags=["aws", "knowledge", "architecture", "services"]
            ),
            Tool(
                name="aws-pricing",
                source="aws-bedrock",
                description="Get current AWS service pricing and cost estimation",
                input_schema={
                    "service": "string",
                    "region": "string",
                    "instance_type": "string (optional)"
                },
                output_schema={
                    "pricing": "object",
                    "unit": "string",
                    "currency": "string"
                },
                tags=["aws", "cost", "pricing", "budget"]
            ),
            Tool(
                name="aws-compliance-checker",
                source="aws-bedrock",
                description="Check AWS services for compliance requirements (PCI-DSS, HIPAA, SOC2, etc.)",
                input_schema={
                    "service": "string",
                    "compliance_standard": "string"
                },
                output_schema={
                    "is_compliant": "boolean",
                    "requirements": "array",
                    "controls": "array"
                },
                tags=["aws", "security", "compliance"]
            ),
            Tool(
                name="aws-performance-analyzer",
                source="aws-bedrock",
                description="Analyze performance characteristics of AWS services (latency, throughput, scalability)",
                input_schema={
                    "service": "string",
                    "metric": "string"
                },
                output_schema={
                    "baseline": "number",
                    "limits": "object",
                    "recommendations": "array"
                },
                tags=["aws", "performance", "optimization"]
            ),
            Tool(
                name="web-search",
                source="mcp",
                description="Search the web for additional information",
                input_schema={
                    "query": "string"
                },
                output_schema={
                    "results": "array"
                },
                tags=["search", "research"]
            ),
            Tool(
                name="browser",
                source="aws-bedrock",
                description=(
                    "Amazon Bedrock AgentCore **Browser** built-in (managed): navigate sites, "
                    "click, fill forms, extract DOM, screenshots. Enable on the AgentCore runtime / "
                    "agent configuration in AWS; use when the task needs live web or authenticated "
                    "portals (see AgentCore Browser tool docs)."
                ),
                input_schema={
                    "url": "string",
                    "goal": "string (what to extract or verify)"
                },
                output_schema={
                    "summary": "string",
                    "sources": "array"
                },
                tags=["browser", "web", "agentcore", "research", "builtin"]
            ),
            Tool(
                name="code-interpreter",
                source="aws-bedrock",
                description=(
                    "Amazon Bedrock AgentCore **Code Interpreter** built-in (managed sandbox): "
                    "run Python, install packages, plot, process uploads. Enable on the AgentCore "
                    "runtime / agent configuration in AWS (see bedrock_agentcore.tools.code_interpreter_client)."
                ),
                input_schema={
                    "code_or_task": "string",
                    "files": "array (optional)"
                },
                output_schema={
                    "stdout": "string",
                    "artifacts": "array"
                },
                tags=["code", "python", "sandbox", "agentcore", "builtin"]
            ),
            # Loan Underwriting Tools
            Tool(
                name="credit-bureau-lookup",
                source="custom",
                description="Retrieve credit bureau data including credit score, payment history, and delinquencies",
                input_schema={
                    "applicant_id": "string"
                },
                output_schema={
                    "credit_score": "number",
                    "payment_history": "string",
                    "delinquencies": "number"
                },
                tags=["loan", "credit", "underwriting"]
            ),
            Tool(
                name="income-document-retrieval",
                source="custom",
                description="Get income verification documents including employment status, annual income, and job details",
                input_schema={
                    "applicant_id": "string"
                },
                output_schema={
                    "employment_status": "string",
                    "annual_income": "string",
                    "tenure_months": "number"
                },
                tags=["loan", "income", "underwriting"]
            ),
            Tool(
                name="bank-statement-analysis",
                source="custom",
                description="Analyze bank statements for account balance, deposits, and financial health indicators",
                input_schema={
                    "applicant_id": "string"
                },
                output_schema={
                    "avg_balance_3m": "string",
                    "monthly_deposits": "string",
                    "overdraft_incidents": "number"
                },
                tags=["loan", "financial", "underwriting"]
            ),
            Tool(
                name="risk-score-calculator",
                source="custom",
                description="Calculate loan risk score based on credit, income, and bank data",
                input_schema={
                    "credit_data": "object",
                    "income_data": "object",
                    "bank_data": "object"
                },
                output_schema={
                    "risk_score": "number",
                    "risk_tier": "string",
                    "dti_ratio": "string"
                },
                tags=["loan", "risk", "scoring"]
            ),
            Tool(
                name="exception-flagger",
                source="custom",
                description="Identify and flag exceptions in loan application for underwriter review",
                input_schema={
                    "risk_data": "object",
                    "credit_data": "object",
                    "income_data": "object"
                },
                output_schema={
                    "exception_count": "number",
                    "flags": "array",
                    "requires_review": "boolean"
                },
                tags=["loan", "exceptions", "review"]
            ),
            Tool(
                name="underwriter-summary-generator",
                source="custom",
                description="Generate comprehensive underwriter summary with recommendation",
                input_schema={
                    "all_data": "object"
                },
                output_schema={
                    "summary": "string",
                    "recommendation": "string",
                    "requires_manual_review": "boolean"
                },
                tags=["loan", "summary", "underwriting"]
            ),
            # Ecommerce / fraud domain tools
            Tool(
                name="fraud-score-checker",
                source="custom",
                description="Score transaction fraud risk using address mismatch, card history, account age, and chargeback signals",
                input_schema={"state": "object"},
                output_schema={
                    "fraud_score": "number",
                    "fraud_risk": "string",
                    "signals_detected": "array",
                    "recommendation": "string"
                },
                tags=["ecommerce", "fraud", "risk", "transaction"]
            ),
            Tool(
                name="velocity-checker",
                source="custom",
                description="Check transaction velocity — flags unusually high purchase frequency in last 24h or 7 days",
                input_schema={"state": "object"},
                output_schema={
                    "transactions_last_24h": "number",
                    "transactions_last_7d": "number",
                    "velocity_flag": "boolean",
                    "assessment": "string"
                },
                tags=["ecommerce", "fraud", "velocity", "transaction"]
            ),
            Tool(
                name="order-risk-evaluator",
                source="custom",
                description="Aggregate order-level risk score combining fraud and velocity signals into a final APPROVE/REVIEW/BLOCK decision",
                input_schema={"state": "object"},
                output_schema={
                    "overall_risk": "string",
                    "fraud_score": "number",
                    "action": "string"
                },
                tags=["ecommerce", "fraud", "risk", "order"]
            ),
        ]

        for tool in tools:
            self.register_aws_bedrock_tool(tool)

    def register_aws_bedrock_tool(self, tool: Tool):
        """Register an AWS Bedrock tool"""
        self.aws_bedrock_tools[tool.name] = tool

    def register_mcp_tool(self, tool: Tool):
        """Register an MCP tool"""
        self.mcp_tools[tool.name] = tool

    def register_custom_tool(
        self,
        name: str,
        description: str,
        endpoint: str,
        input_schema: Dict[str, Any] = None,
        output_schema: Dict[str, Any] = None,
        tags: List[str] = None
    ) -> Tool:
        """Register a custom tool"""
        tool = Tool(
            name=name,
            source="custom",
            description=description,
            endpoint=endpoint,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            tags=tags or []
        )
        self.custom_tools[name] = tool
        return tool

    def get_aws_bedrock_tools(self) -> List[Dict[str, Any]]:
        """Get all AWS Bedrock tools"""
        return [tool.to_dict() for tool in self.aws_bedrock_tools.values()]

    def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Get all MCP tools"""
        return [tool.to_dict() for tool in self.mcp_tools.values()]

    def get_custom_tools(self) -> List[Dict[str, Any]]:
        """Get all custom tools"""
        return [tool.to_dict() for tool in self.custom_tools.values()]

    def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all tools organized by source"""
        return {
            "aws_bedrock": self.get_aws_bedrock_tools(),
            "mcp": self.get_mcp_tools(),
            "custom": self.get_custom_tools()
        }

    def get_tools_for_task(self, task_description: str) -> List[Tool]:
        """
        Get tools suggested for a specific task.
        Uses keyword matching per domain so each workflow gets only the tools
        that are relevant to its domain — preventing a loan-tool set from being
        suggested to an ecommerce, HR, or any other kind of workflow.
        """
        text = task_description.lower()
        suggested_tools = []

        # AWS infrastructure / architecture domain
        if any(kw in text for kw in ["architecture", "design", "aws", "service", "select", "cloud", "infrastructure"]):
            suggested_tools.append(self.aws_bedrock_tools.get("aws-kb-server"))

        if any(kw in text for kw in ["cost", "price", "budget", "estimate", "pricing"]):
            suggested_tools.append(self.aws_bedrock_tools.get("aws-pricing"))

        if any(kw in text for kw in ["compliance", "secure", "security", "pci", "hipaa", "soc2", "gdpr", "regulatory"]):
            suggested_tools.append(self.aws_bedrock_tools.get("aws-compliance-checker"))

        if any(kw in text for kw in ["performance", "latency", "throughput", "optimize", "benchmark"]):
            suggested_tools.append(self.aws_bedrock_tools.get("aws-performance-analyzer"))

        # Loan / mortgage / credit underwriting domain
        if any(kw in text for kw in ["loan", "mortgage", "credit", "underwriting", "lending", "borrower", "applicant"]):
            suggested_tools.append(self.aws_bedrock_tools.get("credit-bureau-lookup"))
            suggested_tools.append(self.aws_bedrock_tools.get("income-document-retrieval"))
            suggested_tools.append(self.aws_bedrock_tools.get("bank-statement-analysis"))
            suggested_tools.append(self.aws_bedrock_tools.get("risk-score-calculator"))
            suggested_tools.append(self.aws_bedrock_tools.get("exception-flagger"))
            suggested_tools.append(self.aws_bedrock_tools.get("underwriter-summary-generator"))

        # Ecommerce / fraud / order risk domain
        if any(kw in text for kw in ["ecommerce", "e-commerce", "order", "transaction", "fraud",
                                      "payment", "checkout", "cart", "purchase", "chargeback",
                                      "velocity", "card", "shopify", "merchant"]):
            suggested_tools.append(self.aws_bedrock_tools.get("fraud-score-checker"))
            suggested_tools.append(self.aws_bedrock_tools.get("velocity-checker"))
            suggested_tools.append(self.aws_bedrock_tools.get("order-risk-evaluator"))

        # Compliance / knowledge-base lookup applies broadly
        if any(kw in text for kw in ["policy", "regulation", "audit", "kyc", "aml", "ofac"]):
            suggested_tools.append(self.aws_bedrock_tools.get("aws-kb-server"))
            suggested_tools.append(self.aws_bedrock_tools.get("aws-compliance-checker"))

        if any(
            kw in text
            for kw in [
                "browser",
                "browse the",
                "web page",
                "website",
                "open url",
                "fetch page",
                "live web",
                "agentcore browser",
            ]
        ):
            suggested_tools.append(self.aws_bedrock_tools.get("browser"))

        if any(
            kw in text
            for kw in [
                "code interpreter",
                "code-interpreter",
                "execute python",
                "run python",
                "pandas",
                "numpy",
                "matplotlib",
                "plot ",
                "sandbox",
                "compute in code",
            ]
        ):
            suggested_tools.append(self.aws_bedrock_tools.get("code-interpreter"))

        # Filter out None values and deduplicate while preserving order
        seen = set()
        result = []
        for t in suggested_tools:
            if t is not None and t.name not in seen:
                seen.add(t.name)
                result.append(t)

        # Always include custom tools the caller registered explicitly
        for t in self.custom_tools.values():
            if t.name not in seen:
                seen.add(t.name)
                result.append(t)

        return result

    def get_tool_by_name(self, name: str) -> Tool:
        """Get a specific tool by name"""
        for source_dict in [self.aws_bedrock_tools, self.mcp_tools, self.custom_tools]:
            if name in source_dict:
                return source_dict[name]
        return None

    def validate_tool(self, name: str) -> bool:
        """Check if a tool exists and is valid"""
        return self.get_tool_by_name(name) is not None

    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a tool with the given parameters"""
        tool_executors = {
            "credit-bureau-lookup": lambda **kw: get_credit_bureau_data(kw.get("applicant_id", "APP001")),
            "income-document-retrieval": lambda **kw: get_income_documents(kw.get("applicant_id", "APP001")),
            "bank-statement-analysis": lambda **kw: get_bank_statements(kw.get("applicant_id", "APP001")),
            "risk-score-calculator": lambda **kw: score_risk(
                kw.get("credit_data", {}),
                kw.get("income_data", {}),
                kw.get("bank_data", {})
            ),
            "exception-flagger": lambda **kw: flag_exceptions(
                kw.get("risk_data", {}),
                kw.get("credit_data", {}),
                kw.get("income_data", {})
            ),
            "underwriter-summary-generator": lambda **kw: generate_underwriter_summary(
                kw.get("all_data", {})
            )
        }

        if tool_name in tool_executors:
            return tool_executors[tool_name](**kwargs)
        else:
            return {"error": f"Tool '{tool_name}' not found or not executable"}

    def format_tools_for_agent(self, tool_names: List[str]) -> List[Dict[str, Any]]:
        """
        Format tools for use in an agent configuration
        Returns tool definitions in a format suitable for LangGraph/LLM
        """
        formatted_tools = []

        for tool_name in tool_names:
            tool = self.get_tool_by_name(tool_name)
            if tool:
                formatted_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema or {},
                    "source": tool.source
                })

        return formatted_tools
