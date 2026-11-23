from decimal import Decimal

from django.conf import settings

from menu.models import Addon, Product


def _make_key(product_id, addon_ids):
    addon_part = ','.join(str(a) for a in sorted(addon_ids))
    return f'{product_id}:{addon_part}'


class Cart:
    """Корзина на основе сессии. Хранит id товара, количество и выбранные добавки."""

    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_KEY)
        if cart is None:
            cart = {}
            self.session[settings.CART_SESSION_KEY] = cart
        self.cart = cart

    def _save(self):
        self.session.modified = True

    def add(self, product, quantity=1, addon_ids=None):
        addon_ids = sorted(int(a) for a in (addon_ids or []))
        key = _make_key(product.id, addon_ids)
        if key in self.cart:
            self.cart[key]['quantity'] += quantity
        else:
            self.cart[key] = {
                'product_id': product.id,
                'addon_ids': addon_ids,
                'quantity': quantity,
            }
        self._save()

    def set_quantity(self, key, quantity):
        if key not in self.cart:
            return
        if quantity <= 0:
            del self.cart[key]
        else:
            self.cart[key]['quantity'] = quantity
        self._save()

    def remove(self, key):
        if key in self.cart:
            del self.cart[key]
            self._save()

    def clear(self):
        self.session[settings.CART_SESSION_KEY] = {}
        self._save()

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def __iter__(self):
        product_ids = {item['product_id'] for item in self.cart.values()}
        products = Product.objects.select_related('category').filter(id__in=product_ids)
        products_map = {p.id: p for p in products}

        addon_ids = set()
        for item in self.cart.values():
            addon_ids.update(item['addon_ids'])
        addons_map = {a.id: a for a in Addon.objects.filter(id__in=addon_ids)}

        for key, item in self.cart.items():
            product = products_map.get(item['product_id'])
            if product is None:
                continue
            addons = [addons_map[a] for a in item['addon_ids'] if a in addons_map]
            addons_price = sum((a.price for a in addons), Decimal('0'))
            unit_price = product.price + addons_price
            yield {
                'key': key,
                'product': product,
                'addons': addons,
                'quantity': item['quantity'],
                'unit_price': unit_price,
                'line_total': unit_price * item['quantity'],
            }

    @property
    def items_total(self):
        return sum((row['line_total'] for row in self), Decimal('0'))

    @property
    def total_quantity(self):
        return len(self)

    @property
    def is_empty(self):
        return len(self.cart) == 0
