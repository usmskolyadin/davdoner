from django.shortcuts import render

from menu.models import Category, Product
from orders.models import DeliverySettings

from .models import Benefit, HeroBanner


def home(request):
    context = {
        'banners': HeroBanner.objects.filter(is_active=True),
        'benefits': Benefit.objects.filter(is_active=True),
        'home_categories': Category.objects.filter(is_active=True, show_on_home=True),
        'popular_products': Product.objects.filter(
            is_active=True, is_popular=True,
        ).select_related('category')[:8],
        'delivery_settings': DeliverySettings.load(),
        'meta_title': None,
        'meta_description': None,
    }
    return render(request, 'pages/home.html', context)
