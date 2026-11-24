from decimal import Decimal
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import Order, PaymentAttempt
from .payment_gateway import (
    PaymentCreationOutcomeUnknown,
    PaymentCreationRejected,
    PaymentGatewayError,
    PaymentGatewayNotConfigured,
    PaymentNotification,
    PaymentSession,
    ProviderPaymentStatus,
    get_payment_gateway,
)


def start_payment(order: Order) -> PaymentAttempt:
    if order.payment_method != Order.PaymentMethod.ONLINE:
        raise PaymentGatewayError('Для этого заказа онлайн-оплата не выбрана.')

    gateway = get_payment_gateway()
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.payment_status in {
            Order.PaymentStatus.PAID,
            Order.PaymentStatus.REFUND_PENDING,
            Order.PaymentStatus.REFUNDED,
            Order.PaymentStatus.PARTIALLY_REFUNDED,
        }:
            raise PaymentGatewayError('Заказ уже оплачен или по нему начат возврат.')

        attempt, created = PaymentAttempt.objects.get_or_create(
            order=locked_order,
            status=PaymentAttempt.Status.PENDING,
            defaults={
                'provider': gateway.provider_name,
                'amount': locked_order.total,
                'currency': getattr(settings, 'PAYMENT_CURRENCY', 'RUB'),
            },
        )
        if created:
            locked_order.payment_status = Order.PaymentStatus.PENDING
            locked_order.save(update_fields=['payment_status', 'updated_at'])

    if attempt.provider != gateway.provider_name:
        raise PaymentGatewayError('Провайдер платежа не совпадает с текущей настройкой.')
    if attempt.payment_url:
        return attempt
    if attempt.creation_status != PaymentAttempt.CreationStatus.READY:
        raise PaymentCreationOutcomeUnknown(
            'Создание платежа уже выполняется или его результат нужно сверить с банком.',
        )

    claimed = PaymentAttempt.objects.filter(
        pk=attempt.pk,
        creation_status=PaymentAttempt.CreationStatus.READY,
    ).update(creation_status=PaymentAttempt.CreationStatus.SENDING)
    if not claimed:
        attempt.refresh_from_db()
        if attempt.payment_url:
            return attempt
        raise PaymentCreationOutcomeUnknown(
            'Создание платежа уже выполняется; повторный запрос не отправлен.',
        )

    try:
        session = gateway.create_payment(
            amount=attempt.amount,
            currency=attempt.currency,
            merchant_reference=attempt.idempotency_key,
            order_id=order.pk,
            receipt=build_receipt(order) if settings.TOCHKA_FISCALIZATION_ENABLED else None,
        )
    except PaymentGatewayNotConfigured:
        _set_creation_status(attempt, PaymentAttempt.CreationStatus.READY)
        raise
    except PaymentCreationRejected:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.creation_status = PaymentAttempt.CreationStatus.REJECTED
        attempt.save(update_fields=['status', 'creation_status', 'updated_at'])
        Order.objects.filter(
            pk=attempt.order_id,
            payment_status=Order.PaymentStatus.PENDING,
        ).update(payment_status=Order.PaymentStatus.FAILED)
        raise
    except PaymentCreationOutcomeUnknown:
        _set_creation_status(attempt, PaymentAttempt.CreationStatus.UNKNOWN)
        raise

    try:
        _validate_payment_session(session)
    except PaymentCreationOutcomeUnknown:
        _set_creation_status(attempt, PaymentAttempt.CreationStatus.UNKNOWN)
        raise

    attempt.provider_payment_id = session.provider_payment_id
    attempt.payment_url = session.payment_url
    attempt.creation_status = PaymentAttempt.CreationStatus.CREATED
    attempt.save(update_fields=[
        'provider_payment_id', 'payment_url', 'creation_status', 'updated_at',
    ])
    return attempt


