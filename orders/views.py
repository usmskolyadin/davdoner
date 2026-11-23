from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from menu.models import Product

from .cart import Cart
from .forms import CheckoutForm
from .models import DeliverySettings, Order, OrderItem
from .services import calculate_delivery, distance_to_cafe_km, is_within_delivery_zone


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True, is_stop_list=False)
    quantity = int(request.POST.get('quantity', 1) or 1)
    addon_ids = request.POST.getlist('addon_ids')
    cart = Cart(request)
    cart.add(product, quantity=quantity, addon_ids=addon_ids)

    if _is_ajax(request):
        return JsonResponse({'ok': True, 'count': cart.total_quantity, 'items_total': str(cart.items_total)})

    messages.success(request, f'«{product.name}» добавлен в корзину.')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('orders:cart')
    return redirect(next_url)


@require_POST
def cart_update(request):
    cart = Cart(request)
    key = request.POST.get('key')
    quantity = int(request.POST.get('quantity', 1) or 1)
    cart.set_quantity(key, quantity)
    if _is_ajax(request):
        return JsonResponse({
            'ok': True, 'count': cart.total_quantity, 'items_total': str(cart.items_total),
        })
    return redirect('orders:cart')


@require_POST
def cart_remove(request):
    cart = Cart(request)
    cart.remove(request.POST.get('key'))
    if _is_ajax(request):
        return JsonResponse({
            'ok': True, 'count': cart.total_quantity, 'items_total': str(cart.items_total),
        })
    return redirect('orders:cart')


def cart_detail(request):
    cart = Cart(request)
    settings_obj = DeliverySettings.load()
    delivery_cost, can_deliver, delivery_message = calculate_delivery(cart.items_total, 'delivery')
    pickup_cost, _, pickup_message = calculate_delivery(cart.items_total, 'pickup')

    context = {
        'cart': cart,
        'delivery_settings': settings_obj,
        'delivery_cost': delivery_cost,
        'can_deliver': can_deliver,
        'delivery_message': delivery_message,
        'pickup_message': pickup_message,
        'meta_title': 'Корзина — Dav Doner Club',
    }
    return render(request, 'orders/cart.html', context)


@require_POST
def check_delivery_zone(request):
    try:
        lat = float(request.POST.get('lat'))
        lon = float(request.POST.get('lon'))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Не удалось определить координаты.'}, status=400)

    distance = distance_to_cafe_km(lat, lon)
    within_zone = is_within_delivery_zone(distance)
    settings_obj = DeliverySettings.load()
    return JsonResponse({
        'ok': True,
        'distance_km': distance,
        'within_zone': within_zone,
        'radius_km': float(settings_obj.delivery_radius_km),
        'message': (
            f'Ваш адрес в зоне доставки (≈{distance} км от кафе).' if within_zone else
            f'Похоже, адрес находится вне зоны доставки (≈{distance} км, радиус доставки '
            f'{settings_obj.delivery_radius_km} км). Доставка может быть недоступна — выберите самовывоз '
            f'или уточните адрес у оператора.'
        ),
    })


def checkout(request):
    cart = Cart(request)
    if cart.is_empty:
        messages.info(request, 'Ваша корзина пуста — добавьте блюда перед оформлением заказа.')
        return redirect('menu:catalog')

    settings_obj = DeliverySettings.load()

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            delivery_type = form.cleaned_data['delivery_type']
            delivery_cost, can_deliver, delivery_message = calculate_delivery(
                cart.items_total, delivery_type,
            )
            if not can_deliver:
                messages.error(request, delivery_message)
            else:
                order = form.save(commit=False)
                if request.user.is_authenticated:
                    order.user = request.user
                order.items_total = cart.items_total
                order.delivery_cost = delivery_cost
                order.total = cart.items_total + delivery_cost
                order.distance_km = request.POST.get('distance_km') or None
                order.save()

                for row in cart:
                    OrderItem.objects.create(
                        order=order,
                        product=row['product'],
                        product_name=row['product'].name,
                        unit_price=row['unit_price'],
                        quantity=row['quantity'],
                        addons_snapshot=[
                            {'name': a.name, 'price': str(a.price)} for a in row['addons']
                        ],
                        line_total=row['line_total'],
                    )

                cart.clear()
                return redirect('orders:success', pk=order.pk)
    else:
        initial = {}
        if request.user.is_authenticated:
            initial['customer_name'] = request.user.get_full_name() or request.user.username
            profile = getattr(request.user, 'profile', None)
            if profile:
                initial['phone'] = profile.phone
                initial['address'] = profile.default_address
        form = CheckoutForm(initial=initial)

    delivery_cost, can_deliver, delivery_message = calculate_delivery(cart.items_total, 'delivery')

    context = {
        'cart': cart,
        'form': form,
        'delivery_settings': settings_obj,
        'delivery_cost': delivery_cost,
        'delivery_message': delivery_message,
        'meta_title': 'Оформление заказа — Dav Doner Club',
    }
    return render(request, 'orders/checkout.html', context)


def order_success(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'orders/success.html', {
        'order': order, 'meta_title': 'Заказ оформлен — Dav Doner Club',
    })
