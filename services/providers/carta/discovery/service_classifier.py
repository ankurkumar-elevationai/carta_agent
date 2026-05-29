from enum import Enum
import re

class CapabilityType(str, Enum):
    HOLDINGS = "holdings"
    FINANCIALS = "financials"
    DOCUMENTS = "documents"
    VALUATIONS = "valuations"
    CAPITALIZATION = "capitalization"
    EXPORTS = "exports"
    REPORTS = "reports"
    NOTES = "notes"
    ANALYTICS = "analytics"
    UNKNOWN = "unknown"

class ServiceClassifier:
    """Classifies endpoints into strict semantic categories based on URL heuristics."""
    
    _RULES = [
        (re.compile(r"/holding|/portfolio|/investment", re.I), CapabilityType.HOLDINGS),
        (re.compile(r"/financial|/metric|/irr|/tvpi", re.I), CapabilityType.FINANCIALS),
        (re.compile(r"/document|/file|/attachment", re.I), CapabilityType.DOCUMENTS),
        (re.compile(r"/valuation|/409a|/fmv|/pricing", re.I), CapabilityType.VALUATIONS),
        (re.compile(r"/cap.?table|/equity|/share.?class|/option", re.I), CapabilityType.CAPITALIZATION),
        (re.compile(r"/export|/download", re.I), CapabilityType.EXPORTS),
        (re.compile(r"/report|/statement", re.I), CapabilityType.REPORTS),
        (re.compile(r"/note|/comment", re.I), CapabilityType.NOTES),
        (re.compile(r"/analytic|/dashboard|/chart", re.I), CapabilityType.ANALYTICS),
    ]

    @classmethod
    def classify(cls, url: str) -> CapabilityType:
        path = url.split("?")[0]
        for pattern, cap_type in cls._RULES:
            if pattern.search(path):
                return cap_type
        return CapabilityType.UNKNOWN

    @classmethod
    def infer_service(cls, url: str) -> str:
        """Infers the microservice boundary from the URL."""
        if "/api/v1/" in url:
            return "core_api"
        if "/api/fe-platform/" in url:
            return "fe_platform"
        if "/graphql" in url:
            return "graphql_gateway"
        if "s3.amazonaws.com" in url:
            return "s3_storage"
        return "unknown_service"
