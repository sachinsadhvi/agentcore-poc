"""
Loan Underwriting Multi-Agent Workflow with LangGraph
Production-ready for AWS AgentCore deployment
"""
import os
from dotenv import load_dotenv
import boto3

load_dotenv()

from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from langchain_community.chat_models import BedrockChat
from langchain_core.messages import HumanMessage, SystemMessage
import json
from datetime import datetime

# Initialize Bedrock LLM
llm = BedrockChat(
    model_id="amazon.nova-pro-v1:0",
    region_name="us-east-1",
    client=boto3.client('bedrock-runtime', region_name='us-east-1')
)

class LoanApplicationState(TypedDict):
    # Input fields
    applicant_name: str
    age: int
    annual_income: float
    loan_amount: float
    loan_term_months: int
    credit_score: int
    existing_loans: list
    total_existing_debt: float
    collateral_value: float
    collateral_type: str
    employment_status: str
    years_employed: int

    # Processing fields
    credit_data: dict
    credit_analysis: dict
    income_verification: dict
    financial_analysis: dict
    risk_score: float
    risk_level: str
    risk_details: dict
    exceptions: list
    recommendation: str
    final_summary: str

def data_gatherer_node(state: LoanApplicationState) -> dict:
    """Simulate fetching credit bureau, income docs, and bank statements"""

    credit_data = {
        "credit_score": state["credit_score"],
        "payment_history": "Good" if state["credit_score"] > 650 else "Fair",
        "accounts_open": 5,
        "total_inquiries_6m": 2,
        "delinquencies": 0 if state["credit_score"] > 700 else 1,
    }

    income_verification = {
        "annual_income": state["annual_income"],
        "income_source": "Employment",
        "employment_status": state["employment_status"],
        "years_employed": state["years_employed"],
        "monthly_income": state["annual_income"] / 12,
    }

    return {
        "credit_data": credit_data,
        "income_verification": income_verification,
    }

def credit_analyzer_node(state: LoanApplicationState) -> dict:
    """Analyze credit data and produce credit risk score"""

    credit_score = state["credit_score"]

    # Simple analysis without LLM for reliability
    if credit_score >= 750:
        credit_risk_score = 85
        assessment = "Excellent credit profile"
    elif credit_score >= 700:
        credit_risk_score = 75
        assessment = "Good credit profile"
    elif credit_score >= 650:
        credit_risk_score = 60
        assessment = "Fair credit profile"
    else:
        credit_risk_score = 40
        assessment = "Poor credit profile"

    credit_analysis = {
        "credit_risk_score": credit_risk_score,
        "credit_factors": ["Payment history", "Credit utilization", "Account age"],
        "credit_assessment": assessment
    }

    return {"credit_analysis": credit_analysis}

def financial_analyzer_node(state: LoanApplicationState) -> dict:
    """Analyze income and debt"""

    monthly_income = state["annual_income"] / 12
    monthly_debt = state["total_existing_debt"] / 12
    requested_monthly_payment = (state["loan_amount"] / state["loan_term_months"])

    dti_ratio = (monthly_debt + requested_monthly_payment) / monthly_income if monthly_income > 0 else 1.0

    # Simple analysis without LLM for reliability
    if dti_ratio < 0.36:
        financial_risk_score = 85
        assessment = "Strong financial position"
    elif dti_ratio < 0.43:
        financial_risk_score = 70
        assessment = "Acceptable financial position"
    else:
        financial_risk_score = 45
        assessment = "Concerning financial position"

    financial_analysis = {
        "financial_risk_score": financial_risk_score,
        "dti_ratio": dti_ratio,
        "financial_assessment": assessment
    }

    return {"financial_analysis": financial_analysis}

def risk_scorer_node(state: LoanApplicationState) -> dict:
    """Combine all data and produce final risk score"""

    credit_analysis = state.get("credit_analysis", {})
    financial_analysis = state.get("financial_analysis", {})

    credit_risk = credit_analysis.get("credit_risk_score", 50)
    financial_risk = financial_analysis.get("financial_risk_score", 50)
    collateral_coverage = (state["collateral_value"] / state["loan_amount"]) if state["loan_amount"] > 0 else 0

    collateral_factor = min(collateral_coverage * 100, 100)

    overall_risk_score = (credit_risk * 0.4) + (financial_risk * 0.4) + (collateral_factor * 0.2)

    if overall_risk_score >= 75:
        risk_level = "LOW"
    elif overall_risk_score >= 50:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    risk_details = {
        "risk_factors": ["Credit history", "Income stability", "Debt ratio"],
        "mitigation_strategies": ["Regular monitoring", "Collateral requirement"]
    }

    return {
        "risk_score": overall_risk_score,
        "risk_level": risk_level,
        "risk_details": risk_details
    }