def apply_payment_notification(
    gateway_name: str,
    notification: PaymentNotification,
) -> PaymentAttempt:
    allowed_statuses = {
        PaymentAttempt.Status.PENDING,
        PaymentAttempt.Status.PAID,
        PaymentAttempt.Status.FAILED,
        PaymentAttempt.Status.CANCELLED,
        PaymentAttempt.Status.REFUND_PENDING,
        PaymentAttempt.Status.REFUNDED,
        PaymentAttempt.Status.PARTIALLY_REFUNDED,
    }
    if notification.status not in allowed_statuses:
        raise PaymentGatewayError('Провайдер передал неизвестный статус платежа.')

    with transaction.atomic():
        attempts = PaymentAttempt.objects.select_for_update().filter(provider=gateway_name)
        if notification.merchant_reference:
            attempts = attempts.filter(idempotency_key=notification.merchant_reference)
        else:
            attempts = attempts.filter(provider_payment_id=notification.provider_payment_id)
        attempt = attempts.first()
        if attempt is None:
            raise PaymentGatewayError('Попытка оплаты не найдена.')

        if (
            attempt.amount != Decimal(notification.amount)
            or attempt.currency != notification.currency
        ):
            raise PaymentGatewayError('Сумма или валюта уведомления не совпадает с заказом.')

        if (
            attempt.provider_payment_id
            and attempt.provider_payment_id != notification.provider_payment_id
        ):
            raise PaymentGatewayError('ID платежа в уведомлении не совпадает.')

        transitions = {
            PaymentAttempt.Status.PENDING: allowed_statuses,
            PaymentAttempt.Status.FAILED: {
                PaymentAttempt.Status.FAILED,
                PaymentAttempt.Status.PAID,
            },
            PaymentAttempt.Status.CANCELLED: {
                PaymentAttempt.Status.CANCELLED,
                PaymentAttempt.Status.PAID,
            },
            PaymentAttempt.Status.PAID: {
                PaymentAttempt.Status.PAID,
                PaymentAttempt.Status.REFUND_PENDING,
                PaymentAttempt.Status.REFUNDED,
                PaymentAttempt.Status.PARTIALLY_REFUNDED,
            },
            PaymentAttempt.Status.REFUND_PENDING: {
                PaymentAttempt.Status.REFUND_PENDING,
                PaymentAttempt.Status.REFUNDED,
                PaymentAttempt.Status.PARTIALLY_REFUNDED,
            },
            PaymentAttempt.Status.REFUNDED: {PaymentAttempt.Status.REFUNDED},
            PaymentAttempt.Status.PARTIALLY_REFUNDED: {
                PaymentAttempt.Status.PARTIALLY_REFUNDED,
                PaymentAttempt.Status.REFUNDED,
            },
        }
        if notification.status not in transitions[attempt.status]:
            return attempt
        attempt.provider_payment_id = notification.provider_payment_id
        attempt.status = notification.status
        attempt.save(update_fields=['provider_payment_id', 'status', 'updated_at'])

        order = Order.objects.select_for_update().get(pk=attempt.order_id)
        if attempt.status in {
            PaymentAttempt.Status.PAID,
            PaymentAttempt.Status.REFUND_PENDING,
            PaymentAttempt.Status.REFUNDED,
            PaymentAttempt.Status.PARTIALLY_REFUNDED,
        }:
            order.payment_status = attempt.status
        elif (
            order.payment_status not in {
                Order.PaymentStatus.PAID,
                Order.PaymentStatus.REFUND_PENDING,
                Order.PaymentStatus.REFUNDED,
                Order.PaymentStatus.PARTIALLY_REFUNDED,
            }
            and not order.payment_attempts.filter(
                status=PaymentAttempt.Status.PENDING,
            ).exclude(pk=attempt.pk).exists()
        ):
            order.payment_status = attempt.status
        order.save(update_fields=['payment_status', 'updated_at'])

    return attempt


def reconcile_payment(attempt: PaymentAttempt) -> PaymentAttempt:
    if not attempt.provider_payment_id:
        raise PaymentCreationOutcomeUnknown(
            'Для этой попытки нет operationId; безопасно сверить её через API нельзя.',
        )
    gateway = get_payment_gateway()
    if attempt.provider != gateway.provider_name:
        raise PaymentGatewayError('Провайдер платежа не совпадает с текущей настройкой.')

    snapshot: ProviderPaymentStatus = gateway.get_payment_status(attempt.provider_payment_id)
    if snapshot.operation_id != attempt.provider_payment_id:
        raise PaymentGatewayError('Банк вернул другой operationId.')
    if snapshot.amount != attempt.amount:
        raise PaymentGatewayError('Сумма платежа в банке не совпадает с заказом.')
    if snapshot.payment_link_id and snapshot.payment_link_id != attempt.idempotency_key.hex:
        raise PaymentGatewayError('paymentLinkId в банке не совпадает с попыткой оплаты.')

    return apply_payment_notification(
        gateway.provider_name,
        PaymentNotification(
            merchant_reference=attempt.idempotency_key,
            provider_payment_id=snapshot.operation_id,
            status=gateway.normalize_payment_status(snapshot.status),
            amount=snapshot.amount,
            currency=attempt.currency,
        ),
    )


def request_refund(
    attempt: PaymentAttempt,
    *,
    actor,
    amount: Decimal,
) -> None:
    if not actor.has_perm('orders.refund_payment'):
        raise PermissionDenied
    if not isinstance(amount, Decimal):
        raise PaymentGatewayError('Сумму возврата нужно передавать как Decimal.')
    if attempt.status not in {
        PaymentAttempt.Status.PAID,
        PaymentAttempt.Status.PARTIALLY_REFUNDED,
    }:
        raise PaymentGatewayError('Возврат доступен только для подтверждённого платежа.')
    if amount <= 0 or amount > attempt.amount:
        raise PaymentGatewayError('Сумма возврата должна быть положительной и не превышать платёж.')
    gateway = get_payment_gateway()
    if gateway.provider_name != attempt.provider:
        raise PaymentGatewayError('Провайдер платежа не совпадает с текущей настройкой.')
    gateway.refund_payment(
        operation_id=attempt.provider_payment_id,
        amount=amount,
    )


