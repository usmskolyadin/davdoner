from decimal import Decimal

from django.conf import settings
from django.db import models


class DeliverySettings(models.Model):
    """Единственная запись с настройками доставки — редактируется в админке."""

    cafe_address = models.CharField(
        'Адрес кафе', max_length=255,
        default='Москва, Кутузовский проспект, 36, строение 15',
    )
    cafe_lat = models.DecimalField('Широта кафе', max_digits=9, decimal_places=6, default=Decimal('55.739037'))
    cafe_lon = models.DecimalField('Долгота кафе', max_digits=9, decimal_places=6, default=Decimal('37.532955'))

    delivery_radius_km = models.DecimalField(
        'Радиус доставки, км', max_digits=4, decimal_places=1, default=Decimal('1.0'),
    )
    min_order_amount = models.DecimalField(
        'Минимальная сумма заказа для доставки, ₽', max_digits=8, decimal_places=2, default=Decimal('1000'),
    )
    free_delivery_threshold = models.DecimalField(
        'Сумма заказа для бесплатной доставки, ₽', max_digits=8, decimal_places=2, default=Decimal('3000'),
    )
    paid_delivery_cost = models.DecimalField(
        'Стоимость платной доставки, ₽', max_digits=8, decimal_places=2, default=Decimal('250'),
        help_text='Действует для заказов между минимальной суммой и порогом бесплатной доставки.',
    )

    phone = models.CharField('Телефон кафе', max_length=32, default='+7 (495) 000-00-00')
    work_hours = models.CharField('Часы работы', max_length=120, default='Ежедневно, 10:00 – 23:00')

    preferred_time_enabled = models.BooleanField(
        'Разрешить выбирать желаемое время заказа', default=True,
    )

    class Meta:
        verbose_name = 'Настройки доставки'
        verbose_name_plural = 'Настройки доставки'

    def __str__(self):
        return 'Настройки доставки и магазина'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Order(models.Model):
    class DeliveryType(models.TextChoices):
        DELIVERY = 'delivery', 'Доставка'
        PICKUP = 'pickup', 'Самовывоз'

    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        CONFIRMED = 'confirmed', 'Подтверждён'
        COOKING = 'cooking', 'Готовится'
        ON_THE_WAY = 'on_the_way', 'В пути / готов к выдаче'
        COMPLETED = 'completed', 'Выполнен'
        CANCELLED = 'cancelled', 'Отменён'

    class PaymentMethod(models.TextChoices):
        ONLINE = 'online', 'Онлайн-оплата картой'
        CASH = 'cash', 'Наличными при получении'
        CARD_ON_DELIVERY = 'card_on_delivery', 'Картой при получении'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Ожидает оплаты'
        PAID = 'paid', 'Оплачен'
        FAILED = 'failed', 'Ошибка оплаты'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Пользователь', related_name='orders',
        on_delete=models.SET_NULL, blank=True, null=True,
    )
    customer_name = models.CharField('Имя покупателя', max_length=120)
    phone = models.CharField('Телефон', max_length=32)

    delivery_type = models.CharField(
        'Способ получения', max_length=10, choices=DeliveryType.choices, default=DeliveryType.DELIVERY,
    )
    address = models.CharField('Адрес доставки', max_length=255, blank=True)
    distance_km = models.DecimalField(
        'Расстояние от кафе, км', max_digits=4, decimal_places=2, blank=True, null=True,
    )

    comment = models.TextField('Комментарий к заказу', blank=True)
    preferred_time = models.CharField(
        'Желаемое время', max_length=60, blank=True,
        help_text='Например: «как можно скорее» или «сегодня к 19:00».',
    )

    items_total = models.DecimalField('Сумма товаров, ₽', max_digits=9, decimal_places=2, default=0)
    delivery_cost = models.DecimalField('Стоимость доставки, ₽', max_digits=8, decimal_places=2, default=0)
    total = models.DecimalField('Итого, ₽', max_digits=9, decimal_places=2, default=0)

    status = models.CharField('Статус', max_length=12, choices=Status.choices, default=Status.NEW)
    payment_method = models.CharField(
        'Способ оплаты', max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH,
    )
    payment_status = models.CharField(
        'Статус оплаты', max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING,
    )

    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f'Заказ №{self.pk} — {self.customer_name}'

    @property
    def is_delivery(self):
        return self.delivery_type == self.DeliveryType.DELIVERY


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name='Заказ', related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(
        'menu.Product', verbose_name='Блюдо', related_name='order_items',
        on_delete=models.SET_NULL, blank=True, null=True,
    )
    product_name = models.CharField('Название блюда', max_length=150)
    unit_price = models.DecimalField('Цена за штуку, ₽', max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField('Количество', default=1)
    addons_snapshot = models.JSONField('Добавки', default=list, blank=True)
    line_total = models.DecimalField('Сумма по позиции, ₽', max_digits=9, decimal_places=2)

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'

    def __str__(self):
        return f'{self.product_name} × {self.quantity}'
