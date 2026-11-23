from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegisterForm


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('accounts:profile')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {
        'form': form, 'meta_title': 'Регистрация — Dav Doner Club',
    })


@login_required
def profile(request):
    orders = request.user.orders.prefetch_related('items').all()
    return render(request, 'accounts/profile.html', {
        'orders': orders, 'meta_title': 'Личный кабинет — Dav Doner Club',
    })
