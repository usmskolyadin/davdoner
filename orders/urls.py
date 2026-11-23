from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.cart_detail, name='cart'),
    path('cart/add/<int:product_id>/', views.cart_add, name='add'),
    path('cart/update/', views.cart_update, name='update'),
    path('cart/remove/', views.cart_remove, name='remove'),
    path('cart/check-zone/', views.check_delivery_zone, name='check_zone'),
    path('checkout/', views.checkout, name='checkout'),
    path('order/<int:pk>/success/', views.order_success, name='success'),
]
