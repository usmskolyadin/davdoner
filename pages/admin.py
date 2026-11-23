from django.contrib import admin
from django.shortcuts import redirect
from django.utils.html import format_html

from .models import Benefit, HeroBanner, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Бренд', {'fields': ('site_name', 'tagline', 'phone')}),
        ('Соцсети', {'fields': ('instagram_url', 'telegram_url', 'whatsapp_url')}),
        ('Подвал сайта', {'fields': ('footer_text',)}),
        ('SEO по умолчанию', {'fields': ('seo_default_title', 'seo_default_description')}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SiteSettings.load()
        return redirect('admin:pages_sitesettings_change', obj.pk)


@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):
    list_display = ('preview', 'title', 'subtitle', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    readonly_fields = ('preview',)

    @admin.display(description='Фото')
    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:48px;width:84px;object-fit:cover;border-radius:8px;">',
                obj.image.url,
            )
        return '—'


@admin.register(Benefit)
class BenefitAdmin(admin.ModelAdmin):
    list_display = ('icon', 'title', 'subtitle', 'order', 'is_active')
    list_editable = ('order', 'is_active')
