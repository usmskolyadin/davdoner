from django.contrib import admin
from django.utils.html import format_html

from .models import DeliverySettings, Order, OrderItem

STATUS_COLORS = {
    'new': '#2f6fed',
    'confirmed': '#9a6bd1',
    'cooking': '#d9531e',
    'on_the_way': '#c98a12',
    'completed': '#2e8b4f',
    'cancelled': '#999999',
}


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'product_name', 'unit_price', 'quantity', 'addons_snapshot', 'line_total')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'created_at', 'customer_name', 'phone', 'delivery_type_display',
        'total', 'status_badge', 'payment_status',
    )
    list_filter = ('status', 'delivery_type', 'payment_method', 'payment_status', 'created_at')
    list_editable = ('payment_status',)
    search_fields = ('customer_name', 'phone', 'address', 'id')
    date_hierarchy = 'created_at'
    readonly_fields = (
        'user', 'customer_name', 'phone', 'delivery_type', 'address', 'distance_km',
        'comment', 'preferred_time', 'items_total', 'delivery_cost', 'total',
        'payment_method', 'created_at', 'updated_at',
    )
    fields = (
        ('customer_name', 'phone'),
        ('delivery_type', 'address', 'distance_km'),
        ('comment', 'preferred_time'),
        ('items_total', 'delivery_cost', 'total'),
        'status',
        ('payment_method', 'payment_status'),
        ('created_at', 'updated_at'),
    )
    inlines = [OrderItemInline]
    list_per_page = 40

    @admin.display(description='Получение')
    def delivery_type_display(self, obj):
        return obj.get_delivery_type_display()

    @admin.display(description='Статус')
    def status_badge(self, obj):
        color = STATUS_COLORS.get(obj.status, '#555')
        return format_html(
            '<span style="background:{}22;color:{};padding:3px 10px;border-radius:999px;'
            'font-size:12px;font-weight:600;">{}</span>',
            color, color, obj.get_status_display(),
        )

    def has_add_permission(self, request):
        return False


@admin.register(DeliverySettings)
class DeliverySettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Адрес и геопозиция кафе', {
            'fields': ('cafe_address', ('cafe_lat', 'cafe_lon')),
        }),
        ('Условия доставки', {
            'fields': (
                'delivery_radius_km', 'min_order_amount',
                'free_delivery_threshold', 'paid_delivery_cost',
            ),
        }),
        ('Контакты и режим работы', {
            'fields': ('phone', 'work_hours'),
        }),
        ('Оформление заказа', {
            'fields': ('preferred_time_enabled',),
        }),
    )

    def has_add_permission(self, request):
        return not DeliverySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = DeliverySettings.load()
        from django.shortcuts import redirect
        return redirect('admin:orders_deliverysettings_change', obj.pk)
