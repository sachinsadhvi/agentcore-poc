"""
Mock Tools for Loan Underwriting
Provides realistic fake data for credit bureau, income, bank statements, and analysis.

Also exposes a string-keyed dispatcher `execute_tool(tool_name, state)` that the
generated LangGraph workflow uses to call tools by their workflow-schema name
(e.g. "credit-bureau-lookup", "risk-score-calculator", etc.).

The ``browser`` / ``web-search`` tools fetch pages via Playwright CDP to AgentCore Browser
(see AWS docs: ``browser_session`` + ``connect_over_cdp``) when credentials or a CDP
WebSocket URL are available; otherwise they fall back to httpx.

Design principle: tools ALWAYS prefer real applicant data already in state over
random generation. When data must be synthesised, it is seeded deterministically
from the applicant identifier so results are stable across multiple tool calls
within the same workflow run.
"""

import json
import os
import random
import re
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional


def _applicant_id(state: Dict[str, Any]) -> str:
    """Extract a stable applicant identifier from state."""
    if not isinstance(state, dict):
        return "applicant-unknown"
    # Check nested application dict first
    app = state.get("application")
    if isinstance(app, dict):
        return (
            app.get("applicant_id")
            or app.get("applicant_name")
            or app.get("name")
            or "applicant-unknown"
        )
    # Also check top-level applicant dict (workflow state shape)
    applicant = state.get("applicant")
    if isinstance(applicant, dict):
        return applicant.get("name") or applicant.get("applicant_id") or "applicant-unknown"
    return state.get("applicant_id") or state.get("name") or "applicant-unknown"


def _seeded_rng(applicant_id: str, salt: str = "") -> random.Random:
    """Return a deterministic RNG seeded from the applicant id.

    Using a stable seed means the same applicant always gets the same
    simulated bureau / income numbers, eliminating run-to-run variance
    that previously caused downstream agents to see contradictory data.
    """
    seed_bytes = hashlib.md5(f"{applicant_id}:{salt}".encode()).digest()
    seed_int = int.from_bytes(seed_bytes, "big")
    return random.Random(seed_int)


def _parse_money(value: Any, default: int = 0) -> int:
    """Parse a money string like '$76,226' or an int/float into an int."""
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.replace("$", "").replace(",", "").strip())
        except ValueError:
            pass
    return default


def _get_applicant_field(state: Dict[str, Any], *keys: str, default=None):
    """Look up a field in state['applicant'] or state['application'] or state directly."""
    for source in (
        state.get("applicant") if isinstance(state.get("applicant"), dict) else {},
        state.get("application") if isinstance(state.get("application"), dict) else {},
        state,
    ):
        for k in keys:
            if k in source:
                return source[k]
    return default


def get_credit_bureau_data(applicant_id: str, state: Dict[str, Any] = None) -> Dict[str, Any]:
    """Mock credit bureau data lookup.

    Prefers actual credit_score already in state to avoid contradicting
    the application data the applicant submitted.
    """
    state = state or {}
    rng = _seeded_rng(applicant_id, "credit")

    # Use applicant's own credit score when available
    stated_score = _get_applicant_field(state, "credit_score", "creditScore")
    credit_score = int(stated_score) if stated_score is not None else rng.choice([620, 680, 720, 750, 780, 800])

    # Derive payment history deterministically from the score
    if credit_score >= 750:
        payment_history = rng.choice(["Excellent", "Good"])
    elif credit_score >= 700:
        payment_history = rng.choice(["Good", "Fair"])
    elif credit_score >= 650:
        payment_history = rng.choice(["Fair", "Mixed"])
    else:
        payment_history = rng.choice(["Poor", "Mixed"])

    delinquencies = 0 if credit_score >= 720 else rng.choice([0, 0, 1])

    return {
        "applicant_id": applicant_id,
        "credit_score": credit_score,
        "credit_age_years": rng.randint(2, 15),
        "payment_history": payment_history,
        "accounts_open": rng.randint(3, 8),
        "total_debt": f"${rng.randint(5000, 80000):,}",
        "delinquencies": delinquencies,
        "hard_inquiries_6m": rng.randint(0, 2),
        "source": "Mock Equifax Data",
        "data_consistent_with_application": True,
    }


