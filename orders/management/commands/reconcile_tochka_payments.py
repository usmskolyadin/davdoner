from django.core.management.base import BaseCommand, CommandError

from orders.models import PaymentAttempt
from orders.payment_gateway import PaymentGatewayError
from orders.payment_services import reconcile_payment


class Command(BaseCommand):
    help = 'Сверяет незавершённые платежи Точки по operationId.'

    def add_arguments(self, parser):
        parser.add_argument('--order-id', type=int)
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if options['limit'] < 1:
            raise CommandError('--limit должен быть положительным числом.')

        attempts = PaymentAttempt.objects.filter(
            provider='tochka',
            status__in=[
                PaymentAttempt.Status.PENDING,
                PaymentAttempt.Status.FAILED,
                PaymentAttempt.Status.CANCELLED,
                PaymentAttempt.Status.PAID,
                PaymentAttempt.Status.REFUND_PENDING,
                PaymentAttempt.Status.PARTIALLY_REFUNDED,
            ],
        ).exclude(provider_payment_id='').order_by('created_at')
        if options['order_id'] is not None:
            attempts = attempts.filter(order_id=options['order_id'])

        checked = failed = 0
        for attempt in attempts[:options['limit']]:
            checked += 1
            try:
                updated_attempt = reconcile_payment(attempt)
            except PaymentGatewayError as exc:
                failed += 1
                self.stderr.write(
                    f'Заказ №{attempt.order_id}: сверка не выполнена ({exc}).',
                )
                continue
            self.stdout.write(
                f'Заказ №{attempt.order_id}: {updated_attempt.get_status_display()}.',
            )

        self.stdout.write(f'Проверено: {checked}; ошибок: {failed}.')
        unresolved = PaymentAttempt.objects.filter(
            provider='tochka',
            status=PaymentAttempt.Status.PENDING,
            provider_payment_id='',
        ).count()
        if unresolved:
            self.stderr.write(
                f'Не удалось автоматически сверить попыток без operationId: {unresolved}.',
            )
        if failed:
            raise CommandError('Часть платежей не удалось сверить; см. сообщения выше.')
