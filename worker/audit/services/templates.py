"""Pre-built regulatory and commercial compliance templates."""

FINRA_REG_BI_TEMPLATE = [
    {
        "code": "FINRA_SEC_RISK_DISCLOSURE",
        "title": "Mandatory Investment Risk & Non-Guarantee Disclosure",
        "description": "Advisor must explicitly disclose that investment value fluctuates and past performance does not guarantee future results."
    },
    {
        "code": "FINRA_FEE_STRUCTURE",
        "title": "Clear Fee and Commission Explanation",
        "description": "Advisor must clearly outline advisory fee percentage, transaction charges, or custodian fees."
    },
    {
        "code": "FINRA_CLIENT_RISK_TOLERANCE",
        "title": "Documented Client Risk Profile and Time Horizon",
        "description": "Client must state or agree to their investment time horizon and risk tolerance tier (Conservative, Moderate, Aggressive)."
    },
    {
        "code": "FINRA_CONFLICT_OF_INTEREST",
        "title": "Disclosure of Material Conflicts of Interest",
        "description": "Advisor must disclose any proprietary product compensation or third-party fee sharing agreements."
    }
]

COMMERCIAL_CONTRACT_SLA_TEMPLATE = [
    {
        "code": "CONTRACT_PRICE_PROTECTION",
        "title": "Pricing Lock and Discount Duration",
        "description": "Parties must specify fee terms, discount limits, and renewal rate caps."
    },
    {
        "code": "CONTRACT_SLA_COMMITMENT",
        "title": "Service Level Agreement and Uptime Guarantee",
        "description": "Service availability commitment (e.g. 99.9%) and financial credit remedies for downtime."
    },
    {
        "code": "CONTRACT_DATA_SECURITY",
        "title": "Confidentiality and Data Protection Terms",
        "description": "Explicit commitment to SOC2/ISO/GDPR handling and NDA protections."
    }
]

GENERAL_EXECUTIVE_AUDIT_TEMPLATE = [
    {
        "code": "EXEC_FORMAL_DECISION_CONSENSUS",
        "title": "Explicit Quorum & Binding Decision Consent",
        "description": "All voting or decision-making stakeholders must voice clear approval or sign-off on key motions."
    },
    {
        "code": "EXEC_BUDGET_CAP_APPROVAL",
        "title": "Definitive Budget Authorization and Caps",
        "description": "Explicit approval of financial expenditure limits and assigned budget owner."
    }
]

TEMPLATES = {
    "FINRA_REG_BI": FINRA_REG_BI_TEMPLATE,
    "COMMERCIAL_SLA": COMMERCIAL_CONTRACT_SLA_TEMPLATE,
    "GENERAL_EXECUTIVE": GENERAL_EXECUTIVE_AUDIT_TEMPLATE,
}