def build_receipt(order: Order) -> dict:
    allowed_tax_systems = {
        'osn', 'usn_income', 'usn_income_outcome', 'esn', 'patent',
    }
    allowed_vat_types = {
        'none', 'vat0', 'vat5', 'vat7', 'vat10', 'vat20', 'vat22',
        'vat105', 'vat107', 'vat110', 'vat120', 'vat122',
    }
    allowed_payment_methods = {'full_payment', 'full_prepayment'}
    allowed_payment_objects = {'goods', 'service', 'work'}

    configuration = {
        'TOCHKA_TAX_SYSTEM_CODE': (
            settings.TOCHKA_TAX_SYSTEM_CODE,
            allowed_tax_systems,
        ),
        'TOCHKA_VAT_TYPE': (settings.TOCHKA_VAT_TYPE, allowed_vat_types),
        'TOCHKA_PAYMENT_METHOD': (
            settings.TOCHKA_PAYMENT_METHOD,
            allowed_payment_methods,
        ),
        'TOCHKA_PAYMENT_OBJECT': (
            settings.TOCHKA_PAYMENT_OBJECT,
            allowed_payment_objects,
        ),
    }
    for name, (value, allowed_values) in configuration.items():
        if value not in allowed_values:
            raise PaymentGatewayNotConfigured(
                f'{name} должен быть задан допустимым значением из документации Точки.',
            )
    if not order.customer_email:
        raise PaymentGatewayNotConfigured('Для кассового чека нужен email покупателя.')
    if len(settings.TOCHKA_CUSTOMER_CODE) != 9:
        raise PaymentGatewayNotConfigured('TOCHKA_CUSTOMER_CODE для чека должен содержать 9 символов.')
    if settings.TOCHKA_MERCHANT_ID and len(settings.TOCHKA_MERCHANT_ID) != 15:
        raise PaymentGatewayNotConfigured('TOCHKA_MERCHANT_ID для чека должен содержать 15 символов.')

    items = list(order.items.all())
    receipt_items = []
    calculated_total = Decimal('0')
    for item in items:
        if item.unit_price <= 0 or item.quantity <= 0:
            raise PaymentGatewayNotConfigured('В чеке должны быть положительные цена и количество.')
        addon_names = [
            addon.get('name', '') for addon in item.addons_snapshot
            if isinstance(addon, dict) and addon.get('name')
        ]
        name = item.product_name
        if addon_names:
            name = f'{name} ({", ".join(addon_names)})'
        if len(name) > 256:
            raise PaymentGatewayNotConfigured('Название позиции чека превышает 256 символов.')
        receipt_items.append({
            'name': name,
            'amount': _decimal_number(item.unit_price),
            'quantity': item.quantity,
            'vatType': settings.TOCHKA_VAT_TYPE,
            'paymentMethod': settings.TOCHKA_PAYMENT_METHOD,
            'paymentObject': settings.TOCHKA_PAYMENT_OBJECT,
            'measure': 'шт.',
        })
        calculated_total += item.unit_price * item.quantity

    if calculated_total != order.items_total:
        raise PaymentGatewayNotConfigured('Позиции заказа не совпадают с суммой товаров.')

    if order.delivery_cost > 0:
        delivery_vat = settings.TOCHKA_DELIVERY_VAT_TYPE
        delivery_object = settings.TOCHKA_DELIVERY_PAYMENT_OBJECT
        if delivery_vat not in allowed_vat_types or delivery_object not in allowed_payment_objects:
            raise PaymentGatewayNotConfigured(
                'Нужно отдельно задать НДС и объект расчёта для услуги доставки.',
            )
        receipt_items.append({
            'name': 'Доставка',
            'amount': _decimal_number(order.delivery_cost),
            'quantity': 1,
            'vatType': delivery_vat,
            'paymentMethod': settings.TOCHKA_PAYMENT_METHOD,
            'paymentObject': delivery_object,
            'measure': 'шт.',
        })
        calculated_total += order.delivery_cost

    if calculated_total != order.total or not receipt_items:
        raise PaymentGatewayNotConfigured('Сумма позиций чека не совпадает с итогом заказа.')
    return {
        'taxSystemCode': settings.TOCHKA_TAX_SYSTEM_CODE,
        'Client': {
            'email': order.customer_email,
            'name': order.customer_name,
            'phone': order.phone,
        },
        'Items': receipt_items,
    }


def _decimal_number(amount: Decimal) -> float:
    numeric_amount = float(amount)
    if Decimal(str(numeric_amount)) != amount:
        raise PaymentGatewayNotConfigured('Сумму позиции нельзя точно представить в API-формате.')
    return numeric_amount


def _validate_payment_session(session: PaymentSession) -> None:
    parsed_url = urlsplit(session.payment_url)
    if (
        not session.provider_payment_id
        or parsed_url.scheme != 'https'
        or not parsed_url.netloc
        or parsed_url.username
        or parsed_url.password
    ):
        raise PaymentCreationOutcomeUnknown(
            'Провайдер вернул неполный или некорректный ответ; повторный запрос не отправлен.',
        )


def _set_creation_status(attempt: PaymentAttempt, status: str) -> None:
    PaymentAttempt.objects.filter(pk=attempt.pk).update(creation_status=status)
