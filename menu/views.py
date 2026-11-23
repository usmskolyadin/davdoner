from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Category, Product

SORT_OPTIONS = {
    'default': ('order', 'name'),
    'price_asc': ('price',),
    'price_desc': ('-price',),
    'name': ('name',),
}
SORT_LABELS = {
    'default': 'По умолчанию',
    'price_asc': 'Сначала дешевле',
    'price_desc': 'Сначала дороже',
    'name': 'По алфавиту',
}


def _sorted(qs, request):
    sort = request.GET.get('sort', 'default')
    if sort not in SORT_OPTIONS:
        sort = 'default'
    return qs.order_by(*SORT_OPTIONS[sort]), sort


def catalog(request):
    categories = Category.objects.filter(is_active=True).prefetch_related('products')
    sections = []
    for category in categories:
        products, sort = _sorted(
            category.products.filter(is_active=True), request,
        )
        if products:
            sections.append({'category': category, 'products': products})

    context = {
        'categories': categories,
        'sections': sections,
        'active_category': None,
        'sort': request.GET.get('sort', 'default'),
        'sort_labels': SORT_LABELS,
        'meta_title': 'Меню Dav Doner Club — донеры, боулы, мангал, супы и десерты',
        'meta_description': 'Полное меню Dav Doner Club: донеры и роллы, боулы и салаты, блюда на '
                             'мангале, супы, закуски, десерты и напитки.',
    }
    return render(request, 'menu/catalog.html', context)


def category_detail(request, slug):
    categories = Category.objects.filter(is_active=True)
    category = get_object_or_404(categories, slug=slug)
    products, sort = _sorted(category.products.filter(is_active=True), request)

    context = {
        'categories': categories,
        'sections': [{'category': category, 'products': products}],
        'active_category': category,
        'sort': sort,
        'sort_labels': SORT_LABELS,
        'meta_title': f'{category.name} — Dav Doner Club',
        'meta_description': category.description or f'{category.name} в меню Dav Doner Club.',
    }
    return render(request, 'menu/catalog.html', context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related('category').prefetch_related('addons'),
        slug=slug, is_active=True,
    )
    related = Product.objects.filter(
        category=product.category, is_active=True,
    ).exclude(pk=product.pk)[:4]

    context = {
        'product': product,
        'related_products': related,
        'meta_title': f'{product.name} — заказать с доставкой | Dav Doner Club',
        'meta_description': product.short_description or product.composition[:160],
    }
    return render(request, 'menu/product_detail.html', context)


def search(request):
    query = request.GET.get('q', '').strip()
    results = []
    if query:
        results = Product.objects.filter(
            Q(is_active=True) & (Q(name__icontains=query) | Q(short_description__icontains=query)
                                  | Q(composition__icontains=query)),
        ).select_related('category')

    context = {
        'query': query,
        'results': results,
        'meta_title': f'Поиск: {query} — Dav Doner Club' if query else 'Поиск — Dav Doner Club',
        'meta_description': 'Поиск блюд в меню Dav Doner Club.',
    }
    return render(request, 'menu/search.html', context)
