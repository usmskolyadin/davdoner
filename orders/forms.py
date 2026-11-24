from django import forms
from django.conf import settings

from .models import Order


class CheckoutForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not getattr(settings, 'PAYMENT_GATEWAY', ''):
            self.fields['payment_method'].choices = [
                choice for choice in self.fields['payment_method'].choices
                if choice[0] != Order.PaymentMethod.ONLINE
            ]

    class Meta:
        model = Order
        fields = [
            'customer_name', 'customer_email', 'phone', 'delivery_type', 'address',
            'comment', 'preferred_time', 'payment_method',
        ]
        widgets = {
            'customer_name': forms.TextInput(attrs={'placeholder': 'Ваше имя', 'class': 'input'}),
            'customer_email': forms.EmailInput(attrs={'placeholder': 'name@example.com', 'class': 'input'}),
            'phone': forms.TextInput(attrs={'placeholder': '+7 (___) ___-__-__', 'class': 'input'}),
            'delivery_type': forms.RadioSelect,
            'address': forms.TextInput(attrs={
                'placeholder': 'Улица, дом, квартира', 'class': 'input',
            }),
            'comment': forms.Textarea(attrs={
                'placeholder': 'Например: позвонить за 10 минут, домофон не работает…',
                'class': 'input', 'rows': 3,
            }),
            'preferred_time': forms.TextInput(attrs={
                'placeholder': 'Как можно скорее', 'class': 'input',
            }),
            'payment_method': forms.RadioSelect,
        }
        labels = {
            'customer_name': 'Имя',
            'customer_email': 'Email для кассового чека',
            'phone': 'Телефон',
            'delivery_type': 'Способ получения',
            'address': 'Адрес доставки',
            'comment': 'Комментарий к заказу',
            'preferred_time': 'Желаемое время',
            'payment_method': 'Способ оплаты',
        }

    def clean(self):
        cleaned_data = super().clean()
        delivery_type = cleaned_data.get('delivery_type')
        address = cleaned_data.get('address')
        if delivery_type == Order.DeliveryType.DELIVERY and not address:
            self.add_error('address', 'Укажите адрес доставки.')
        if (
            settings.TOCHKA_FISCALIZATION_ENABLED
            and cleaned_data.get('payment_method') == Order.PaymentMethod.ONLINE
            and not cleaned_data.get('customer_email')
        ):
            self.add_error('customer_email', 'Укажите email для кассового чека.')
        return cleaned_data
