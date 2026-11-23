from django.urls import path

from . import views

app_name = 'menu'

urlpatterns = [
    path('menu/', views.catalog, name='catalog'),
    path('menu/search/', views.search, name='search'),
    path('menu/<slug:slug>/', views.category_detail, name='category'),
    path('product/<slug:slug>/', views.product_detail, name='product'),
]
