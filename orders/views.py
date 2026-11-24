import logging

from django.contrib import messages
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from menu.models import Product

from .cart import Cart
from .forms import CheckoutForm
from .models import DeliverySettings, Order, OrderItem
from .payment_gateway import (
    InvalidPaymentNotification,
    PaymentGatewayError,
    PaymentGatewayNotConfigured,
    get_payment_gateway,
)
from .payment_services import apply_payment_notification, reconcile_payment, start_payment
from .services import calculate_delivery, distance_to_cafe_km, is_within_delivery_zone

logger = logging.getLogger(__name__)


def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _remember_order_for_guest(request, order):
    if order.user_id:
        return
    order_ids = request.session.get('guest_order_ids', [])
    request.session['guest_order_ids'] = (order_ids + [order.pk])[-20:]


def _can_access_order(request, order):
    if order.user_id:
        return request.user.is_authenticated and request.user.pk == order.user_id
    return order.pk in request.session.get('guest_order_ids', [])


def _create_order_from_checkout(form, request, cart, delivery_cost):
    order = form.save(commit=False)
    if request.user.is_authenticated:
        order.user = request.user
    order.items_total = cart.items_total
    order.delivery_cost = delivery_cost
    order.total = cart.items_total + delivery_cost
    order.distance_km = request.POST.get('distance_km') or None

    with transaction.atomic():
        order.save()
        OrderItem.objects.bulk_create([
            OrderItem(
                order=order,
                product=row['product'],
                product_name=row['product'].name,
                unit_price=row['unit_price'],
                quantity=row['quantity'],
                addons_snapshot=[
                    {'name': addon.name, 'price': str(addon.price)} for addon in row['addons']
                ],
                line_total=row['line_total'],
            )
            for row in cart
        ])
    _remember_order_for_guest(request, order)
    return order


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
                order = _create_order_from_checkout(form, request, cart, delivery_cost)
                cart.clear()
                if order.payment_method == Order.PaymentMethod.ONLINE:
                    try:
                        attempt = start_payment(
                            order,
                        )
                    except PaymentGatewayError:
                        logger.warning('Could not start payment for order %s', order.pk)
                        messages.error(
                            request,
                            'Не удалось открыть оплату. Заказ сохранён; попробуйте начать оплату '
                            'со страницы заказа позже.',
                        )
                        return redirect('orders:success', pk=order.pk)
                    return redirect(attempt.payment_url)
                return redirect('orders:success', pk=order.pk)
    else:
        initial = {}
        if request.user.is_authenticated:
            initial['customer_name'] = request.user.get_full_name() or request.user.username
            initial['customer_email'] = request.user.email
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
        'online_payment_enabled': bool(getattr(settings, 'PAYMENT_GATEWAY', '')),
        'fiscalization_enabled': settings.TOCHKA_FISCALIZATION_ENABLED,
        'meta_title': 'Оформление заказа — Dav Doner Club',
    }
    return render(request, 'orders/checkout.html', context)


def order_success(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not _can_access_order(request, order):
        return HttpResponse(status=404)
    return render(request, 'orders/success.html', {
        'order': order,
        'online_payment_enabled': bool(getattr(settings, 'PAYMENT_GATEWAY', '')),
        'can_manage_payment': (
            order.payment_method == Order.PaymentMethod.ONLINE
            and order.payment_status in {
                Order.PaymentStatus.PENDING,
                Order.PaymentStatus.FAILED,
                Order.PaymentStatus.CANCELLED,
            }
        ),
        'meta_title': 'Заказ оформлен — Dav Doner Club',
    })


@require_POST
def retry_payment(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not _can_access_order(request, order):
        return HttpResponse(status=404)
    if order.payment_method != Order.PaymentMethod.ONLINE:
        return HttpResponse(status=400)
    if order.payment_status == Order.PaymentStatus.PAID:
        messages.info(request, 'Заказ уже оплачен.')
        return redirect('orders:success', pk=order.pk)

    try:
        attempt = start_payment(
            order,
        )
    except PaymentGatewayError:
        logger.warning('Could not retry payment for order %s', order.pk)
        messages.error(request, 'Не удалось открыть оплату. Попробуйте ещё раз позже.')
        return redirect('orders:success', pk=order.pk)
    return redirect(attempt.payment_url)


@require_POST
def check_payment_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not _can_access_order(request, order):
        return HttpResponse(status=404)
    if order.payment_method != Order.PaymentMethod.ONLINE:
        return HttpResponse(status=400)

    attempt = order.payment_attempts.exclude(
        provider_payment_id='',
    ).order_by('-created_at').first()
    if attempt is None:
        messages.error(request, 'У банка пока нет идентификатора платежа для сверки.')
        return redirect('orders:success', pk=order.pk)
    try:
        reconcile_payment(attempt)
    except PaymentGatewayError:
        logger.warning('Could not reconcile payment for order %s', order.pk)
        messages.error(request, 'Не удалось получить подтверждённый статус от банка.')
    else:
        messages.success(request, 'Статус платежа обновлён по данным банка.')
    return redirect('orders:success', pk=order.pk)


@csrf_exempt
@require_POST
def payment_notification(request):
    try:
        gateway = get_payment_gateway()
    except PaymentGatewayNotConfigured:
        return HttpResponse(status=503)

    try:
        notification = gateway.parse_notification(request)
    except InvalidPaymentNotification:
        logger.warning('Rejected invalid payment notification')
        return HttpResponse(status=400)
    except PaymentGatewayError:
        logger.warning('Payment provider could not verify notification')
        return HttpResponse(status=503)

    try:
        apply_payment_notification(gateway.provider_name, notification)
    except PaymentGatewayError:
        logger.warning('Could not apply payment notification')
        return HttpResponse(status=400)
    return HttpResponse(status=200)
