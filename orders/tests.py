import json
import uuid
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory
from django.test import TestCase, override_settings

from .forms import CheckoutForm
from .models import Order, OrderItem, PaymentAttempt
from .payment_gateway import (
    InvalidPaymentNotification,
    PaymentGateway,
    PaymentGatewayError,
    PaymentCreationOutcomeUnknown,
    PaymentGatewayNotConfigured,
    PaymentGatewayNotFound,
    PaymentNotification,
    PaymentSession,
    ProviderPaymentStatus,
)
from .payment_services import (
    apply_payment_notification,
    build_receipt,
    reconcile_payment,
    request_refund,
    start_payment,
)
from .tochka_gateway import TochkaPaymentGateway


def _sign_test_jwt(claims):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return jwt.encode(claims, private_key, algorithm='RS256'), json.dumps(jwk)


class FakePaymentGateway(PaymentGateway):
    provider_name = 'fake'
    create_calls = 0
    create_error = None
    status_snapshot = None

    def create_payment(self, **kwargs):
        del kwargs
        type(self).create_calls += 1
        if type(self).create_error:
            raise type(self).create_error
        return PaymentSession('fake-payment-1', 'https://pay.example.test/session/1')

    def parse_notification(self, request):
        del request
        raise InvalidPaymentNotification('Invalid fake notification.')

    def get_payment_status(self, operation_id):
        del operation_id
        return type(self).status_snapshot

    def normalize_payment_status(self, provider_status):
        return {
            'CREATED': PaymentAttempt.Status.PENDING,
            'APPROVED': PaymentAttempt.Status.PAID,
            'EXPIRED': PaymentAttempt.Status.FAILED,
        }[provider_status]


class PaymentPreparationTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            customer_name='Test',
            phone='+70000000000',
            payment_method=Order.PaymentMethod.ONLINE,
            total=Decimal('1250.00'),
        )
        FakePaymentGateway.create_calls = 0
        FakePaymentGateway.create_error = None
        FakePaymentGateway.status_snapshot = None

    @override_settings(PAYMENT_GATEWAY='')
    def test_online_payment_choice_is_hidden_until_gateway_is_configured(self):
        form = CheckoutForm()
        choices = dict(form.fields['payment_method'].choices)

        self.assertNotIn(Order.PaymentMethod.ONLINE, choices)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_repeated_start_reuses_the_pending_payment_attempt(self):
        first_attempt = start_payment(self.order)
        second_attempt = start_payment(self.order)

        self.assertEqual(first_attempt.pk, second_attempt.pk)
        self.assertEqual(FakePaymentGateway.create_calls, 1)
        self.assertEqual(PaymentAttempt.objects.filter(order=self.order).count(), 1)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_unknown_create_result_is_not_retried_blindly(self):
        FakePaymentGateway.create_error = PaymentCreationOutcomeUnknown('timeout')

        with self.assertRaises(PaymentCreationOutcomeUnknown):
            start_payment(self.order)
        with self.assertRaises(PaymentCreationOutcomeUnknown):
            start_payment(self.order)

        attempt = PaymentAttempt.objects.get(order=self.order)
        self.assertEqual(FakePaymentGateway.create_calls, 1)
        self.assertEqual(attempt.creation_status, PaymentAttempt.CreationStatus.UNKNOWN)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_in_progress_attempt_is_not_created_twice(self):
        PaymentAttempt.objects.create(
            order=self.order,
            provider='fake',
            amount=self.order.total,
            status=PaymentAttempt.Status.PENDING,
            creation_status=PaymentAttempt.CreationStatus.SENDING,
        )

        with self.assertRaises(PaymentCreationOutcomeUnknown):
            start_payment(self.order)

        self.assertEqual(FakePaymentGateway.create_calls, 0)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_verified_paid_notification_updates_order_and_is_idempotent(self):
        attempt = start_payment(self.order)
        notification = PaymentNotification(
            merchant_reference=attempt.idempotency_key,
            provider_payment_id='fake-payment-1',
            status=PaymentAttempt.Status.PAID,
            amount=attempt.amount,
            currency=attempt.currency,
        )

        apply_payment_notification('fake', notification)
        apply_payment_notification('fake', notification)
        apply_payment_notification('fake', PaymentNotification(
            merchant_reference=attempt.idempotency_key,
            provider_payment_id='fake-payment-1',
            status=PaymentAttempt.Status.PENDING,
            amount=attempt.amount,
            currency=attempt.currency,
        ))
        self.order.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(attempt.status, PaymentAttempt.Status.PAID)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_notification_with_wrong_amount_is_rejected(self):
        attempt = start_payment(self.order)
        notification = PaymentNotification(
            merchant_reference=attempt.idempotency_key,
            provider_payment_id='fake-payment-1',
            status=PaymentAttempt.Status.PAID,
            amount=Decimal('1.00'),
            currency=attempt.currency,
        )

        with self.assertRaises(PaymentGatewayError):
            apply_payment_notification('fake', notification)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_expired_payment_is_marked_failed_during_reconciliation(self):
        attempt = start_payment(self.order)
        FakePaymentGateway.status_snapshot = ProviderPaymentStatus(
            operation_id=attempt.provider_payment_id,
            status='EXPIRED',
            amount=attempt.amount,
            payment_link_id=attempt.idempotency_key.hex,
        )

        updated_attempt = reconcile_payment(attempt)
        self.order.refresh_from_db()

        self.assertEqual(updated_attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_customer_can_refresh_status_from_provider_api(self):
        attempt = start_payment(self.order)
        FakePaymentGateway.status_snapshot = ProviderPaymentStatus(
            operation_id=attempt.provider_payment_id,
            status='APPROVED',
            amount=attempt.amount,
            payment_link_id=attempt.idempotency_key.hex,
        )
        session = self.client.session
        session['guest_order_ids'] = [self.order.pk]
        session.save()

        response = self.client.post(f'/order/{self.order.pk}/check-payment/')
        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    @override_settings(
        TOCHKA_JWT_TOKEN='test-token',
        TOCHKA_CUSTOMER_CODE='1234567ab',
        TOCHKA_PAYMENT_MODES=['card', 'sbp'],
        TOCHKA_SUCCESS_URL='https://shop.example.test/payment/success/',
        TOCHKA_FAIL_URL='https://shop.example.test/payment/fail/',
        TOCHKA_WEBHOOK_URL='https://shop.example.test/payments/tochka/webhook/',
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
        TOCHKA_MERCHANT_ID='',
        TOCHKA_PAYMENT_TTL_MINUTES='',
    )
    def test_tochka_payment_request_uses_decimal_amount_and_unique_link_id(self):
        gateway = TochkaPaymentGateway()
        response = {
            'Data': {
                'operationId': 'operation-123',
                'paymentLink': 'https://pay.example.test/link/123',
            },
        }

        with patch.object(gateway, '_request', return_value=response) as request:
            session = gateway.create_payment(
                amount=Decimal('1500.00'),
                currency='RUB',
                merchant_reference=uuid.uuid4(),
                order_id=self.order.pk,
                receipt=None,
            )

        body = request.call_args.args[2]['Data']
        self.assertEqual(body['amount'], 1500.0)
        self.assertEqual(body['purpose'], f'Оплата заказа №{self.order.pk}')
        self.assertEqual(len(body['paymentLinkId']), 32)
        self.assertEqual(session.provider_payment_id, 'operation-123')
        self.assertEqual(session.payment_url, 'https://pay.example.test/link/123')

    @override_settings(
        TOCHKA_JWT_TOKEN='test-token',
        TOCHKA_CUSTOMER_CODE='1234567ab',
        TOCHKA_PAYMENT_MODES=['card'],
        TOCHKA_SUCCESS_URL='https://shop.example.test/payment/success/',
        TOCHKA_FAIL_URL='https://shop.example.test/payment/fail/',
        TOCHKA_WEBHOOK_URL='https://shop.example.test/payments/tochka/webhook/',
        TOCHKA_MERCHANT_ID='',
        TOCHKA_PAYMENT_TTL_MINUTES='',
        TOCHKA_FISCALIZATION_ENABLED=True,
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
    )
    def test_tochka_receipt_request_uses_receipt_endpoint(self):
        gateway = TochkaPaymentGateway()
        response = {
            'Data': {
                'operationId': 'operation-receipt',
                'paymentLink': 'https://pay.example.test/receipt',
            },
        }
        receipt = {
            'taxSystemCode': 'usn_income',
            'Client': {'email': 'buyer@example.test'},
            'Items': [{'name': 'Еда', 'amount': 1500.0, 'quantity': 1}],
        }

        with patch.object(gateway, '_request', return_value=response) as request:
            gateway.create_payment(
                amount=Decimal('1500.00'),
                currency='RUB',
                merchant_reference=uuid.uuid4(),
                order_id=self.order.pk,
                receipt=receipt,
            )

        self.assertEqual(request.call_args.args[1], '/acquiring/v1.0/payments_with_receipt')
        self.assertEqual(request.call_args.args[2]['Data']['Client'], receipt['Client'])

    def test_tochka_status_selects_matching_operation_and_accepts_decimal_string(self):
        gateway = TochkaPaymentGateway()
        response = {
            'Data': {
                'Operation': [
                    {'operationId': 'other-operation', 'amount': 10, 'status': 'CREATED'},
                    {
                        'operationId': 'operation-123',
                        'amount': '1500.00',
                        'status': 'APPROVED',
                        'paymentLinkId': 'order-link-123',
                    },
                ],
            },
        }

        with patch.object(gateway, '_request', return_value=response):
            status = gateway.get_payment_status('operation-123')

        self.assertEqual(status.amount, Decimal('1500.00'))
        self.assertEqual(status.status, 'APPROVED')
        self.assertEqual(status.operation_id, 'operation-123')

    @override_settings(
        TOCHKA_TAX_SYSTEM_CODE='usn_income',
        TOCHKA_VAT_TYPE='none',
        TOCHKA_PAYMENT_METHOD='full_payment',
        TOCHKA_PAYMENT_OBJECT='goods',
        TOCHKA_DELIVERY_VAT_TYPE='none',
        TOCHKA_DELIVERY_PAYMENT_OBJECT='service',
        TOCHKA_CUSTOMER_CODE='1234567ab',
        TOCHKA_MERCHANT_ID='',
    )
    def test_receipt_requires_config_and_matches_order_total(self):
        self.order.customer_email = 'buyer@example.test'
        self.order.items_total = Decimal('1200.00')
        self.order.delivery_cost = Decimal('250.00')
        self.order.total = Decimal('1450.00')
        self.order.save()
        OrderItem.objects.create(
            order=self.order,
            product_name='Донер',
            unit_price=Decimal('600.00'),
            quantity=2,
            line_total=Decimal('1200.00'),
        )

        receipt = build_receipt(self.order)

        self.assertEqual(
            sum(Decimal(str(item['amount'])) * item['quantity'] for item in receipt['Items']),
            self.order.total,
        )
        self.assertEqual(receipt['Client']['email'], 'buyer@example.test')
        self.assertEqual(len(receipt['Items']), 2)

    @override_settings(
        TOCHKA_TAX_SYSTEM_CODE='',
        TOCHKA_VAT_TYPE='',
        TOCHKA_PAYMENT_METHOD='',
        TOCHKA_PAYMENT_OBJECT='',
        TOCHKA_CUSTOMER_CODE='1234567ab',
        TOCHKA_MERCHANT_ID='',
    )
    def test_receipt_rejects_missing_tax_configuration(self):
        with self.assertRaises(PaymentGatewayNotConfigured):
            build_receipt(self.order)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_refund_is_permission_gated_and_provider_schema_is_fail_closed(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider='fake',
            amount=self.order.total,
            status=PaymentAttempt.Status.PAID,
        )
        user_model = get_user_model()
        actor = user_model.objects.create_user(username='refund-operator', password='unused')

        with self.assertRaises(PermissionDenied):
            request_refund(attempt, actor=actor, amount=Decimal('100.00'))

        permission = Permission.objects.get(
            content_type__app_label='orders',
            codename='refund_payment',
        )
        actor.user_permissions.add(permission)
        actor = user_model.objects.get(pk=actor.pk)
        with self.assertRaises(PaymentGatewayNotConfigured):
            request_refund(attempt, actor=actor, amount=Decimal('100.00'))

    @override_settings(
        TOCHKA_WEBHOOK_JWK='',
    )
    def test_invalid_webhook_signature_is_rejected(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
        token = jwt.encode({'event': 'acquiringInternetPayment'}, wrong_key, algorithm='RS256')
        request = RequestFactory().post(
            '/payments/notification/',
            data=token,
            content_type='text/plain',
        )
        with override_settings(TOCHKA_WEBHOOK_JWK=json.dumps(jwk)):
            with self.assertRaises(InvalidPaymentNotification):
                TochkaPaymentGateway().parse_notification(request)

    @override_settings(
        PAYMENT_GATEWAY='orders.tochka_gateway.TochkaPaymentGateway',
        TOCHKA_CUSTOMER_CODE='1234567ab',
        TOCHKA_MERCHANT_ID='',
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
    )
    def test_signed_webhook_updates_payment_once_and_duplicate_is_acknowledged(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider='tochka',
            provider_payment_id='operation-123',
            payment_url='https://pay.example.test/1',
            amount=self.order.total,
            creation_status=PaymentAttempt.CreationStatus.CREATED,
        )
        token, jwk = _sign_test_jwt({
            'webhookType': 'acquiringInternetPayment',
            'operationId': 'operation-123',
            'paymentLinkId': attempt.idempotency_key.hex,
            'customerCode': '1234567ab',
            'amount': '1250.00',
            'status': 'APPROVED',
            'paymentType': 'card',
        })

        with override_settings(TOCHKA_WEBHOOK_JWK=jwk):
            first_response = self.client.post(
                '/payments/notification/',
                data=token,
                content_type='text/plain',
            )
            duplicate_response = self.client.post(
                '/payments/notification/',
                data=token,
                content_type='text/plain',
            )
        self.order.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(attempt.status, PaymentAttempt.Status.PAID)

    @override_settings(
        PAYMENT_GATEWAY='orders.tochka_gateway.TochkaPaymentGateway',
        TOCHKA_CUSTOMER_CODE='1234567ab',
        TOCHKA_MERCHANT_ID='',
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
    )
    def test_signed_webhook_with_wrong_amount_is_rejected(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            provider='tochka',
            provider_payment_id='operation-123',
            amount=self.order.total,
        )
        token, jwk = _sign_test_jwt({
            'webhookType': 'acquiringInternetPayment',
            'operationId': 'operation-123',
            'paymentLinkId': attempt.idempotency_key.hex,
            'customerCode': '1234567ab',
            'amount': '1.00',
            'status': 'APPROVED',
            'paymentType': 'sbp',
        })

        with override_settings(TOCHKA_WEBHOOK_JWK=jwk):
            response = self.client.post(
                '/payments/notification/',
                data=token,
                content_type='text/plain',
            )
        self.order.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_guest_order_page_requires_the_original_session(self):
        response = self.client.get(f'/order/{self.order.pk}/success/')
        self.assertEqual(response.status_code, 404)

        session = self.client.session
        session['guest_order_ids'] = [self.order.pk]
        session.save()

        response = self.client.get(f'/order/{self.order.pk}/success/')
        self.assertEqual(response.status_code, 200)

    @override_settings(PAYMENT_GATEWAY='orders.tests.FakePaymentGateway')
    def test_unverified_provider_notification_is_rejected(self):
        response = self.client.post('/payments/notification/', data='{}', content_type='application/json')

        self.assertEqual(response.status_code, 400)


class WebhookRegistrationCommandTests(TestCase):
    webhook_url = 'https://shop.example.test/payments/notification/'

    @override_settings(
        TOCHKA_ENABLED=False,
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
        TOCHKA_WEBHOOK_URL=webhook_url,
    )
    def test_existing_matching_subscription_is_not_rewritten(self):
        subscription = {
            'Data': {
                'webhooksList': ['acquiringInternetPayment'],
                'url': self.webhook_url,
            },
        }
        with (
            patch.object(TochkaPaymentGateway, 'get_webhook_subscription', return_value=subscription),
            patch.object(TochkaPaymentGateway, 'register_webhook') as register_webhook,
        ):
            call_command('register_tochka_webhook', stdout=StringIO())

        register_webhook.assert_not_called()

    @override_settings(
        TOCHKA_ENABLED=False,
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
        TOCHKA_WEBHOOK_URL=webhook_url,
    )
    def test_get_404_requires_explicit_confirmation(self):
        with (
            patch.object(
                TochkaPaymentGateway,
                'get_webhook_subscription',
                side_effect=PaymentGatewayNotFound('not found'),
            ),
            patch.object(TochkaPaymentGateway, 'register_webhook') as register_webhook,
        ):
            with self.assertRaises(CommandError):
                call_command('register_tochka_webhook', stdout=StringIO())

        register_webhook.assert_not_called()

    @override_settings(
        TOCHKA_ENABLED=False,
        TOCHKA_WEBHOOK_CLAIMS_CONFIRMED=True,
        TOCHKA_WEBHOOK_URL=webhook_url,
    )
    def test_confirmed_404_registers_expected_subscription(self):
        registration_response = {
            'Data': {
                'webhooksList': ['acquiringInternetPayment'],
                'url': self.webhook_url,
            },
        }
        with (
            patch.object(
                TochkaPaymentGateway,
                'get_webhook_subscription',
                side_effect=PaymentGatewayNotFound('not found'),
            ),
            patch.object(
                TochkaPaymentGateway,
                'register_webhook',
                return_value=registration_response,
            ) as register_webhook,
        ):
            call_command('register_tochka_webhook', '--confirm-not-found', stdout=StringIO())

        register_webhook.assert_called_once_with()


class TochkaRequestConfigurationTests(TestCase):
    @override_settings(
        TOCHKA_JWT_TOKEN='test-token',
        TOCHKA_API_BASE_URL='http://bank.example.test/uapi',
    )
    def test_api_request_refuses_to_send_bearer_token_over_http(self):
        with self.assertRaises(PaymentGatewayNotConfigured):
            TochkaPaymentGateway().get_payment_status('operation-123')