def get_income_documents(applicant_id: str, state: Dict[str, Any] = None) -> Dict[str, Any]:
    """Mock income verification documents.

    Uses the applicant's stated income and employment years when present
    so agents see numbers consistent with the original application.
    """
    state = state or {}
    rng = _seeded_rng(applicant_id, "income")

    stated_income = _get_applicant_field(state, "income", "annual_income", "annualIncome")
    annual_income_int = _parse_money(stated_income, default=rng.randint(35000, 250000))

    stated_years = _get_applicant_field(state, "employment_years", "employmentYears", "tenure_years")
    tenure_months = int(stated_years) * 12 if stated_years is not None else rng.randint(6, 120)

    monthly_income_int = annual_income_int // 12

    return {
        "applicant_id": applicant_id,
        "employment_status": "Employed",
        "annual_income": f"${annual_income_int:,}",
        "monthly_income": f"${monthly_income_int:,}",
        "employment_type": rng.choice(["Full-time", "Full-time", "Contract"]),
        "employer": "ACME Corporation",
        "job_title": rng.choice(["Manager", "Engineer", "Analyst", "Consultant"]),
        "tenure_months": tenure_months,
        "documents": ["W2", "Recent Pay Stub", "Tax Return"],
        "source": "Mock IRS Verification",
        "data_consistent_with_application": True,
    }


def get_bank_statements(applicant_id: str, state: Dict[str, Any] = None) -> Dict[str, Any]:
    """Mock bank statement analysis seeded from applicant id."""
    state = state or {}
    rng = _seeded_rng(applicant_id, "bank")

    stated_income = _get_applicant_field(state, "income", "annual_income", "annualIncome")
    monthly_income_int = _parse_money(stated_income, default=60000) // 12

    avg_balance = max(5000, int(monthly_income_int * rng.uniform(1.5, 4.0)))
    avg_deposits = max(3000, int(monthly_income_int * rng.uniform(0.9, 1.1)))

    return {
        "applicant_id": applicant_id,
        "account_type": "Checking",
        "avg_balance_3m": f"${avg_balance:,}",
        "avg_monthly_deposits": f"${avg_deposits:,}",
        "monthly_nsfchecks": rng.randint(0, 1),
        "overdraft_incidents_3m": rng.randint(0, 1),
        "recent_large_deposits": 0,
        "recent_large_withdrawals": 0,
        "statements_reviewed": "Last 3 months",
        "source": "Mock Bank Statement Analysis",
        "data_consistent_with_application": True,
    }


