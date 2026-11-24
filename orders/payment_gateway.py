from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest
from django.utils.module_loading import import_string


class PaymentGatewayError(Exception):
    """Base exception for payment-provider failures."""


class PaymentGatewayNotConfigured(PaymentGatewayError):
    """Raised when no payment-provider adapter is configured."""


class PaymentGatewayNotFound(PaymentGatewayError):
    """Raised when a provider resource does not exist."""


class PaymentCreationRejected(PaymentGatewayError):
    """Raised when the provider definitively rejects a create-payment request."""


class PaymentCreationOutcomeUnknown(PaymentGatewayError):
    """Raised when the provider may have created a payment but the result is unknown."""


class InvalidPaymentNotification(PaymentGatewayError):
    """Raised when a provider notification is invalid or cannot be verified."""


@dataclass(frozen=True)
class PaymentSession:
    provider_payment_id: str
    payment_url: str


@dataclass(frozen=True)
class PaymentNotification:
    merchant_reference: UUID | None
    provider_payment_id: str
    status: str
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ProviderPaymentStatus:
    operation_id: str
    status: str
    amount: Decimal
    payment_link_id: str


class PaymentGateway(ABC):
    provider_name = ''

    @abstractmethod
    def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant_reference: UUID,
        order_id: int,
        receipt: dict | None,
    ) -> PaymentSession:
        """Create or retrieve a payment using merchant_reference idempotently."""

    @abstractmethod
    def parse_notification(self, request: HttpRequest) -> PaymentNotification:
        """Verify the provider notification and normalize its fields."""

    @abstractmethod
    def get_payment_status(self, operation_id: str) -> ProviderPaymentStatus:
        """Fetch the authoritative payment status from the provider."""

    @abstractmethod
    def normalize_payment_status(self, provider_status: str) -> str:
        """Map the provider status to PaymentAttempt.Status."""

    def refund_payment(
        self,
        *,
        operation_id: str,
        amount: Decimal,
    ) -> None:
        raise PaymentGatewayNotConfigured(
            'Возврат отключён до подтверждения схемы запроса Точка.API.',
        )


def get_payment_gateway() -> PaymentGateway:
    gateway_path = getattr(settings, 'PAYMENT_GATEWAY', '')
    if not gateway_path:
        raise PaymentGatewayNotConfigured('Онлайн-оплата пока не настроена.')

    gateway_class = import_string(gateway_path)
    gateway = gateway_class()
    if not isinstance(gateway, PaymentGateway) or not gateway.provider_name:
        raise PaymentGatewayNotConfigured('Некорректно настроен платёжный адаптер.')
    return gateway
