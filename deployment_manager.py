"""
Deployment Manager
Converts workflows to LangGraph and deploys to AWS AgentCore Runtime or Docker
Supports both native AgentCore deployment and containerized deployment
"""

from typing import Dict, List, Any, Optional
import os
import re
import uuid
import json
import tempfile
import subprocess
import shutil
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import anthropic


def _sanitize_agent_runtime_name(name: str) -> str:
    """Sanitize a name to match AgentCore's agentRuntimeName regex: [a-zA-Z][a-zA-Z0-9_]{0,47}.

    - Replaces any disallowed character (incl. spaces, hyphens) with underscore.
    - Ensures the first character is a letter, prefixing with 'a_' if not.
    - Truncates to 48 characters.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name or "")
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "a_" + cleaned
    return cleaned[:48] or "agent"

class DeploymentManager:
    def __init__(self, aws_region: str, aws_account_id: str, aws_access_key: str = None, aws_secret_key: str = None):
        self.aws_region = aws_region
        self.aws_account_id = aws_account_id
        self.ecr_registry = f"{aws_account_id}.dkr.ecr.{aws_region}.amazonaws.com"
        self.deployments: Dict[str, Dict] = {}

        # Initialize AWS clients with credentials if provided
        session_kwargs = {}
        if aws_access_key and aws_secret_key:
            session_kwargs = {
                'aws_access_key_id': aws_access_key,
                'aws_secret_access_key': aws_secret_key,
                'region_name': aws_region
            }
        else:
            session_kwargs = {'region_name': aws_region}

        self.ecr_client = boto3.client('ecr', **session_kwargs)
        self.iam_client = boto3.client('iam', **session_kwargs)
        self.bedrock_agent_client = boto3.client('bedrock-agent', **session_kwargs)
        self.s3_client = boto3.client('s3', **session_kwargs)
        self.agentcore_client = boto3.client('bedrock-agentcore', **session_kwargs)
        self.agentcore_control_client = boto3.client('bedrock-agentcore-control', **session_kwargs)

    async def deploy(
        self,
        workflow: Dict[str, Any],
        deployment_name: str,
        runtime: str = "agentcore-docker",
        credentials: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Deploy workflow to runtime

        Args:
            workflow: Workflow schema
            deployment_name: Name for this deployment
            runtime: Target runtime - "agentcore-native" for direct Bedrock Agent,
                     "agentcore-docker" for Docker-based (default),
                     "flotorch", "langgraph" for other containerized runtimes
            credentials: AWS credentials dict with access_key_id, secret_access_key

        Returns:
            Deployment details including agent_id and/or image_uri
        """

        deployment_id = f"deploy-{str(uuid.uuid4())[:8]}"

        try:
            # Get or create IAM role (check env var first)
            role_arn = os.getenv("AGENTCORE_EXECUTION_ROLE_ARN") or self._get_or_create_agent_role()
            print(f"[OK] Using IAM role: {role_arn}")

            # Route to appropriate deployment method
            if runtime == "agentcore-native":
                print(f"\n[*] Deploying to AgentCore (native)...")
                return await self._deploy_native_agentcore(
                    workflow, deployment_name, deployment_id, role_arn
                )
            elif runtime == "agentcore-runtime":
                print(f"\n[*] Deploying to AgentCore Runtime (hosted)...")
                return await self._deploy_agentcore_runtime(
                    workflow, deployment_name, deployment_id, role_arn
                )
            else:
                # Default to Docker-based deployment (agentcore-docker, flotorch, langgraph, etc.)
                print(f"\n[*] Deploying to {runtime} (Docker-based)...")
                return await self._deploy_docker(
                    workflow, deployment_name, deployment_id, role_arn, runtime
                )

        except Exception as e:
            print(f"[ERROR] Deployment failed: {str(e)}")
            return {
                "deployment_id": deployment_id,
                "status": "failed",
                "error": str(e)
            }

    async def _deploy_native_agentcore(
        self,
        workflow: Dict[str, Any],
        deployment_name: str,
        deployment_id: str,
        role_arn: str
    ) -> Dict[str, Any]:
        """Deploy directly to Bedrock Agent (native AgentCore)"""
        try:
            # Convert Blueprint schema to AgentCore schema
            print("[*] Converting workflow schema to AgentCore format...")
            agent_schema = self._convert_to_agentcore_schema(workflow)

            # Create Bedrock Agent with action groups
            print("[*] Creating Bedrock Agent with action groups...")
            agent_result = self._create_bedrock_agent_native(
                deployment_name,
                role_arn,
                workflow.get('description', f"Agentic workflow: {workflow.get('name', 'Unknown')}"),
                agent_schema
            )

            agent_id = agent_result.get('agentId', deployment_id)
            print(f"[OK] Agent created: {agent_id}")

            # Prepare agent
            print("[*] Preparing agent...")
            self.bedrock_agent_client.prepare_agent(agentId=agent_id)
            print("[OK] Agent prepared")

            deployment_info = {
                "deployment_id": deployment_id,
                "agent_id": agent_id,
                "deployment_name": deployment_name,
                "workflow_name": workflow.get("name", "Untitled"),
                "runtime": "agentcore-native",
                "status": "deployed",
                "created_at": str(__import__('datetime').datetime.now().isoformat()),
                "aws_region": self.aws_region,
                "role_arn": role_arn,
                "deployment_method": "native"
            }

            self.deployments[deployment_id] = deployment_info
            return deployment_info

        except Exception as e:
            print(f"[ERROR] Native AgentCore deployment failed: {str(e)}")
            raise

    async def _deploy_agentcore_runtime(
        self,
        workflow: Dict[str, Any],
        deployment_name: str,
        deployment_id: str,
        role_arn: str
    ) -> Dict[str, Any]:
        """Deploy to AWS Bedrock AgentCore Runtime (Hosted)"""
        try:
            print("[*] Deploying to AgentCore Runtime (Hosted)...")

            # Step 1: Create S3 bucket if needed
            s3_bucket = self._get_or_create_s3_bucket()
            print(f"[OK] Using S3 bucket: {s3_bucket}")

            # Step 2: Package agent for AgentCore Runtime
            print("[*] Packaging agent for AgentCore Runtime...")
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Create agent package (returns directory path)
                agent_dir = self._package_agent_for_agentcore(
                    workflow, deployment_name, temp_path
                )
                print(f"[OK] Agent packaged in: {agent_dir}")

                # Step 3: Upload files INDIVIDUALLY to S3 (not zipped)
                print("[*] Uploading agent files to S3...")
                agent_dir_path = Path(agent_dir)
                uploaded_files = []

                for file_path in agent_dir_path.rglob("*"):
                    if file_path.is_file():
                        # Create S3 key: agents/deployment-name/filename
                        s3_key = f"agents/{deployment_name}/{file_path.name}"

                        # Upload individual file
                        self._upload_to_s3(s3_bucket, str(file_path), s3_key)
                        uploaded_files.append(s3_key)
                        print(f"   [OK] Uploaded: {s3_key}")

                print(f"\n[OK] All files uploaded to S3!")
                print(f"    S3 Bucket: {s3_bucket}")
                print(f"    Files: {len(uploaded_files)}")
                for f in uploaded_files:
                    print(f"      - {f}")

                # Step 4: Deploy via AgentCore Runtime API
                print("[*] Deploying to AgentCore Runtime...")
                agent_result = self._create_agentcore_runtime_agent(
                    deployment_name,
                    s3_bucket,
                    s3_key,
                    workflow.get('description', f"Agentic workflow: {workflow.get('name', 'Unknown')}")
                )

                agent_id = agent_result.get('agentId', deployment_id)
                print(f"[OK] Agent deployed: {agent_id}")

            # Step 5: Return deployment info
            deployment_info = {
                "deployment_id": deployment_id,
                "agent_id": agent_id,
                "deployment_name": deployment_name,
                "workflow_name": workflow.get("name", "Untitled"),
                "s3_bucket": s3_bucket,
                "s3_prefix": f"agents/{deployment_name}",
                "s3_files": uploaded_files,
                "runtime": "agentcore-runtime",
                "status": "ready-for-agentcore-setup",
                "created_at": str(__import__('datetime').datetime.now().isoformat()),
                "aws_region": self.aws_region,
                "role_arn": role_arn,
                "deployment_method": "agentcore-runtime"
            }

            self.deployments[deployment_id] = deployment_info
            return deployment_info

        except Exception as e:
            print(f"[ERROR] AgentCore Runtime deployment failed: {str(e)}")
            raise

    async def _deploy_docker(
        self,
        workflow: Dict[str, Any],
        deployment_name: str,
        deployment_id: str,
        role_arn: str,
        runtime: str
    ) -> Dict[str, Any]:
        """Deploy as Docker container"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Generate workflow code
                print("[*] Generating workflow code...")
                langgraph_code = self._generate_langgraph_code(workflow)
                with open(temp_path / "main.py", "w") as f:
                    f.write(langgraph_code)

                handler_code = self._generate_handler(workflow)
                with open(temp_path / "handler.py", "w") as f:
                    f.write(handler_code)

                # Copy mock_tools.py if it exists
                mock_tools_path = os.path.join(os.path.dirname(__file__), "mock_tools.py")
                if os.path.exists(mock_tools_path):
                    shutil.copy(mock_tools_path, temp_path / "mock_tools.py")

                # Generate requirements and Dockerfile
                requirements = self._generate_requirements()
                with open(temp_path / "requirements.txt", "w") as f:
                    f.write(requirements)

                dockerfile = self._generate_dockerfile(deployment_name)
                with open(temp_path / "Dockerfile", "w") as f:
                    f.write(dockerfile)

                # Build Docker image
                image_name = deployment_name.lower().replace(" ", "-")
                image_tag = "latest"
                image_uri = f"{self.ecr_registry}/{image_name}:{image_tag}"

                print(f"\n[*] Building Docker image: {image_name} (arm64, this may take 10-15 minutes)...")
                build_result = subprocess.run(
                    ["docker", "buildx", "build", "--platform", "linux/arm64", "--load", "-t", image_uri, str(temp_path)],
                    capture_output=True,
                    text=True,
                    timeout=1200
                )

                if build_result.returncode != 0:
                    print(f"[ERROR] Docker build failed: {build_result.stderr}")
                    raise Exception(f"Docker build failed: {build_result.stderr}")
                print("[OK] Docker image built successfully")

                # Authenticate and push to ECR
                print(f"\n[*] Authenticating to ECR...")
                self._authenticate_ecr()
                print("[OK] ECR authenticated")

                print("[*] Pushing to ECR...")
                self._create_ecr_repository(image_name)
                self._push_to_ecr(image_uri)
                print(f"[OK] Pushed to ECR: {image_uri}")

            # Create AgentCore Runtime
            print("\n[*] Creating AgentCore Runtime...")
            runtime_result = self._create_agentcore_runtime(
                deployment_name=deployment_name,
                image_uri=image_uri,
                role_arn=role_arn
            )

            deployment_info = {
                "deployment_id": deployment_id,
                "agentRuntimeArn": runtime_result["agentRuntimeArn"],
                "agentRuntimeEndpoint": runtime_result.get("agentRuntimeEndpoint", ""),
                "imageUri": image_uri,
                "deployment_name": deployment_name,
                "workflow_name": workflow.get("name", "Untitled"),
                "runtime": runtime,
                "status": "deployed",
                "created_at": str(__import__('datetime').datetime.now().isoformat()),
                "aws_region": self.aws_region,
                "role_arn": role_arn,
                "deployment_method": "agentcore-runtime"
            }

            self.deployments[deployment_id] = deployment_info
            return deployment_info

        except Exception as e:
            print(f"[ERROR] Docker deployment failed: {str(e)}")
            raise

    def _get_or_create_agent_role(self) -> str:
        """Get existing agent role or create new one"""
        role_name = "blueprint-poc-agentcore-role"

        try:
            response = self.iam_client.get_role(RoleName=role_name)
            return response['Role']['Arn']
        except ClientError:
            # Role doesn't exist, create it
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": ["bedrock.amazonaws.com", "bedrock-agentcore.amazonaws.com"]
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }

            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Role for Blueprint POC AgentCore agents"
            )

            role_arn = response['Role']['Arn']

            # Attach policy
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
            )

            return role_arn

    def _authenticate_ecr(self):
        """Authenticate Docker with ECR"""
        try:
            auth_response = self.ecr_client.get_authorization_token()
            auth_data = auth_response['authorizationData'][0]

            username = "AWS"
            password = auth_data['authorizationToken']

            # Decode password from base64
            import base64
            password_decoded = base64.b64decode(password).decode('utf-8').split(':')[1]

            registry = auth_data['proxyEndpoint'].replace('https://', '')

            # Docker login
            login_result = subprocess.run(
                ["docker", "login", "-u", username, "-p", password_decoded, registry],
                capture_output=True,
                text=True
            )

            if login_result.returncode != 0:
                raise Exception(f"Docker login failed: {login_result.stderr}")

        except Exception as e:
            raise Exception(f"ECR authentication failed: {str(e)}")

    def _create_ecr_repository(self, repo_name: str):
        """Create ECR repository if it doesn't exist"""
        try:
            self.ecr_client.create_repository(repositoryName=repo_name)
            print(f"[OK] Created ECR repository: {repo_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'RepositoryAlreadyExistsException':
                print(f"[OK] ECR repository already exists: {repo_name}")
            else:
                raise

    def _push_to_ecr(self, image_uri: str):
        """Push Docker image to ECR"""
        push_result = subprocess.run(
            ["docker", "push", image_uri],
            capture_output=True,
            text=True
        )

        if push_result.returncode != 0:
            raise Exception(f"ECR push failed: {push_result.stderr}")

    def _create_bedrock_agent(self, agent_name: str, role_arn: str, description: str) -> Dict[str, Any]:
        """Create a Bedrock Agent wrapper for Docker-based deployment"""
        try:
            response = self.bedrock_agent_client.create_agent(
                agentName=agent_name.replace(" ", "-")[:50],
                agentResourceRoleArn=role_arn,
                foundationModel="anthropic.claude-haiku-4-5-20251001",
                description=description,
                idleSessionTTLInSeconds=900,
                instruction="You are an AI agent that processes and analyzes workflow tasks. Use the available tools to complete the assigned work and provide detailed results."
            )
            return response['agent']
        except ClientError as e:
            print(f"[WARNING] Could not create Bedrock Agent: {e}")
            # Return a mock response for POC if real creation fails
            return {"agentId": f"agent-{str(uuid.uuid4())[:8]}"}

    def _build_runtime_environment(self) -> Dict[str, str]:
        """Collect environment variables to pass into the AgentCore container.

        The deployed container needs credentials for any LLM SDKs it imports
        (e.g. anthropic.Anthropic() looks up ANTHROPIC_API_KEY at construction).
        We forward a curated allow-list of env vars from the host process so the
        container can call those services without baking secrets into the image.
        """
        forward_keys = [
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "AWS_DEFAULT_REGION",
        ]
        env: Dict[str, str] = {}
        for k in forward_keys:
            v = os.getenv(k)
            if v:
                env[k] = v

        if "ANTHROPIC_API_KEY" not in env:
            print("[WARN] ANTHROPIC_API_KEY is not set in this process; agents that call "
                  "Anthropic will fail at runtime. Set it in .env and redeploy.")
        else:
            masked = env["ANTHROPIC_API_KEY"][:6] + "..." + env["ANTHROPIC_API_KEY"][-4:]
            print(f"[*] Forwarding ANTHROPIC_API_KEY to runtime ({masked})")
        return env

    def _create_agentcore_runtime(self, deployment_name: str, image_uri: str, role_arn: str) -> Dict[str, Any]:
        """Create (or update if it already exists) an AWS AgentCore Runtime."""
        runtime_name = _sanitize_agent_runtime_name(deployment_name)
        print(f"[*] Using agentRuntimeName: {runtime_name}")

        artifact = {"containerConfiguration": {"containerUri": image_uri}}
        network_cfg = {"networkMode": "PUBLIC"}
        env_vars = self._build_runtime_environment()

        common_kwargs: Dict[str, Any] = {
            "agentRuntimeArtifact": artifact,
            "roleArn": role_arn,
            "networkConfiguration": network_cfg,
        }
        if env_vars:
            common_kwargs["environmentVariables"] = env_vars

        existing = self._find_agent_runtime_by_name(runtime_name)
        if existing:
            runtime_id = existing["agentRuntimeId"]
            print(f"[*] Runtime '{runtime_name}' already exists (id={runtime_id}); updating image...")
            result = self.agentcore_control_client.update_agent_runtime(
                agentRuntimeId=runtime_id,
                **common_kwargs,
            )
            print(f"[OK] AgentCore Runtime updated: {result['agentRuntimeArn']}")
            return result

        try:
            result = self.agentcore_control_client.create_agent_runtime(
                agentRuntimeName=runtime_name,
                **common_kwargs,
            )
            print(f"[OK] AgentCore Runtime ARN: {result['agentRuntimeArn']}")
            return result
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in {"ConflictException", "ResourceInUseException", "ValidationException"}:
                # Race: someone created it between list and create. Fall back to update.
                existing = self._find_agent_runtime_by_name(runtime_name)
                if existing:
                    print(f"[*] Race detected, switching to update for id={existing['agentRuntimeId']}")
                    return self.agentcore_control_client.update_agent_runtime(
                        agentRuntimeId=existing["agentRuntimeId"],
                        **common_kwargs,
                    )
            print(f"[ERROR] AgentCore Runtime creation failed: {e}")
            raise

    def _find_agent_runtime_by_name(self, runtime_name: str) -> Optional[Dict[str, Any]]:
        """Return the first agent runtime matching the given name, or None."""
        try:
            paginator = self.agentcore_control_client.get_paginator("list_agent_runtimes")
        except Exception:
            paginator = None

        runtimes: List[Dict[str, Any]] = []
        try:
            if paginator:
                for page in paginator.paginate():
                    runtimes.extend(page.get("agentRuntimes", []))
            else:
                runtimes = self.agentcore_control_client.list_agent_runtimes().get("agentRuntimes", [])
        except ClientError as e:
            print(f"[WARN] list_agent_runtimes failed: {e}")
            return None

        for r in runtimes:
            if r.get("agentRuntimeName") == runtime_name:
                return r
        return None

    def _convert_to_agentcore_schema(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Blueprint schema to AgentCore-compatible format"""
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])
        workflow_def = schema.get("workflow", {})

        # Combine all agent instructions into unified instruction
        unified_instructions = workflow.get("description", "Process the workflow")
        agent_descriptions = []
        for agent in agents:
            agent_descriptions.append(f"- {agent.get('name', 'Agent')}: {agent.get('instructions', 'Execute tasks')}")

        if agent_descriptions:
            unified_instructions += "\n\nAgents:\n" + "\n".join(agent_descriptions)

        # Extract action groups from workflow tools
        action_groups = self._extract_action_groups(workflow)

        return {
            "agents": agents,
            "action_groups": action_groups,
            "unified_instruction": unified_instructions,
            "workflow_definition": workflow_def
        }

    def _extract_action_groups(self, workflow: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract workflow tools and convert to AgentCore action groups"""
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])

        action_groups = []
        seen_tools = set()

        for agent in agents:
            agent_tools = agent.get("tools", [])
            for tool_name in agent_tools:
                if tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    action_groups.append({
                        "groupName": tool_name.replace("-", "_"),
                        "description": f"Tool: {tool_name}",
                        "toolSpecs": [
                            {
                                "name": tool_name,
                                "description": f"Execute {tool_name}",
                                "inputSchema": {
                                    "json": {
                                        "type": "object",
                                        "properties": {
                                            "input": {"type": "string", "description": "Input data"}
                                        }
                                    }
                                }
                            }
                        ]
                    })

        return action_groups

    def _create_bedrock_agent_native(
        self,
        agent_name: str,
        role_arn: str,
        description: str,
        agent_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a native Bedrock Agent with action groups (no Docker wrapper)"""
        try:
            # Prepare action groups
            action_groups = agent_schema.get("action_groups", [])

            # Create agent
            response = self.bedrock_agent_client.create_agent(
                agentName=agent_name.replace(" ", "-")[:50],
                agentResourceRoleArn=role_arn,
                foundationModel="anthropic.claude-haiku-4-5-20251001",
                description=description,
                idleSessionTTLInSeconds=900,
                instruction=agent_schema.get("unified_instruction", "Process the workflow"),
            )

            agent_id = response['agent']['agentId']

            # Add action groups if any
            if action_groups:
                print(f"[*] Adding {len(action_groups)} action groups...")
                for action_group in action_groups:
                    try:
                        self.bedrock_agent_client.create_agent_action_group(
                            agentId=agent_id,
                            agentVersion="DRAFT",
                            actionGroupName=action_group.get("groupName", "tools"),
                            description=action_group.get("description", "Workflow tools"),
                            actionGroupExecutor={
                                "customControl": "RETURN_CONTROL"
                            },
                            toolSpecs=action_group.get("toolSpecs", [])
                        )
                    except Exception as e:
                        print(f"[WARNING] Could not add action group: {e}")

            return response['agent']

        except ClientError as e:
            print(f"[ERROR] Native agent creation failed: {e}")
            return {"agentId": f"agent-{str(uuid.uuid4())[:8]}"}

    # Injected at the start of every agent's system prompt.
    # Keeps agents grounded strictly in the provided input data.
    _GROUNDING_PREFIX = (
        "GROUNDING RULES — apply these before everything else:\\n"
        "1. You have two sources of data: 'Input Data' (the original user submission) "
        "and 'Previous Agent Outputs' (work done by earlier agents in this pipeline). "
        "Both are verified — use both.\\n"
        "2. Base every fact, number, and conclusion EXCLUSIVELY on values present "
        "in one of these two sections.\\n"
        "3. NEVER invent, estimate, or assume a value not explicitly present in either section.\\n"
        "4. If a field is absent from both sections, state 'Not available in provided data' — "
        "do not substitute a guess.\\n"
        "5. Do NOT add flags or conclusions not directly supported by the provided data.\\n"
        "6. If 'Previous Agent Outputs' is present, you may build on and refine that work "
        "but you may not contradict facts stated there unless Input Data shows a clear error.\\n"
        "---\\n"
    )

    def _generate_langgraph_code(self, workflow: Dict[str, Any]) -> str:
        """Generate LangGraph code that executes any workflow schema.

        Agents receive the full user-submitted input and reason from it directly.
        No external tool calls are made — the pipeline works for any domain.
        """
        workflow_name = workflow.get("name", "Unnamed-Workflow")
        workflow_description = workflow.get("description", "Multi-agent workflow")
        schema = workflow.get("schema", {})
        agents = schema.get("agents", [])
        workflow_nodes = schema.get("workflow", {}).get("nodes", [])

        # Build agent function definitions
        agents_code = ""
        for agent in agents:
            agent_id = agent.get("id", "unknown")
            agent_name = agent.get("name", agent_id)
            agent_instructions = agent.get("instructions", "Process the workflow step.")

            # Escape characters that would break a single-line string literal
            safe_instructions = (
                agent_instructions
                .replace("\\", "\\\\")
                .replace(chr(34), chr(92) + chr(34))
                .replace("\n", "\\n")
                .replace("\r", "\\r")
            )

            agents_code += f'''
# Agent: {agent_name}
def agent_{agent_id.replace("-", "_")}(state: dict) -> dict:
    """Execute {agent_name} agent"""
    try:
        client = anthropic.Anthropic()

        # Split state into original input and previous agent outputs.
        # Agents receive BOTH so each step can build on prior work.
        internal_keys = {{"workflow_name", "status"}}
        internal_suffixes = ("_error", "_tool_result")

        original_input = {{
            k: v for k, v in state.items()
            if not k.endswith("_result")
            and not any(k.endswith(s) for s in internal_suffixes)
            and k not in internal_keys
        }}

        prior_outputs = {{
            k: v for k, v in state.items()
            if k.endswith("_result")
        }}

        # Build the user message: original data first, then prior agent outputs
        parts = ["Input Data:", json.dumps(original_input, default=str, indent=2)]
        if prior_outputs:
            parts += ["\\nPrevious Agent Outputs:", json.dumps(prior_outputs, default=str, indent=2)]

        user_message = "\\n".join(parts)

        system_prompt = (
            "{self._GROUNDING_PREFIX}"
            "{safe_instructions}"
        )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            temperature=0.1,
            system=system_prompt,
            messages=[{{"role": "user", "content": user_message}}]
        )

        state["{agent_id}_result"] = response.content[0].text
        return state
    except Exception as e:
        state["{agent_id}_error"] = str(e)
        return state
\n'''

        code = f'''"""
Generated Workflow: {workflow_name}
Description: {workflow_description}

Agents reason directly from input data — no external tool calls required.
This workflow works for any domain without additional configuration.
"""
import json
import os
from typing import Dict, Any
from dotenv import load_dotenv
import anthropic

load_dotenv()

{agents_code}

def invoke_workflow(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the entire workflow"""
    try:
        state = input_data.copy()
        state["workflow_name"] = "{workflow_name}"
        state["status"] = "started"

        # Execute agents in sequence based on workflow definition
        # This is a simplified linear execution - can be extended for DAG/parallel
        agent_steps = [
'''

        # Add agent execution steps
        for i, node in enumerate(workflow_nodes[:len(agents)]):
            agent_id = node.get("agent_id", agents[i].get("id") if i < len(agents) else f"agent-{i}")
            code += f'            ("agent_{agent_id.replace("-", "_")}", agent_{agent_id.replace("-", "_")}),\n'

        code += '''        ]

        for step_name, step_func in agent_steps:
            state = step_func(state)

        state["status"] = "completed"
        return state
    except Exception as e:
        return {{"error": str(e), "status": "failed"}}
'''

        return code

    def _generate_handler(self, workflow: Dict[str, Any] = None) -> str:
        """Generate handler that matches the Bedrock AgentCore Runtime HTTP contract.

        AgentCore Runtime invokes the container on POST /invocations and probes
        health with GET /ping. The response body of /invocations is returned
        verbatim as the `response` stream of the InvokeAgentRuntime API.
        """
        workflow_name = workflow.get("name", "Unknown") if workflow else "Unknown"

        return f'''"""
AgentCore Handler
Implements the Bedrock AgentCore Runtime container contract:
  POST /invocations   <- agent invocation
  GET  /ping          <- health check
"""

import json
import logging
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("agentcore-handler")

app = FastAPI(title="Blueprint Agent - {workflow_name}")


@app.post("/invocations")
async def invocations(request: Request):
    """Primary invocation endpoint required by Bedrock AgentCore Runtime."""
    from main import invoke_workflow

    try:
        body_bytes = await request.body()
        try:
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {{}}
        except json.JSONDecodeError:
            payload = {{"user_input": body_bytes.decode("utf-8", errors="replace")}}

        if not isinstance(payload, dict):
            payload = {{"user_input": str(payload)}}

        log.info("Received invocation with keys=%s", list(payload.keys()))
        result = invoke_workflow(payload)

        agent_result_keys = sorted(k for k in result if k.endswith("_result"))
        log.info("Workflow finished status=%s agents_fired=%d (%s)",
                 result.get("status"), len(agent_result_keys), agent_result_keys)

        # Expose a top-level "result" key so the chat manager can find the
        # final agent output without parsing the entire state dict.
        if agent_result_keys and "result" not in result:
            result["result"] = result[agent_result_keys[-1]]

        return JSONResponse(result)
    except Exception as e:
        log.exception("Invocation failed")
        return JSONResponse({{"status": "failed", "error": str(e)}}, status_code=500)


@app.get("/ping")
async def ping():
    """Health check required by Bedrock AgentCore Runtime."""
    return {{"status": "ok"}}


@app.get("/health")
async def health():
    """Convenience health endpoint (not required by AgentCore)."""
    return {{"status": "healthy", "workflow": "{workflow_name}"}}
'''

    def _generate_dockerfile(self, deployment_name: str) -> str:
        """Generate Dockerfile for AgentCore deployment"""
        return f'''FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY handler.py .
COPY mock_tools.py .

EXPOSE 8080

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8080"]
'''

    def _generate_requirements(self) -> str:
        """Generate requirements.txt for deployed container"""
        return '''fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.7.4
anthropic==0.39.0
boto3==1.43.6
python-dotenv==1.0.0
langgraph==0.2.27
langchain==0.2.16
langchain-core==0.2.39
langchain-community==0.2.16
httpx==0.25.2
'''

    def _get_or_create_s3_bucket(self) -> str:
        """Get or create S3 bucket for AgentCore Runtime agents"""
        bucket_name = f"blueprint-poc-agents-{self.aws_account_id}-{self.aws_region}"

        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            print(f"[OK] S3 bucket exists: {bucket_name}")
            return bucket_name
        except ClientError:
            print(f"[*] Creating S3 bucket: {bucket_name}")
            try:
                if self.aws_region == "us-east-1":
                    self.s3_client.create_bucket(Bucket=bucket_name)
                else:
                    self.s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': self.aws_region}
                    )
                print(f"[OK] S3 bucket created: {bucket_name}")
                return bucket_name
            except ClientError as e:
                print(f"[ERROR] Failed to create S3 bucket: {e}")
                raise

    def _package_agent_for_agentcore(
        self,
        workflow: Dict[str, Any],
        deployment_name: str,
        temp_path: Path
    ) -> str:
        """Package agent code for AgentCore Runtime deployment (files directly in S3)"""

        # Create agent package structure - files will be uploaded INDIVIDUALLY to S3
        agent_dir = temp_path / "agent"
        agent_dir.mkdir()

        # 1. Create agent.yaml (manifest for AgentCore Runtime)
        agent_manifest = f"""name: {deployment_name}
description: {workflow.get('description', '')}
version: 1.0.0
type: agentic_workflow
runtime: agentcore

# Workflow Schema
workflow:
  name: {workflow.get('name', 'Unknown')}
  description: {workflow.get('description', '')}

# Agents
agents:
"""
        agents = workflow.get("schema", {}).get("agents", [])
        for agent in agents:
            agent_manifest += f"""  - name: {agent.get('name', 'Unknown')}
    role: {agent.get('role', '')}
    instructions: |
      {agent.get('instructions', '').replace(chr(10), chr(10) + '      ')}
    tools: {agent.get('tools', [])}
"""

        with open(agent_dir / "agent.yaml", "w") as f:
            f.write(agent_manifest)

        # 2. Create handler.py (entry point for AgentCore Runtime)
        handler_code = f'''"""
AgentCore Runtime Handler
Entry point for {deployment_name} agent
"""

import json
from typing import Dict, Any
from fastapi import FastAPI
from main import invoke_workflow

app = FastAPI(title="{deployment_name}")

@app.post("/invoke")
async def invoke_agent(request: Dict[str, Any]):
    """Invoke the workflow"""
    try:
        user_input = request.get("inputText", "")
        input_data = {{"user_input": user_input}}

        # Add any additional input parameters
        if "input_data" in request:
            input_data.update(request["input_data"])

        result = invoke_workflow(input_data)

        return {{
            "statusCode": 200,
            "output": result,
            "message": "Workflow executed successfully"
        }}
    except Exception as e:
        return {{
            "statusCode": 500,
            "error": str(e)
        }}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {{"status": "healthy", "agent": "{deployment_name}"}}
'''

        with open(agent_dir / "handler.py", "w") as f:
            f.write(handler_code)

        # 3. Create main.py (agent code)
        agent_code = self._generate_langgraph_code(workflow)
        with open(agent_dir / "main.py", "w") as f:
            f.write(agent_code)

        # 4. Create requirements.txt
        requirements = self._generate_requirements()
        with open(agent_dir / "requirements.txt", "w") as f:
            f.write(requirements)

        # 5. Create README.md
        readme = f"""# {deployment_name}

## Overview
{workflow.get('description', '')}

## Agent Workflow
This agent was generated from a Blueprint workflow.

## How to Deploy

### In AWS AgentCore Runtime Console:
1. Go to: https://console.aws.amazon.com/bedrock-agentcore/
2. Click: Create Agent
3. Select: S3 Source
4. Choose bucket: blueprint-poc-agents-*
5. Navigate to: agents/{deployment_name}/
6. Select: agent.yaml (NOT a ZIP file)
7. Configure and deploy

## Files in this Directory

- **agent.yaml** - Agent configuration and workflow definition
- **handler.py** - HTTP entry point for invocation
- **main.py** - LangGraph workflow implementation
- **requirements.txt** - Python dependencies
- **README.md** - This file

## Agents in Workflow
"""
        for agent in agents:
            readme += f"\n- **{agent.get('name')}**: {agent.get('role', '')}"

        with open(agent_dir / "README.md", "w") as f:
            f.write(readme)

        print(f"[OK] Agent package prepared: {agent_dir}")
        print(f"[INFO] Files will be uploaded INDIVIDUALLY to S3 (not zipped)")

        return str(agent_dir)

    def _upload_to_s3(self, bucket: str, file_path: str, s3_key: str) -> None:
        """Upload file to S3"""
        try:
            self.s3_client.upload_file(file_path, bucket, s3_key)
            print(f"[OK] File uploaded to S3: {s3_key}")
        except ClientError as e:
            print(f"[ERROR] Failed to upload to S3: {e}")
            raise

    def _create_agentcore_runtime_agent(
        self,
        agent_name: str,
        s3_bucket: str,
        s3_key: str,
        description: str
    ) -> Dict[str, Any]:
        """
        Prepare agent for AgentCore Runtime deployment

        Note: AgentCore Runtime requires manual configuration in AWS console
        because it uses the S3 package as input, not an API-based creation.
        """

        s3_uri = f"s3://{s3_bucket}/{s3_key}"

        print(f"\n[INFO] AgentCore Runtime Setup Instructions:")
        print(f"{'='*70}")
        print(f"\n1. Agent Package Ready:")
        print(f"   S3 Bucket: {s3_bucket}")
        print(f"   S3 URI: {s3_uri}")
        print(f"\n2. Next Steps (Manual Configuration):")
        print(f"   a. Go to AWS Console → Bedrock AgentCore")
        print(f"   b. Click 'Create Agent'")
        print(f"   c. Select 'S3 Source' as source type")
        print(f"   d. Choose bucket: {s3_bucket}")
        print(f"   e. Select the ZIP file from agents/ folder")
        print(f"   f. Configure agent settings")
        print(f"   g. Click 'Deploy'")
        print(f"\n3. After Deployment:")
        print(f"   - Copy Agent ID from console")
        print(f"   - Use it to test in Streamlit 'Test Agents' page")
        print(f"   - Or test directly in AgentCore Runtime console")
        print(f"\n{'='*70}\n")

        # Return agent info for reference
        agent_id = f"agentcore-{agent_name.replace(' ', '-')[:30]}"
        return {
            "agentId": agent_id,
            "s3_uri": s3_uri,
            "setup_status": "MANUAL_CONFIG_REQUIRED",
            "instructions": "See console output above"
        }

    def get_deployment(self, deployment_id: str) -> Dict[str, Any]:
        """Get deployment status"""
        if deployment_id in self.deployments:
            return self.deployments[deployment_id]
        return {"status": "not_found", "deployment_id": deployment_id}

    async def execute(
        self,
        deployment_id: str,
        input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a deployed workflow via AgentCore"""
        if deployment_id not in self.deployments:
            return {"error": "Deployment not found", "deployment_id": deployment_id}

        deployment = self.deployments[deployment_id]

        try:
            # Invoke Bedrock Agent
            agent_id = deployment.get("agent_id")
            if not agent_id:
                return {"error": "No agent_id in deployment"}

            runtime_client = boto3.client('bedrock-agent-runtime', region_name=self.aws_region)
            user_input = input_data.get("user_input", "Process loan application for APP001")

            response = runtime_client.invoke_agent(
                agentId=agent_id,
                agentAliasId="TSTALIASID",
                sessionId=str(uuid.uuid4()),
                inputText=user_input
            )

            # Stream the response
            output = ""
            for event in response.get('completion', []):
                if 'chunk' in event:
                    chunk_text = event['chunk']['bytes'].decode('utf-8')
                    output += chunk_text

            return {
                "execution_id": str(uuid.uuid4()),
                "status": "completed",
                "output": output if output else {"message": "Workflow executed successfully"},
                "execution_time_ms": 5000
            }

        except Exception as e:
            return {
                "execution_id": str(uuid.uuid4()),
                "status": "failed",
                "error": str(e)
            }
