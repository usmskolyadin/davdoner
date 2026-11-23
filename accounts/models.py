from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name='Пользователь', related_name='profile',
        on_delete=models.CASCADE,
    )
    phone = models.CharField('Телефон', max_length=32, blank=True)
    default_address = models.CharField('Адрес по умолчанию', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили покупателей'

    def __str__(self):
        return f'Профиль {self.user}'
