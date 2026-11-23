from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField('Название', max_length=100)
    slug = models.SlugField('Ссылка (slug)', max_length=120, unique=True)
    icon = models.CharField(
        'Иконка (emoji)', max_length=8, blank=True,
        help_text='Например: 🔥 🥗 🌯 🍲 🍟 🍰 🥤',
    )
    cover = models.ImageField(
        'Фото для плитки категории', upload_to='categories/', blank=True, null=True,
    )
    description = models.CharField('Короткое описание', max_length=200, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Показывать на сайте', default=True)
    show_on_home = models.BooleanField('Выводить плиткой на главной', default=True)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории меню'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('menu:category', kwargs={'slug': self.slug})

    @property
    def active_products_count(self):
        return self.products.filter(is_active=True).count()


class Addon(models.Model):
    """Доп. ингредиенты, соусы и добавки к блюдам."""
    name = models.CharField('Название', max_length=100)
    price = models.DecimalField('Цена, ₽', max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField('Активна', default=True)

    class Meta:
        verbose_name = 'Добавка / соус'
        verbose_name_plural = 'Добавки и соусы'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} (+{self.price:.0f} ₽)'


class Product(models.Model):
    class WeightUnit(models.TextChoices):
        GRAM = 'г', 'граммы (г)'
        ML = 'мл', 'миллилитры (мл)'
        PCS = 'шт', 'штуки (шт)'

    category = models.ForeignKey(
        Category, verbose_name='Категория', related_name='products',
        on_delete=models.PROTECT,
    )
    name = models.CharField('Название блюда', max_length=150)
    slug = models.SlugField('Ссылка (slug)', max_length=170, unique=True)
    short_description = models.CharField(
        'Короткое описание', max_length=200, blank=True,
        help_text='Показывается в карточке в каталоге, одна-две строки.',
    )
    composition = models.TextField(
        'Состав', blank=True,
        help_text='Полный состав блюда, показывается на странице товара.',
    )
    image = models.ImageField('Фотография', upload_to='products/', blank=True, null=True)

    weight_value = models.PositiveIntegerField('Вес / объём', default=0)
    weight_unit = models.CharField(
        'Единица', max_length=4, choices=WeightUnit.choices, default=WeightUnit.GRAM,
    )

    price = models.DecimalField('Цена, ₽', max_digits=8, decimal_places=2)
    old_price = models.DecimalField(
        'Старая цена, ₽', max_digits=8, decimal_places=2, blank=True, null=True,
        help_text='Заполните, если нужно показать зачёркнутую старую цену (акция).',
    )

    calories = models.PositiveIntegerField('Калории, ккал', blank=True, null=True)
    proteins = models.DecimalField('Белки, г', max_digits=5, decimal_places=1, blank=True, null=True)
    fats = models.DecimalField('Жиры, г', max_digits=5, decimal_places=1, blank=True, null=True)
    carbs = models.DecimalField('Углеводы, г', max_digits=5, decimal_places=1, blank=True, null=True)

    addons = models.ManyToManyField(
        Addon, verbose_name='Доступные добавки', related_name='products', blank=True,
    )

    is_active = models.BooleanField(
        'Опубликовано', default=True,
        help_text='Если выключено — блюдо не показывается на сайте вовсе.',
    )
    is_stop_list = models.BooleanField(
        'Стоп-лист (временно нет)', default=False,
        help_text='Блюдо видно в каталоге, но недоступно для заказа.',
    )
    is_popular = models.BooleanField(
        'Показывать в "Популярном" на главной', default=False,
    )
    order = models.PositiveIntegerField('Порядок внутри категории', default=0)

    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Блюдо'
        verbose_name_plural = 'Блюда'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('menu:product', kwargs={'slug': self.slug})

    @property
    def is_orderable(self):
        return self.is_active and not self.is_stop_list

    @property
    def weight_display(self):
        return f'{self.weight_value} {self.weight_unit}'

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return round((1 - self.price / self.old_price) * 100)
        return 0