def exception_flagger_node(state: LoanApplicationState) -> dict:
    """Flag exceptions and red flags"""

    exceptions = []

    if state.get("credit_data", {}).get("delinquencies", 0) > 0:
        exceptions.append({
            "severity": "HIGH",
            "type": "Payment Delinquency",
            "description": "Applicant has payment delinquencies on record"
        })

    dti_ratio = state.get("financial_analysis", {}).get("dti_ratio", 0)
    if dti_ratio > 0.43:
        exceptions.append({
            "severity": "MEDIUM",
            "type": "High DTI Ratio",
            "description": f"Debt-to-income ratio of {dti_ratio:.2%} exceeds recommended threshold"
        })

    if state["credit_score"] < 600:
        exceptions.append({
            "severity": "HIGH",
            "type": "Low Credit Score",
            "description": f"Credit score of {state['credit_score']} is below acceptable threshold"
        })

    if state["years_employed"] < 2:
        exceptions.append({
            "severity": "MEDIUM",
            "type": "Employment Tenure",
            "description": "Applicant has less than 2 years in current position"
        })

    if state["collateral_value"] > 0 and (state["collateral_value"] / state["loan_amount"]) < 0.8:
        exceptions.append({
            "severity": "MEDIUM",
            "type": "Low Collateral Coverage",
            "description": f"Collateral covers only {(state['collateral_value'] / state['loan_amount']):.1%} of loan amount"
        })

    return {"exceptions": exceptions}

def summary_generator_node(state: LoanApplicationState) -> dict:
    """Generate final underwriter summary"""

    recommendation = "CONDITIONAL"
    if state.get('risk_level') == 'LOW' and len(state.get('exceptions', [])) == 0:
        recommendation = "APPROVE"
    elif state.get('risk_level') == 'HIGH' or any(e['severity'] == 'HIGH' for e in state.get('exceptions', [])):
        recommendation = "DECLINE"

    summary = f"""
LOAN UNDERWRITING ASSESSMENT

Applicant: {state['applicant_name']}
Risk Score: {state.get('risk_score', 0):.1f}/100
Risk Level: {state.get('risk_level', 'UNKNOWN')}
Recommendation: {recommendation}

Credit Analysis: {state.get('credit_analysis', {}).get('credit_assessment', 'N/A')}
Financial Analysis: {state.get('financial_analysis', {}).get('financial_assessment', 'N/A')}

Exceptions Flagged: {len(state.get('exceptions', []))}

Decision: {recommendation} is recommended based on comprehensive risk assessment.
    """.strip()

    return {
        "recommendation": recommendation,
        "final_summary": summary
    }

def build_workflow():
    """Build the LangGraph workflow"""
    workflow = StateGraph(LoanApplicationState)

    workflow.add_node("data_gatherer", data_gatherer_node)
    workflow.add_node("credit_analyzer", credit_analyzer_node)
    workflow.add_node("financial_analyzer", financial_analyzer_node)
    workflow.add_node("risk_scorer", risk_scorer_node)
    workflow.add_node("exception_flagger", exception_flagger_node)
    workflow.add_node("summary_generator", summary_generator_node)

    workflow.add_edge(START, "data_gatherer")
    workflow.add_edge("data_gatherer", "credit_analyzer")
    workflow.add_edge("data_gatherer", "financial_analyzer")
    workflow.add_edge("credit_analyzer", "risk_scorer")
    workflow.add_edge("financial_analyzer", "risk_scorer")
    workflow.add_edge("risk_scorer", "exception_flagger")
    workflow.add_edge("exception_flagger", "summary_generator")
    workflow.add_edge("summary_generator", END)

    return workflow.compile()

