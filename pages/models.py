from django.db import models


class SiteSettings(models.Model):
    site_name = models.CharField('Название бренда', max_length=100, default='Dav Doner Club')
    tagline = models.CharField('Слоган', max_length=150, default='Здоровый стритфуд')
    phone = models.CharField('Телефон для шапки сайта', max_length=32, default='+7 (495) 000-00-00')
    instagram_url = models.URLField('Instagram', blank=True)
    telegram_url = models.URLField('Telegram', blank=True)
    whatsapp_url = models.URLField('WhatsApp', blank=True)
    footer_text = models.CharField(
        'Текст в подвале сайта', max_length=255,
        default='Свежие ингредиенты, блюда на мангале и сбалансированное меню каждый день.',
    )
    seo_default_title = models.CharField(
        'SEO: заголовок по умолчанию', max_length=160,
        default='Dav Doner Club — здоровый стритфуд с доставкой и самовывозом',
    )
    seo_default_description = models.CharField(
        'SEO: описание по умолчанию', max_length=255,
        default='Донеры, боулы, блюда на мангале, супы и десерты из свежих ингредиентов. '
                 'Доставка по Москве и самовывоз.',
    )

    class Meta:
        verbose_name = 'Настройки сайта'
        verbose_name_plural = 'Настройки сайта'

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class HeroBanner(models.Model):
    title = models.CharField('Заголовок', max_length=150)
    subtitle = models.CharField('Подзаголовок', max_length=200, blank=True)
    badge_text = models.CharField(
        'Текст плашки на фото', max_length=60, blank=True,
        help_text='Например: «Донеры, боулы и блюда на мангале».',
    )
    image = models.ImageField('Фотография (справа)', upload_to='banners/')
    cta_text = models.CharField('Текст кнопки', max_length=40, default='Смотреть меню')
    cta_link = models.CharField('Ссылка кнопки', max_length=200, default='/menu/')
    is_active = models.BooleanField('Показывать на сайте', default=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'Баннер на главной'
        verbose_name_plural = 'Баннеры на главной'
        ordering = ['order', '-id']

    def __str__(self):
        return self.title


class Benefit(models.Model):
    icon = models.CharField('Иконка (emoji)', max_length=8, default='🌿')
    title = models.CharField('Заголовок', max_length=60)
    subtitle = models.CharField('Подпись', max_length=100, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Показывать', default=True)

    class Meta:
        verbose_name = 'Преимущество'
        verbose_name_plural = 'Преимущества (блок на главной)'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title