def score_risk(
    credit_data: Dict[str, Any],
    income_data: Dict[str, Any],
    bank_data: Dict[str, Any],
    state: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Calculate loan risk score based on credit, income, and bank data"""
    state = state or {}
    credit_score = credit_data.get("credit_score", 700)
    annual_income = _parse_money(income_data.get("annual_income"), default=50000)
    avg_balance = _parse_money(bank_data.get("avg_balance_3m"), default=10000)

    # Use actual loan amount from state when available (was previously hardcoded to 200000)
    stated_loan = _get_applicant_field(state, "loan_amount", "loanAmount", "requested_amount_usd")
    loan_amount = _parse_money(stated_loan, default=200000)

    monthly_payment = (loan_amount * 0.07 / 12)  # 7% annual rate estimate
    monthly_income = annual_income / 12
    dti_ratio = (monthly_payment / monthly_income) * 100 if monthly_income > 0 else 100

    # Risk scoring
    risk_score = 100

    if credit_score >= 750:
        risk_score -= 20
    elif credit_score >= 700:
        risk_score -= 15
    elif credit_score >= 650:
        risk_score -= 10
    else:
        risk_score += 10

    if dti_ratio < 30:
        risk_score -= 15
    elif dti_ratio < 43:
        risk_score -= 10
    else:
        risk_score += 15

    if avg_balance > 50000:
        risk_score -= 10
    elif avg_balance < 5000:
        risk_score += 10

    delinquencies = credit_data.get("delinquencies", 0)
    risk_score += (delinquencies * 5)

    risk_score = max(0, min(100, risk_score))

    if risk_score < 30:
        risk_tier = "LOW"
    elif risk_score < 60:
        risk_tier = "MEDIUM"
    else:
        risk_tier = "HIGH"

    return {
        "risk_score": risk_score,
        "risk_tier": risk_tier,
        "dti_ratio": f"{dti_ratio:.1f}%",
        "debt_to_income_analysis": "Acceptable" if dti_ratio < 43 else "High",
        "liquidity_assessment": "Adequate" if avg_balance > 10000 else "Low",
        "credit_strength": "Strong" if credit_score >= 700 else "Weak"
    }

def flag_exceptions(risk_data: Dict[str, Any], credit_data: Dict[str, Any], income_data: Dict[str, Any]) -> Dict[str, Any]:
    """Identify exception flags for underwriter review"""
    flags: List[str] = []
    severity: List[str] = []

    credit_score = credit_data.get("credit_score", 700)
    risk_score = risk_data.get("risk_score", 50)
    delinquencies = credit_data.get("delinquencies", 0)
    dti = float(risk_data.get("dti_ratio", "30").replace("%", ""))

    if credit_score < 650:
        flags.append("Low credit score")
        severity.append("HIGH")

    if delinquencies > 0:
        flags.append(f"Payment delinquencies: {delinquencies}")
        severity.append("MEDIUM")

    if dti > 43:
        flags.append("Debt-to-income ratio exceeds threshold")
        severity.append("HIGH")

    if risk_score > 70:
        flags.append("Overall risk profile elevated")
        severity.append("MEDIUM")

    employment_status = income_data.get("employment_status", "")
    if employment_status in ["Self-Employed"]:
        flags.append("Self-employment requires additional documentation")
        severity.append("LOW")

    if not flags:
        flags.append("No exceptions flagged")
        severity.append("INFO")

    return {
        "exception_count": len(flags),
        "flags": flags,
        "severity_levels": severity,
        "requires_review": len(flags) > 1 or any(s == "HIGH" for s in severity),
        "recommended_action": "Approve with conditions" if len(flags) == 1 else "Refer to senior underwriter" if any(s == "HIGH" for s in severity) else "Approve"
    }

def generate_underwriter_summary(all_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive underwriter summary"""
    credit_data = all_data.get("credit_data", {})
    income_data = all_data.get("income_data", {})
    bank_data = all_data.get("bank_data", {})
    risk_data = all_data.get("risk_data", {})
    exception_data = all_data.get("exception_data", {})

    recommendation = exception_data.get("recommended_action", "Review")

    summary = f"""
LOAN UNDERWRITING SUMMARY
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Applicant ID: {credit_data.get('applicant_id', 'N/A')}

CREDIT PROFILE:
- Credit Score: {credit_data.get('credit_score', 'N/A')}
- Payment History: {credit_data.get('payment_history', 'N/A')}
- Delinquencies: {credit_data.get('delinquencies', 0)}

INCOME VERIFICATION:
- Status: {income_data.get('employment_status', 'N/A')}
- Annual Income: {income_data.get('annual_income', 'N/A')}
- Tenure: {income_data.get('tenure_months', 0)} months

FINANCIAL POSITION:
- Average Balance (3m): {bank_data.get('avg_balance_3m', 'N/A')}
- DTI Ratio: {risk_data.get('dti_ratio', 'N/A')}
- Credit Strength: {risk_data.get('credit_strength', 'N/A')}

RISK ASSESSMENT:
- Overall Risk Score: {risk_data.get('risk_score', 'N/A')}/100
- Risk Tier: {risk_data.get('risk_tier', 'N/A')}
- Exceptions Flagged: {exception_data.get('exception_count', 0)}

EXCEPTIONS:
{chr(10).join([f'- {flag}' for flag in exception_data.get('flags', [])])}

UNDERWRITER RECOMMENDATION: {recommendation}

This is a comprehensive analysis for underwriter review and approval.
    """

    return {
        "summary": summary.strip(),
        "recommendation": recommendation,
        "risk_tier": risk_data.get("risk_tier", "MEDIUM"),
        "requires_manual_review": exception_data.get("requires_review", False),
        "timestamp": datetime.now().isoformat()
    }


# =============================================================================
# Ecommerce / Fraud domain mock tools
# These cover workflows that deal with order risk, transaction fraud, user
# behaviour analysis, and inventory/fulfilment checks.
# =============================================================================

def _get_order_field(state: Dict[str, Any], *keys, default=None):
    """Read a field from state['order'], state['payment'], state['user'], or top-level."""
    for source_key in ("order", "payment", "user", "transaction"):
        src = state.get(source_key)
        if isinstance(src, dict):
            for k in keys:
                if k in src:
                    return src[k]
    for k in keys:
        if k in state:
            return state[k]
    return default


def get_fraud_score(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mock fraud scoring service — derives score from state data when present."""
    rng = _seeded_rng(_applicant_id(state) or "order", "fraud")

    address_mismatch = _get_order_field(state, "address_mismatch", default=False)
    is_first_card = _get_order_field(state, "is_first_time_card", "first_time_card", default=False)
    chargebacks = _get_order_field(state, "chargebacks", default=0)
    account_age = _get_order_field(state, "account_age_days", "account_age", default=180)
    returns = _get_order_field(state, "returns_last_30_days", "recent_returns", default=0)

    # Deterministic score based on risk signals
    fraud_score = 10
    if address_mismatch:
        fraud_score += 30
    if is_first_card:
        fraud_score += 20
    if int(chargebacks) > 0:
        fraud_score += int(chargebacks) * 25
    if int(account_age) < 30:
        fraud_score += 20
    elif int(account_age) < 90:
        fraud_score += 10
    if int(returns) > 2:
        fraud_score += 10
    fraud_score = min(100, fraud_score + rng.randint(0, 5))

    return {
        "fraud_score": fraud_score,
        "fraud_risk": "HIGH" if fraud_score >= 60 else "MEDIUM" if fraud_score >= 30 else "LOW",
        "signals_detected": [
            s for s, cond in [
                ("address_mismatch", address_mismatch),
                ("first_time_card", is_first_card),
                ("chargeback_history", int(chargebacks) > 0),
                ("new_account", int(account_age) < 30),
                ("high_returns", int(returns) > 2),
            ] if cond
        ],
        "recommendation": "BLOCK" if fraud_score >= 70 else "REVIEW" if fraud_score >= 40 else "APPROVE",
        "source": "Mock Fraud Scoring Engine",
    }


def get_velocity_check(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mock velocity checker — flags unusually high transaction frequency."""
    rng = _seeded_rng(_applicant_id(state) or "order", "velocity")
    account_age = int(_get_order_field(state, "account_age_days", default=180))

    txn_24h = _get_order_field(state, "velocity_24h", "transactions_24h", default=rng.randint(1, 5))
    txn_7d  = _get_order_field(state, "velocity_7d",  "transactions_7d",  default=rng.randint(3, 15))

    return {
        "transactions_last_24h": int(txn_24h),
        "transactions_last_7d": int(txn_7d),
        "velocity_flag": int(txn_24h) > 5 or int(txn_7d) > 20,
        "account_age_days": account_age,
        "assessment": "NORMAL" if int(txn_24h) <= 5 else "ELEVATED",
        "source": "Mock Velocity Check Service",
    }


def get_order_risk_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate order risk from fraud + velocity results already in state."""
    fraud = _resolve_tool_result(state, "fraud-score-checker",
                                 lambda s: get_fraud_score(s))
    velocity = _resolve_tool_result(state, "velocity-checker",
                                    lambda s: get_velocity_check(s))

    fraud_score = fraud.get("fraud_score", 0)
    velocity_flag = velocity.get("velocity_flag", False)
    overall_risk = "HIGH" if fraud_score >= 60 or velocity_flag else \
                   "MEDIUM" if fraud_score >= 30 else "LOW"

    return {
        "overall_risk": overall_risk,
        "fraud_score": fraud_score,
        "fraud_recommendation": fraud.get("recommendation", "REVIEW"),
        "velocity_flag": velocity_flag,
        "action": "BLOCK" if overall_risk == "HIGH" else
                  "MANUAL_REVIEW" if overall_risk == "MEDIUM" else "APPROVE",
        "source": "Mock Order Risk Aggregator",
    }


def _aws_kb_server(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mock AWS Knowledge Base lookup."""
    app = state.get("application", {}) if isinstance(state, dict) else {}
    return {
        "kb_documents_found": random.randint(3, 12),
        "relevant_policies": [
            "Loan-Underwriting-Standards-v3.2",
            "KYC-Compliance-Policy",
            "Risk-Tiering-Matrix",
        ],
        "applicant_summary": {
            "name": app.get("applicant_name", "N/A"),
            "requested_amount": app.get("requested_amount_usd"),
            "purpose": app.get("purpose"),
        },
        "source": "Mock AWS Knowledge Base",
    }


def _extract_fetch_urls(state: Dict[str, Any]) -> List[str]:
    """Collect HTTP(S) URLs from common workflow input keys."""
    urls: List[str] = []
    if not isinstance(state, dict):
        return urls
    tu = state.get("target_urls")
    if isinstance(tu, list):
        for u in tu:
            if isinstance(u, str) and u.startswith(("http://", "https://")):
                urls.append(u.strip())
    for key in ("url", "browser_url", "website_url", "page_url"):
        u = state.get(key)
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            urls.append(u.strip())
    seen: set[str] = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _strip_html_to_text(html: str, max_len: int = 120_000) -> str:
    if not html:
        return ""
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len]


def _fetch_robots_txt_excerpt(state: Dict[str, Any]) -> Optional[str]:
    ru = state.get("robots_txt_url") if isinstance(state, dict) else None
    if not isinstance(ru, str) or not ru.startswith(("http://", "https://")):
        return None
    try:
        import httpx

        r = httpx.get(ru, timeout=15.0, follow_redirects=True)
        if r.status_code == 200:
            return (r.text or "")[:8000]
        return f"(robots.txt HTTP {r.status_code})"
    except Exception as e:
        return f"(robots.txt fetch failed: {e})"


def _fetch_url_httpx(url: str) -> Dict[str, Any]:
    import httpx

    headers = {
        "User-Agent": os.environ.get(
            "BLUEPRINT_FETCH_USER_AGENT",
            "BlueprintPOC/1.0 (+https://github.com/aws-samples; research)",
        )
    }
    try:
        r = httpx.get(url, timeout=30.0, follow_redirects=True, headers=headers)
        text = _strip_html_to_text(r.text or "")
        return {
            "fetched_content": text or "(empty response body)",
            "fetched_url": str(r.url),
            "http_status": r.status_code,
            "blocked_pages": [],
            "pagination_info": "Not available in provided data",
            "auth_required": r.status_code in (401, 403),
            "browser_source": "httpx",
        }
    except Exception as e:
        return {
            "fetched_content": "Not available in provided data",
            "fetch_error": str(e),
            "fetched_url": url,
            "blocked_pages": [],
            "pagination_info": "Not available in provided data",
            "auth_required": False,
            "browser_source": "httpx-error",
        }


def _fetch_url_playwright_agentcore(url: str) -> Optional[Dict[str, Any]]:
    """Use Playwright over AgentCore Browser CDP (official pattern).

    1) If ``AGENTCORE_BROWSER_CDP_WS_URL`` or ``AGENTCORE_AUTOMATION_WS_URL`` is set (e.g. injected
       by AgentCore Runtime UI), connect with optional ``AGENTCORE_BROWSER_CDP_HEADERS_JSON``.
    2) Else use ``bedrock_agentcore.tools.browser_client.browser_session`` + ``generate_ws_headers()``
       (requires IAM + ``bedrock-agentcore`` package + managed Browser in the account).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    ws_url = os.environ.get("AGENTCORE_BROWSER_CDP_WS_URL") or os.environ.get(
        "AGENTCORE_AUTOMATION_WS_URL"
    )
    headers: Optional[Dict[str, str]] = None
    raw_h = os.environ.get("AGENTCORE_BROWSER_CDP_HEADERS_JSON")
    if raw_h:
        try:
            parsed = json.loads(raw_h)
            if isinstance(parsed, dict):
                headers = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass

    if not ws_url:
        try:
            from bedrock_agentcore.tools.browser_client import browser_session

            region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "us-east-1"
            with browser_session(region) as bclient:
                ws_url, hdrs = bclient.generate_ws_headers()
                if hdrs and isinstance(hdrs, dict):
                    headers = {str(k): str(v) for k, v in hdrs.items()}
        except Exception:
            return None

    if not ws_url:
        return None

    out: Dict[str, Any] = {}
    try:
        with sync_playwright() as p:
            connect_kw: Dict[str, Any] = {}
            if headers:
                connect_kw["headers"] = headers
            browser = p.chromium.connect_over_cdp(ws_url, **connect_kw)
            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                html = page.content()
                text = _strip_html_to_text(html)
                out = {
                    "fetched_content": text or "(empty body)",
                    "fetched_html": (html or "")[:80_000],
                    "fetched_url": page.url,
                    "page_title": page.title(),
                    "http_status": 200,
                    "blocked_pages": [],
                    "pagination_info": "Not available in provided data",
                    "auth_required": False,
                    "browser_source": "playwright-agentcore-cdp",
                }
            finally:
                browser.close()
        return out
    except Exception as e:
        return {
            "fetch_error": str(e),
            "fetched_url": url,
            "browser_source": "playwright-agentcore-cdp-error",
        }


def _browser_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch web content: AgentCore Browser (Playwright CDP) when available, else httpx.

    Matches AWS docs: ``chromium.connect_over_cdp(ws_url, headers=headers)`` after
    ``browser_session(region).generate_ws_headers()`` or a presigned automation WS URL in env.
    """
    urls = _extract_fetch_urls(state if isinstance(state, dict) else {})
    goal = ""
    if isinstance(state, dict):
        goal = str(state.get("goal") or state.get("browser_goal") or state.get("prompt") or "")

    if not urls:
        return {
            "fetched_content": "Not available in provided data",
            "blocked_pages": [],
            "pagination_info": "Not available in provided data",
            "auth_required": False,
            "fetch_error": "No target_urls / url / browser_url with http(s) in input state.",
            "browser_source": "none",
            "goal": goal,
        }

    primary = urls[0]
    robots_ex = _fetch_robots_txt_excerpt(state if isinstance(state, dict) else {})

    pw_result = _fetch_url_playwright_agentcore(primary)
    if pw_result and not pw_result.get("fetch_error") and pw_result.get("fetched_content"):
        if robots_ex:
            pw_result["robots_txt_excerpt"] = robots_ex
        if goal:
            pw_result["browser_goal"] = goal
        return pw_result

    http_result = _fetch_url_httpx(primary)
    if robots_ex:
        http_result["robots_txt_excerpt"] = robots_ex
    if goal:
        http_result["browser_goal"] = goal
    if pw_result and pw_result.get("fetch_error"):
        http_result["playwright_attempt_error"] = pw_result["fetch_error"]
    return http_result


def _code_interpreter_tool(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mock AgentCore Code Interpreter (POC: no real sandbox)."""
    task = ""
    if isinstance(state, dict):
        task = str(state.get("code_or_task") or state.get("code") or "")
    return {
        "stdout": (
            "Mock Code Interpreter (POC): enable AgentCore managed Code Interpreter on the runtime. "
            + (f"Task hint: {task[:200]}" if task else "")
        ).strip(),
        "artifacts": [],
        "source": "Mock AgentCore Code Interpreter",
    }


def _aws_compliance_checker(state: Dict[str, Any]) -> Dict[str, Any]:
    """Mock AWS compliance check against KYC/AML/regulatory policies."""
    checks = {
        "kyc_passed": True,
        "aml_screening": "clear",
        "ofac_sdn_match": False,
        "fair_lending_review": "passed",
        "tila_respa_disclosures": "complete",
    }
    return {
        "compliance_status": "PASS",
        "checks": checks,
        "policies_verified": ["KYC", "AML", "OFAC", "Fair-Lending", "TILA-RESPA"],
        "source": "Mock AWS Compliance Checker",
    }


def _resolve_tool_result(state: Dict[str, Any], tool_key: str, fallback_fn):
    """Return an already-computed tool result from state, or call fallback_fn(state).

    Results are keyed as '<tool-name>_tool_result' on state once persisted by the
    generated workflow. Using cached results prevents downstream tools from calling
    the random generators a second time with a different seed, which was the main
    source of numerical contradictions between agents.
    """
    cached = state.get(f"{tool_key}_tool_result")
    if isinstance(cached, dict) and cached:
        # Unwrap the {tool, status, result} envelope written by execute_tool()
        return cached.get("result", cached)
    return fallback_fn(state)


TOOL_REGISTRY = {
    # Ecommerce / fraud domain
    "fraud-score-checker":   lambda state: get_fraud_score(state),
    "fraud-scorer":          lambda state: get_fraud_score(state),
    "fraud-detection":       lambda state: get_fraud_score(state),
    "velocity-checker":      lambda state: get_velocity_check(state),
    "velocity-check":        lambda state: get_velocity_check(state),
    "order-risk-evaluator":  lambda state: get_order_risk_summary(state),
    "order-risk-calculator": lambda state: get_order_risk_summary(state),
    "transaction-validator": lambda state: get_fraud_score(state),
    # AWS / knowledge base
    "aws-kb-server": lambda state: _aws_kb_server(state),
    "browser": lambda state: _browser_tool(state),
    "web-search": lambda state: _browser_tool(state),
    "code-interpreter": lambda state: _code_interpreter_tool(state),
    "code_interpreter": lambda state: _code_interpreter_tool(state),
    "credit-bureau-lookup": lambda state: get_credit_bureau_data(_applicant_id(state), state),
    "income-document-retrieval": lambda state: get_income_documents(_applicant_id(state), state),
    "bank-statement-analysis": lambda state: get_bank_statements(_applicant_id(state), state),
    "risk-score-calculator": lambda state: score_risk(
        _resolve_tool_result(state, "credit-bureau-lookup",
                             lambda s: get_credit_bureau_data(_applicant_id(s), s)),
        _resolve_tool_result(state, "income-document-retrieval",
                             lambda s: get_income_documents(_applicant_id(s), s)),
        _resolve_tool_result(state, "bank-statement-analysis",
                             lambda s: get_bank_statements(_applicant_id(s), s)),
        state,
    ),
    "exception-flagger": lambda state: flag_exceptions(
        _resolve_tool_result(state, "risk-score-calculator", lambda s: {}),
        _resolve_tool_result(state, "credit-bureau-lookup",
                             lambda s: get_credit_bureau_data(_applicant_id(s), s)),
        _resolve_tool_result(state, "income-document-retrieval",
                             lambda s: get_income_documents(_applicant_id(s), s)),
    ),
    "underwriter-summary-generator": lambda state: generate_underwriter_summary({
        "credit_data": _resolve_tool_result(state, "credit-bureau-lookup",
                                            lambda s: get_credit_bureau_data(_applicant_id(s), s)),
        "income_data": _resolve_tool_result(state, "income-document-retrieval",
                                            lambda s: get_income_documents(_applicant_id(s), s)),
        "bank_data": _resolve_tool_result(state, "bank-statement-analysis",
                                          lambda s: get_bank_statements(_applicant_id(s), s)),
        "risk_data": _resolve_tool_result(state, "risk-score-calculator", lambda s: {}),
        "exception_data": _resolve_tool_result(state, "exception-flagger", lambda s: {}),
    }),
    "aws-compliance-checker": lambda state: _aws_compliance_checker(state),
}


def execute_tool(tool_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a workflow tool by name.

    Called by the generated LangGraph workflow (`from mock_tools import execute_tool`).
    Returns a dict result for the tool; never raises (errors are returned in the dict).
    """
    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {
            "tool": tool_name,
            "status": "unknown_tool",
            "message": f"No mock implementation registered for '{tool_name}'.",
            "available_tools": sorted(TOOL_REGISTRY.keys()),
        }
    try:
        return {"tool": tool_name, "status": "ok", "result": fn(state)}
    except Exception as e:
        return {"tool": tool_name, "status": "error", "error": str(e)}
