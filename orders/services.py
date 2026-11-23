from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from .models import DeliverySettings


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def distance_to_cafe_km(lat, lon):
    settings_obj = DeliverySettings.load()
    return round(haversine_km(settings_obj.cafe_lat, settings_obj.cafe_lon, lat, lon), 2)


def is_within_delivery_zone(distance_km):
    settings_obj = DeliverySettings.load()
    return Decimal(str(distance_km)) <= settings_obj.delivery_radius_km


def calculate_delivery(items_total, delivery_type):
    """Возвращает (delivery_cost, can_deliver, message) с учётом настроек магазина."""
    settings_obj = DeliverySettings.load()
    items_total = Decimal(items_total)

    if delivery_type == 'pickup':
        return Decimal('0'), True, 'Самовывоз бесплатный.'

    if items_total < settings_obj.min_order_amount:
        missing = settings_obj.min_order_amount - items_total
        return (
            Decimal('0'),
            False,
            f'Минимальная сумма заказа для доставки — {settings_obj.min_order_amount:.0f} ₽. '
            f'Добавьте в корзину ещё на {missing:.0f} ₽ или выберите самовывоз.',
        )

    if items_total >= settings_obj.free_delivery_threshold:
        return Decimal('0'), True, 'Доставка бесплатная!'

    missing = settings_obj.free_delivery_threshold - items_total
    return (
        settings_obj.paid_delivery_cost,
        True,
        f'Добавьте ещё на {missing:.0f} ₽ до бесплатной доставки.',
    )
