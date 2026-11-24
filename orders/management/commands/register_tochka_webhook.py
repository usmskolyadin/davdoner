from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from orders.payment_gateway import PaymentGatewayNotFound
from orders.tochka_gateway import TochkaPaymentGateway


class Command(BaseCommand):
    help = 'Безопасно проверяет и регистрирует webhook Точка.API.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm-not-found',
            action='store_true',
            help='Подтвердить, что HTTP 404 означает отсутствие подписки, а client_id проверен.',
        )

    def handle(self, *args, **options):
        if not settings.TOCHKA_WEBHOOK_CLAIMS_CONFIRMED:
            raise CommandError(
                'Регистрация отключена: схема claims webhook ещё не подтверждена.',
            )

        gateway = TochkaPaymentGateway()
        try:
            existing = gateway.get_webhook_subscription()
        except PaymentGatewayNotFound:
            existing = None

        if existing is not None:
            data = existing.get('Data')
            if (
                not isinstance(data, dict)
                or not isinstance(data.get('webhooksList'), list)
                or not isinstance(data.get('url'), str)
            ):
                raise CommandError(
                    'GET вернул неизвестную схему; PUT не отправлен.',
                )
            if data['url'] != settings.TOCHKA_WEBHOOK_URL:
                raise CommandError(
                    'Для client_id уже настроен другой URL; PUT не отправлен.',
                )
            if 'acquiringInternetPayment' in data['webhooksList']:
                self.stdout.write(self.style.SUCCESS('Webhook уже настроен; PUT не выполнялся.'))
                return
            raise CommandError(
                'На URL уже настроены другие события. Измените подписку отдельным официальным '
                'методом Edit Webhook; PUT не отправлен.',
            )

        if not options['confirm_not_found']:
            raise CommandError(
                'GET вернул 404. Проверьте client_id и доступ, затем повторите с --confirm-not-found.',
            )

        response = gateway.register_webhook()
        data = response.get('Data')
        expected = {
            'webhooksList': ['acquiringInternetPayment'],
            'url': settings.TOCHKA_WEBHOOK_URL,
        }
        if not isinstance(data, dict) or any(data.get(key) != value for key, value in expected.items()):
            raise CommandError('Ответ PUT не подтвердил ожидаемую webhook-подписку.')
        self.stdout.write(self.style.SUCCESS('Webhook Точки зарегистрирован.'))
