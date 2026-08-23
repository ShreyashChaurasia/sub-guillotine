"""Data schemas and Pydantic models for Sub Guillotine."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class SubscriptionStatus(str, Enum):
    """Lifecycle state machine status for a subscription."""
    MONITORING = "MONITORING"
    STAGED_FOR_CANCEL = "STAGED_FOR_CANCEL"
    CANCELLED = "CANCELLED"
    KEPT = "KEPT"
    FAILED = "FAILED"


class HITLDecisionType(str, Enum):
    """User decision in Human-in-the-Loop gate."""
    CANCEL = "CANCEL"
    KEEP = "KEEP"
    DEFER = "DEFER"


class ExtractedSubscriptionData(BaseModel):
    """Structured extraction output from Bedrock parsing raw subscription emails."""
    service_name: str = Field(..., description="Name of the service (e.g. Netflix, Adobe)")
    plan_name: Optional[str] = Field(default=None, description="Tier/Plan name (e.g. Premium Family)")
    amount: float = Field(..., ge=0.0, description="Cost of the subscription")
    currency: str = Field(default="USD", description="3-letter currency code (e.g. USD, EUR, INR)")
    billing_cycle: str = Field(default="monthly", description="Billing frequency: monthly, annual, etc.")
    renewal_date: datetime = Field(..., description="Timestamp of the upcoming renewal / charge date")
    cancellation_url: Optional[str] = Field(default=None, description="Direct URL or portal URL for cancellation")
    login_url: Optional[str] = Field(default=None, description="Login URL for the service")
    account_email: Optional[str] = Field(default=None, description="Account identifier/email in the subscription")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="LLM extraction confidence")


class SubscriptionItem(BaseModel):
    """Full database representation of a tracked subscription."""
    id: Optional[int] = Field(default=None, description="Primary key in database")
    service_name: str = Field(..., description="Name of the service")
    plan_name: Optional[str] = Field(default=None, description="Plan or tier name")
    amount: float = Field(..., ge=0.0, description="Subscription cost per billing cycle")
    currency: str = Field(default="USD", description="Currency code")
    billing_cycle: str = Field(default="monthly", description="Frequency of billing")
    renewal_date: datetime = Field(..., description="Next renewal datetime")
    cancellation_url: Optional[str] = Field(default=None, description="URL to cancel subscription")
    login_url: Optional[str] = Field(default=None, description="URL to login")
    status: SubscriptionStatus = Field(default=SubscriptionStatus.MONITORING, description="Current lifecycle state")
    proof_screenshot_path: Optional[str] = Field(default=None, description="Path to cancellation proof PNG")
    pre_cancel_screenshot_path: Optional[str] = Field(default=None, description="Path to staged pre-cancel PNG")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")

    @field_validator("currency", mode="before")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.upper() if isinstance(v, str) else "USD"


class ImminentSubscription(BaseModel):
    """Representation of an imminent subscription renewal."""
    subscription: SubscriptionItem
    hours_remaining: float = Field(..., description="Hours until renewal deadline")
    is_critical: bool = Field(default=False, description="True if within critical threshold (e.g. <= 6h)")


class HITLRequest(BaseModel):
    """Payload presented to human operator during HITL gate."""
    subscription: SubscriptionItem
    hours_until_renewal: float
    staged_screenshot_path: Optional[str] = None
    prompt_message: str


class HITLDecision(BaseModel):
    """User decision returned from HITL gate."""
    decision: HITLDecisionType
    subscription_id: int
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Optional[str] = None


class CancellationResult(BaseModel):
    """Result of an attempted subscription cancellation."""
    success: bool
    subscription_id: int
    service_name: str
    amount_saved: float
    currency: str = "USD"
    proof_screenshot_path: Optional[str] = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
