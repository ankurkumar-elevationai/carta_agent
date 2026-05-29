import re
import logging
from enum import Enum
from typing import Optional, Any

log = logging.getLogger(__name__)

class CapabilityType(str, Enum):
    VALUATION = "valuation"
    PERFORMANCE = "performance"
    HOLDINGS = "holdings"
    DOCUMENTS = "documents"
    REPORTS = "reports"
    EXPORTS = "exports"
    PERMISSIONS = "permissions"
    COMPLIANCE = "compliance"
    CAP_TABLE = "cap_table"
    UNKNOWN = "unknown"

class CapabilityClassifier:
    """
    Classifies a URL into a specialized CapabilityType.
    This differs from EndpointClassifier which maps general API categories;
    this focuses on semantic graph capabilities for an Entity.
    """
    
    def __init__(self):
        # Heuristics for capability inference
        self.rules = [
            (re.compile(r"/valuation|/409a|/fmv|/pricing", re.I), CapabilityType.VALUATION),
            (re.compile(r"/performance|/metrics|/irr|/tvpi|/dpi", re.I), CapabilityType.PERFORMANCE),
            (re.compile(r"/holding|/portfolio|/investment|/position", re.I), CapabilityType.HOLDINGS),
            (re.compile(r"/document|/file|/attachment", re.I), CapabilityType.DOCUMENTS),
            (re.compile(r"/report|/statement", re.I), CapabilityType.REPORTS),
            (re.compile(r"/export|/download", re.I), CapabilityType.EXPORTS),
            (re.compile(r"/permission|/role|/access", re.I), CapabilityType.PERMISSIONS),
            (re.compile(r"/compliance|/kyc|/aml|/audit", re.I), CapabilityType.COMPLIANCE),
            (re.compile(r"/cap.?table|/equity|/share", re.I), CapabilityType.CAP_TABLE),
        ]

    def classify_route(self, url: str) -> CapabilityType:
        """Infer capability type from URL."""
        path = url.split("?")[0]
        for pattern, cap_type in self.rules:
            if pattern.search(path):
                return cap_type
        return CapabilityType.UNKNOWN

    def infer_from_schema(self, keys: set[str]) -> CapabilityType:
        """Infer capability based on specific payload keys."""
        if {"irr", "multiple", "tvpi"} & keys:
            return CapabilityType.PERFORMANCE
        if {"fmv", "price_per_share", "409a"} & keys:
            return CapabilityType.VALUATION
        if {"shares", "options", "warrants"} & keys:
            return CapabilityType.CAP_TABLE
        if {"file_name", "s3_url", "mime_type"} & keys:
            return CapabilityType.DOCUMENTS
        return CapabilityType.UNKNOWN
