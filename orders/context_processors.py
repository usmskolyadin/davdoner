from .cart import Cart
from .models import DeliverySettings


def cart(request):
    current_cart = Cart(request)
    return {
        'header_cart_count': current_cart.total_quantity,
        'header_cart_total': current_cart.items_total,
        'delivery_settings': DeliverySettings.load(),
    }
