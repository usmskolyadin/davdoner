from django import forms

from .models import Order


class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'customer_name', 'phone', 'delivery_type', 'address',
            'comment', 'preferred_time', 'payment_method',
        ]
        widgets = {
            'customer_name': forms.TextInput(attrs={'placeholder': 'Ваше имя', 'class': 'input'}),
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
        return cleaned_data