def execute_loan_workflow_verbose(application_data: dict) -> tuple:
    """Execute workflow and return both results and intermediate agent outputs"""

    graph = build_workflow()

    state = {
        "applicant_name": application_data.get("applicant_name", "John Doe"),
        "age": application_data.get("age", 35),
        "annual_income": application_data.get("annual_income", 75000),
        "loan_amount": application_data.get("loan_amount", 250000),
        "loan_term_months": application_data.get("loan_term_months", 360),
        "credit_score": application_data.get("credit_score", 720),
        "existing_loans": application_data.get("existing_loans", []),
        "total_existing_debt": application_data.get("total_existing_debt", 25000),
        "collateral_value": application_data.get("collateral_value", 300000),
        "collateral_type": application_data.get("collateral_type", "Property"),
        "employment_status": application_data.get("employment_status", "Employed"),
        "years_employed": application_data.get("years_employed", 5),
        "credit_data": {},
        "credit_analysis": {},
        "income_verification": {},
        "financial_analysis": {},
        "risk_score": 0.0,
        "risk_level": "MEDIUM",
        "risk_details": {},
        "exceptions": [],
        "recommendation": "CONDITIONAL",
        "final_summary": ""
    }

    # Execute workflow and capture intermediate state at each step
    intermediate_results = {}
    result = graph.invoke(state)

    # Extract agent outputs
    intermediate_results = {
        "data_gatherer": {
            "credit_data": result.get("credit_data", {}),
            "income_verification": result.get("income_verification", {})
        },
        "credit_analyzer": {
            "credit_analysis": result.get("credit_analysis", {})
        },
        "financial_analyzer": {
            "financial_analysis": result.get("financial_analysis", {})
        },
        "risk_scorer": {
            "risk_score": result.get("risk_score", 0),
            "risk_level": result.get("risk_level", ""),
            "risk_details": result.get("risk_details", {})
        },
        "exception_flagger": {
            "exceptions": result.get("exceptions", [])
        },
        "summary_generator": {
            "recommendation": result.get("recommendation", ""),
            "final_summary": result.get("final_summary", "")
        }
    }

    final_result = {
        "applicant": result.get("applicant_name"),
        "risk_score": result.get("risk_score"),
        "risk_level": result.get("risk_level"),
        "recommendation": result.get("recommendation"),
        "exceptions": result.get("exceptions", []),
        "final_summary": result.get("final_summary"),
        "processed_at": datetime.now().isoformat()
    }

    return final_result, intermediate_results

def execute_loan_workflow(application_data: dict) -> dict:
    """Execute the loan underwriting workflow"""

    graph = build_workflow()

    state = {
        "applicant_name": application_data.get("applicant_name", "John Doe"),
        "age": application_data.get("age", 35),
        "annual_income": application_data.get("annual_income", 75000),
        "loan_amount": application_data.get("loan_amount", 250000),
        "loan_term_months": application_data.get("loan_term_months", 360),
        "credit_score": application_data.get("credit_score", 720),
        "existing_loans": application_data.get("existing_loans", []),
        "total_existing_debt": application_data.get("total_existing_debt", 25000),
        "collateral_value": application_data.get("collateral_value", 300000),
        "collateral_type": application_data.get("collateral_type", "Property"),
        "employment_status": application_data.get("employment_status", "Employed"),
        "years_employed": application_data.get("years_employed", 5),
        "credit_data": {},
        "credit_analysis": {},
        "income_verification": {},
        "financial_analysis": {},
        "risk_score": 0.0,
        "risk_level": "MEDIUM",
        "risk_details": {},
        "exceptions": [],
        "recommendation": "CONDITIONAL",
        "final_summary": ""
    }

    result = graph.invoke(state)

    return {
        "applicant": result.get("applicant_name"),
        "risk_score": result.get("risk_score"),
        "risk_level": result.get("risk_level"),
        "recommendation": result.get("recommendation"),
        "exceptions": result.get("exceptions", []),
        "final_summary": result.get("final_summary"),
        "processed_at": datetime.now().isoformat()
    }

if __name__ == "__main__":
    test_application = {
        "applicant_name": "Jane Smith",
        "age": 38,
        "annual_income": 95000,
        "loan_amount": 350000,
        "loan_term_months": 360,
        "credit_score": 750,
        "existing_loans": [],
        "total_existing_debt": 15000,
        "collateral_value": 400000,
        "collateral_type": "Property",
        "employment_status": "Employed",
        "years_employed": 8,
    }

    print("Starting Loan Underwriting Workflow...")
    print("=" * 80)
    result = execute_loan_workflow(test_application)
    print(json.dumps(result, indent=2))
