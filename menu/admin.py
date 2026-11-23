from django.contrib import admin
from django.utils.html import format_html

from .models import Addon, Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'cover_preview', 'order', 'active_products_count', 'is_active', 'show_on_home')
    list_display_links = ('name',)
    list_editable = ('order', 'is_active', 'show_on_home')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    fields = ('name', 'slug', 'icon', 'description', 'cover', 'cover_preview', 'order', 'is_active', 'show_on_home')
    readonly_fields = ('cover_preview',)

    @admin.display(description='Фото')
    def cover_preview(self, obj):
        if obj.cover:
            return format_html(
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:8px;">',
                obj.cover.url,
            )
        return '—'

    @admin.display(description='Активных блюд')
    def active_products_count(self, obj):
        return obj.active_products_count


@admin.register(Addon)
class AddonAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    list_editable = ('price', 'is_active')
    search_fields = ('name',)


class StopListFilter(admin.SimpleListFilter):
    title = 'стоп-лист'
    parameter_name = 'stop'

    def lookups(self, request, model_admin):
        return (('yes', 'В стоп-листе'), ('no', 'Доступны'))

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(is_stop_list=True)
        if self.value() == 'no':
            return queryset.filter(is_stop_list=False)
        return queryset


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'image_preview', 'name', 'category', 'price_display', 'weight_column',
        'is_active', 'is_stop_list', 'is_popular', 'order',
    )
    list_display_links = ('image_preview', 'name')
    list_editable = ('is_active', 'is_stop_list', 'is_popular', 'order')
    list_filter = ('category', StopListFilter, 'is_active', 'is_popular')
    search_fields = ('name', 'short_description', 'composition')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('addons',)
    readonly_fields = ('image_preview_big', 'created_at', 'updated_at')
    list_per_page = 50

    fieldsets = (
        ('Основное', {
            'fields': ('category', 'name', 'slug', 'short_description', 'composition'),
        }),
        ('Фотография', {
            'fields': ('image', 'image_preview_big'),
        }),
        ('Вес и цена', {
            'fields': (('weight_value', 'weight_unit'), ('price', 'old_price')),
        }),
        ('Пищевая ценность (на порцию, по желанию)', {
            'classes': ('collapse',),
            'fields': (('calories',), ('proteins', 'fats', 'carbs')),
        }),
        ('Добавки', {
            'fields': ('addons',),
        }),
        ('Публикация', {
            'fields': ('is_active', 'is_stop_list', 'is_popular', 'order'),
        }),
        ('Служебное', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Фото')
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:44px;width:44px;object-fit:cover;border-radius:8px;">',
                obj.image.url,
            )
        return format_html('<span style="opacity:.4;">{}</span>', 'нет фото')

    @admin.display(description='Текущее фото')
    def image_preview_big(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:220px;border-radius:12px;">', obj.image.url,
            )
        return 'Фотография ещё не загружена — на сайте будет показана заглушка.'

    @admin.display(description='Вес / объём')
    def weight_column(self, obj):
        return obj.weight_display

    @admin.display(description='Цена')
    def price_display(self, obj):
        if obj.old_price:
            return format_html(
                '<span style="text-decoration:line-through;opacity:.5;">{} ₽</span> '
                '<b style="color:#d9531e;">{} ₽</b>',
                int(obj.old_price), int(obj.price),
            )
        return f'{int(obj.price)} ₽'
