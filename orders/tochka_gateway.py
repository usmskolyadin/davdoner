import json
import socket
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)
from uuid import UUID

import jwt
from django.conf import settings

from .payment_gateway import (
    InvalidPaymentNotification,
    PaymentCreationOutcomeUnknown,
    PaymentCreationRejected,
    PaymentGateway,
    PaymentGatewayNotConfigured,
    PaymentGatewayNotFound,
    PaymentNotification,
    PaymentSession,
    ProviderPaymentStatus,
)

_PAYMENT_STATUSES = {
    'CREATED',
    'APPROVED',
    'ON-REFUND',
    'REFUNDED',
    'EXPIRED',
    'REFUNDED_PARTIALLY',
    'AUTHORIZED',
    'WAIT_FULL_PAYMENT',
}
_PAYMENT_MODES = {'sbp', 'card', 'tinkoff', 'dolyame'}
_PAYMENT_TYPES = _PAYMENT_MODES | {'digitalRuble'}
_TOCHKA_WEBHOOK_JWK = {
    'kty': 'RSA',
    'e': 'AQAB',
    'n': (
        'rwm77av7GIttq-JF1itEgLCGEZW_zz16RlUQVYlLbJtyRSu61fCec_rroP6PxjXU2u'
        'LzUOaGaLgAPeUZAJrGuVp9nryKgbZceHckdHDYgJd9TsdJ1MYUsXaOb9joN9vmsCsc'
        'Bx1lwSlFQyNQsHUsrjuDk-opf6RCuazRQ9gkoDCX70HV8WBMFoVm-YWQKJHZEaIQxg'
        '_DU4gMFyKRkDGKsYKA0POL-UgWA1qkg6nHY5BOMKaqxbc5ky87muWB5nNk4mfmsckyFv'
        '9j1gBiXLKekA_y4UwG2o1pbOLpJS3bP_c95rm4M9ZBmGXqfOQhbjz8z-s9C11i-jmOQ'
        '2ByohS-ST3E5sqBzIsxxrxyQDTw--bZNhzpbciyYW4GfkkqyeYoOPd_84jPTBDKQXss'
        'vj8ZOj2XboS77tvEO1n1WlwUzh8HPCJod5_fEgSXuozpJtOggXBv0C2ps7yXlDZf-7J'
        'ar0UYc_NJEHJF-xShlqd6Q3sVL02PhSCM-ibn9DN9BKmD'
    ),
}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class TochkaPaymentGateway(PaymentGateway):
    provider_name = 'tochka'

    def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant_reference,
        order_id: int,
        receipt: dict | None,
    ) -> PaymentSession:
        if not settings.TOCHKA_WEBHOOK_CLAIMS_CONFIRMED:
            raise PaymentGatewayNotConfigured(
                'Онлайн-оплата не включена: схема claims webhook ещё не подтверждена.',
            )
        _require_payment_configuration()
        if currency != 'RUB' or amount <= 0:
            raise PaymentGatewayNotConfigured('Для Точка.API нужна положительная сумма в RUB.')

        payment_modes = settings.TOCHKA_PAYMENT_MODES
        if not payment_modes or not set(payment_modes).issubset(_PAYMENT_MODES):
            raise PaymentGatewayNotConfigured('Некорректно заданы способы оплаты Точки.')

        success_url = settings.TOCHKA_SUCCESS_URL
        configured_fail_url = settings.TOCHKA_FAIL_URL
        webhook_url = settings.TOCHKA_WEBHOOK_URL
        if not success_url or not configured_fail_url or not webhook_url:
            raise PaymentGatewayNotConfigured(
                'Нужно задать TOCHKA_SUCCESS_URL, TOCHKA_FAIL_URL и TOCHKA_WEBHOOK_URL.',
            )
        for callback_url in (success_url, configured_fail_url, webhook_url):
            _require_https_url(callback_url)
        amount_value = float(amount)
        if Decimal(str(amount_value)) != amount:
            raise PaymentGatewayNotConfigured('Сумму заказа нельзя точно представить в API-формате.')

        data = {
            'customerCode': settings.TOCHKA_CUSTOMER_CODE,
            'amount': amount_value,
            'purpose': f'Оплата заказа №{order_id}',
            'paymentMode': payment_modes,
            'paymentLinkId': merchant_reference.hex,
            'redirectUrl': success_url,
            'failRedirectUrl': configured_fail_url,
            'preAuthorization': False,
        }
        endpoint = '/acquiring/v1.0/payments'
        if settings.TOCHKA_FISCALIZATION_ENABLED:
            if not receipt:
                raise PaymentGatewayNotConfigured('Не сформированы данные кассового чека.')
            data.update(receipt)
            endpoint = '/acquiring/v1.0/payments_with_receipt'
        elif receipt is not None:
            raise PaymentGatewayNotConfigured(
                'Данные чека переданы при выключенной фискализации.',
            )
        if settings.TOCHKA_MERCHANT_ID:
            data['merchantId'] = settings.TOCHKA_MERCHANT_ID
        if settings.TOCHKA_PAYMENT_TTL_MINUTES:
            try:
                ttl = int(settings.TOCHKA_PAYMENT_TTL_MINUTES)
            except ValueError as exc:
                raise PaymentGatewayNotConfigured('Некорректный срок действия платёжной ссылки.') from exc
            if not 1 <= ttl <= 44640:
                raise PaymentGatewayNotConfigured('Срок ссылки должен быть от 1 до 44640 минут.')
            data['ttl'] = ttl

        response_data = self._request(
            'POST',
            endpoint,
            {'Data': data},
            creating_payment=True,
        )
        response = response_data.get('Data')
        if not isinstance(response, dict):
            raise PaymentCreationOutcomeUnknown('Ответ создания платежа имеет неизвестный формат.')
        operation_id = response.get('operationId')
        payment_url = response.get('paymentLink')
        if not isinstance(operation_id, str) or not operation_id:
            raise PaymentCreationOutcomeUnknown('В ответе банка отсутствует operationId.')
        if not isinstance(payment_url, str) or not payment_url:
            raise PaymentCreationOutcomeUnknown('В ответе банка отсутствует paymentLink.')
        try:
            _require_https_url(payment_url)
        except PaymentGatewayNotConfigured as exc:
            raise PaymentCreationOutcomeUnknown(
                'Банк создал платеж, но вернул некорректную ссылку; повтор не отправлен.',
            ) from exc
        return PaymentSession(operation_id, payment_url)

    def get_payment_status(self, operation_id: str) -> ProviderPaymentStatus:
        if not operation_id:
            raise PaymentGatewayNotConfigured('Не задан operationId для сверки платежа.')
        response_data = self._request(
            'GET',
            f'/acquiring/v1.0/payments/{quote(operation_id, safe="")}',
        )
        data = response_data.get('Data')
        operations = data.get('Operation') if isinstance(data, dict) else None
        if not isinstance(operations, list) or not operations:
            raise PaymentGatewayNotConfigured('Банк не вернул операции для сверки.')

        operation = next(
            (
                item for item in operations
                if isinstance(item, dict) and item.get('operationId') == operation_id
            ),
            None,
        )
        if operation is None:
            raise PaymentGatewayNotConfigured('operationId не найден в ответе банка.')

        status = operation.get('status')
        try:
            amount = Decimal(str(operation['amount']))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise PaymentGatewayNotConfigured('В ответе банка некорректная сумма платежа.') from exc
        if (
            not isinstance(status, str)
            or status not in _PAYMENT_STATUSES
            or not amount.is_finite()
        ):
            raise PaymentGatewayNotConfigured('В ответе банка неизвестный статус или сумма.')
        payment_link_id = operation.get('paymentLinkId', '')
        if not isinstance(payment_link_id, str):
            raise PaymentGatewayNotConfigured('В ответе банка некорректный paymentLinkId.')
        return ProviderPaymentStatus(
            operation_id=operation_id,
            status=status,
            amount=amount,
            payment_link_id=payment_link_id,
        )

    def normalize_payment_status(self, provider_status: str) -> str:
        status_map = {
            'CREATED': 'pending',
            'AUTHORIZED': 'pending',
            'WAIT_FULL_PAYMENT': 'pending',
            'APPROVED': 'paid',
            'EXPIRED': 'failed',
            'ON-REFUND': 'refund_pending',
            'REFUNDED': 'refunded',
            'REFUNDED_PARTIALLY': 'partially_refunded',
        }
        try:
            return status_map[provider_status]
        except KeyError as exc:
            raise PaymentGatewayNotConfigured('Неизвестный статус платежа Точки.') from exc

    def get_webhook_subscription(self):
        if not settings.TOCHKA_CLIENT_ID:
            raise PaymentGatewayNotConfigured('Не задан TOCHKA_CLIENT_ID.')
        return self._request(
            'GET',
            f'/webhook/v1.0/{quote(settings.TOCHKA_CLIENT_ID, safe="")}',
        )

    def register_webhook(self):
        if not settings.TOCHKA_CLIENT_ID or not settings.TOCHKA_WEBHOOK_URL:
            raise PaymentGatewayNotConfigured(
                'Нужно задать TOCHKA_CLIENT_ID и TOCHKA_WEBHOOK_URL.',
            )
        _require_https_url(settings.TOCHKA_WEBHOOK_URL)
        return self._request(
            'PUT',
            f'/webhook/v1.0/{quote(settings.TOCHKA_CLIENT_ID, safe="")}',
            {
                'webhooksList': ['acquiringInternetPayment'],
                'url': settings.TOCHKA_WEBHOOK_URL,
            },
        )

    def parse_notification(self, request) -> PaymentNotification:
        try:
            token = request.body.decode('ascii', errors='strict').strip()
        except UnicodeDecodeError as exc:
            raise InvalidPaymentNotification('Тело webhook должно содержать ASCII JWT.') from exc
        if not token:
            raise InvalidPaymentNotification('Пустое уведомление.')
        claims = _verify_webhook_jwt(token)
        if claims.get('webhookType') != 'acquiringInternetPayment':
            raise InvalidPaymentNotification('Неизвестный тип webhook.')
        operation_id = claims.get('operationId')
        payment_link_id = claims.get('paymentLinkId')
        if not isinstance(operation_id, str) or not operation_id:
            raise InvalidPaymentNotification('В webhook отсутствует operationId.')
        if not isinstance(payment_link_id, str) or not payment_link_id:
            raise InvalidPaymentNotification('В webhook отсутствует paymentLinkId.')
        try:
            merchant_reference = UUID(payment_link_id)
            amount = Decimal(str(claims['amount']))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidPaymentNotification('Некорректная сумма или paymentLinkId.') from exc
        if not amount.is_finite() or amount <= 0:
            raise InvalidPaymentNotification('Некорректная сумма webhook.')
        if claims.get('customerCode') != settings.TOCHKA_CUSTOMER_CODE:
            raise InvalidPaymentNotification('customerCode webhook не совпадает.')
        if settings.TOCHKA_MERCHANT_ID and claims.get('merchantId') != settings.TOCHKA_MERCHANT_ID:
            raise InvalidPaymentNotification('merchantId webhook не совпадает.')
        if claims.get('paymentType') not in _PAYMENT_TYPES:
            raise InvalidPaymentNotification('Неизвестный paymentType webhook.')
        status = claims.get('status')
        if not isinstance(status, str):
            raise InvalidPaymentNotification('В webhook отсутствует статус платежа.')
        try:
            normalized_status = self.normalize_payment_status(status)
        except PaymentGatewayNotConfigured as exc:
            raise InvalidPaymentNotification('Неизвестный статус webhook.') from exc
        return PaymentNotification(
            merchant_reference=merchant_reference,
            provider_payment_id=operation_id,
            status=normalized_status,
            amount=amount,
            currency='RUB',
        )

    def _request(self, method, path, payload=None, *, creating_payment=False):
        token = settings.TOCHKA_JWT_TOKEN
        if not token:
            raise PaymentGatewayNotConfigured('Не задан TOCHKA_JWT_TOKEN.')

        base_url = settings.TOCHKA_API_BASE_URL.rstrip('/')
        _require_https_url(base_url)
        url = f'{base_url}{path}'
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = Request(
            url,
            data=body,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            method=method,
        )
        opener = build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=10) as response:
                raw_response = response.read(1_000_001)
        except HTTPError as exc:
            if not creating_payment and method == 'GET' and exc.code == 404:
                raise PaymentGatewayNotFound('Ресурс Точки не найден.') from exc
            if creating_payment and 400 <= exc.code < 500:
                raise PaymentCreationRejected(
                    f'Банк отклонил создание платежа (HTTP {exc.code}).',
                ) from exc
            if creating_payment:
                raise PaymentCreationOutcomeUnknown(
                    'Банк не подтвердил результат создания платежа; повтор не отправлен.',
                ) from exc
            raise PaymentGatewayNotConfigured(
                f'Запрос к Точке завершился с HTTP {exc.code}.',
            ) from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            if creating_payment:
                raise PaymentCreationOutcomeUnknown(
                    'Неизвестно, создал ли банк платёж; повтор не отправлен.',
                ) from exc
            raise PaymentGatewayNotConfigured('Точка временно недоступна для сверки.') from exc

        if len(raw_response) > 1_000_000:
            error = PaymentCreationOutcomeUnknown if creating_payment else PaymentGatewayNotConfigured
            raise error('Ответ Точки превышает допустимый размер.')
        try:
            parsed_response = json.loads(raw_response)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            error = PaymentCreationOutcomeUnknown if creating_payment else PaymentGatewayNotConfigured
            raise error('Точка вернула некорректный JSON.') from exc
        if not isinstance(parsed_response, dict):
            error = PaymentCreationOutcomeUnknown if creating_payment else PaymentGatewayNotConfigured
            raise error('Точка вернула ответ неожиданного типа.')
        return parsed_response


def _require_payment_configuration():
    if not settings.TOCHKA_JWT_TOKEN:
        raise PaymentGatewayNotConfigured('Не задан TOCHKA_JWT_TOKEN.')
    if not settings.TOCHKA_CUSTOMER_CODE:
        raise PaymentGatewayNotConfigured('Не задан TOCHKA_CUSTOMER_CODE.')


def _require_https_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise PaymentGatewayNotConfigured('Для Точки требуется корректный HTTPS URL.')


def _verify_webhook_jwt(token):
    try:
        jwk = (
            json.loads(settings.TOCHKA_WEBHOOK_JWK)
            if settings.TOCHKA_WEBHOOK_JWK else _TOCHKA_WEBHOOK_JWK
        )
        if not isinstance(jwk, dict) or jwk.get('kty') != 'RSA':
            raise ValueError('Expected an RSA JWK.')
        signing_key = jwt.PyJWK.from_dict(jwk, algorithm='RS256').key
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256':
            raise ValueError('Unexpected JWT algorithm.')
        return jwt.decode(token, signing_key, algorithms=['RS256'])
    except (jwt.PyJWTError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidPaymentNotification('Подпись webhook не прошла проверку.') from exc
