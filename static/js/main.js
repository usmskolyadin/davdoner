(function () {
  'use strict';

  function csrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  // ---- Mobile category menu toggle ---------------------------------
  const menuToggle = document.querySelector('[data-menu-toggle]');
  const categoryNav = document.querySelector('[data-category-nav]');
  if (menuToggle && categoryNav) {
    menuToggle.addEventListener('click', function () {
      categoryNav.classList.toggle('is-open');
    });
  }

  // ---- Sort select navigates with ?sort= ---------------------------
  document.querySelectorAll('[data-sort-select]').forEach(function (select) {
    select.addEventListener('change', function () {
      const url = new URL(window.location.href);
      url.searchParams.set('sort', select.value);
      window.location.href = url.toString();
    });
  });

  // ---- Quantity steppers --------------------------------------------
  document.querySelectorAll('[data-qty-stepper]').forEach(function (stepper) {
    const input = stepper.querySelector('[data-qty-input]');
    const minus = stepper.querySelector('[data-qty-minus]');
    const plus = stepper.querySelector('[data-qty-plus]');
    const isCartRow = stepper.classList.contains('qty-stepper--cart');

    function submitIfCartRow() {
      if (isCartRow && stepper.tagName === 'FORM') {
        stepper.requestSubmit ? stepper.requestSubmit() : stepper.submit();
      }
    }

    minus && minus.addEventListener('click', function () {
      const value = Math.max(1, parseInt(input.value || '1', 10) - 1);
      input.value = value;
      submitIfCartRow();
    });
    plus && plus.addEventListener('click', function () {
      const value = parseInt(input.value || '1', 10) + 1;
      input.value = value;
      submitIfCartRow();
    });
    if (isCartRow && input) {
      input.addEventListener('change', submitIfCartRow);
    }
  });

  // ---- Add to cart: progressive AJAX enhancement --------------------
  const cartBadge = document.querySelector('[data-cart-badge]');

  function updateCartBadge(count) {
    if (!cartBadge) return;
    cartBadge.textContent = count;
    cartBadge.style.display = count > 0 ? 'flex' : 'none';
  }

  // ---- Toast notifications -------------------------------------------
  const toastContainer = document.querySelector('[data-toast-container]');

  function showToast(message) {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    const icon = document.createElement('span');
    icon.className = 'toast__icon';
    icon.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M4 12.5l5 5L20 6" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const text = document.createElement('span');
    text.textContent = message;
    toast.appendChild(icon);
    toast.appendChild(text);
    toastContainer.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add('is-visible'); });
    setTimeout(function () {
      toast.classList.remove('is-visible');
      setTimeout(function () { toast.remove(); }, 250);
    }, 2600);
  }

  document.querySelectorAll('.add-to-cart-form, .product-page__order').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (!window.fetch) return; // let it submit normally
      event.preventDefault();
      const button = form.querySelector('[data-add-to-cart]');
      const productName = form.dataset.productName || 'Товар';
      const formData = new FormData(form);
      fetch(form.action, { method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.ok) {
            updateCartBadge(data.count);
            showToast('«' + productName + '» добавлен в корзину');
            if (button) {
              button.classList.add('is-added');
              setTimeout(function () { button.classList.remove('is-added'); }, 700);
            }
          }
        })
        .catch(function () { form.submit(); });
    });
  });

  // ---- Horizontal sliders (arrow controls instead of the native scrollbar)
  document.querySelectorAll('[data-slider]').forEach(function (slider) {
    const track = slider.querySelector('[data-scroll-row]');
    const prevBtn = slider.querySelector('[data-slider-prev]');
    const nextBtn = slider.querySelector('[data-slider-next]');
    if (!track) return;

    function update() {
      const max = track.scrollWidth - track.clientWidth - 2;
      if (prevBtn) prevBtn.disabled = track.scrollLeft <= 0;
      if (nextBtn) nextBtn.disabled = track.scrollLeft >= max;
    }

    function scrollByStep(direction) {
      const card = track.querySelector('.dish-card');
      const step = card ? card.getBoundingClientRect().width + 18 : track.clientWidth * 0.8;
      track.scrollBy({ left: direction * step * 2, behavior: 'smooth' });
    }

    if (prevBtn) prevBtn.addEventListener('click', function () { scrollByStep(-1); });
    if (nextBtn) nextBtn.addEventListener('click', function () { scrollByStep(1); });
    track.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    update();
  });

  // ---- Checkout: delivery/pickup toggle + live totals ---------------
  const checkoutForm = document.querySelector('[data-checkout-form]');
  if (checkoutForm) {
    const deliveryFields = document.querySelector('[data-delivery-fields]');
    const radios = checkoutForm.querySelectorAll('input[name=delivery_type]');
    const itemsTotal = parseFloat(checkoutForm.dataset.itemsTotal || '0');
    const minOrder = parseFloat(checkoutForm.dataset.minOrder || '0');
    const freeThreshold = parseFloat(checkoutForm.dataset.freeThreshold || '0');
    const paidCost = parseFloat(checkoutForm.dataset.paidCost || '0');

    const sumDelivery = checkoutForm.querySelector('[data-sum-delivery]');
    const sumTotal = checkoutForm.querySelector('[data-sum-total]');
    const deliveryMessage = checkoutForm.querySelector('[data-delivery-message]');

    function currentType() {
      const checked = checkoutForm.querySelector('input[name=delivery_type]:checked');
      return checked ? checked.value : 'delivery';
    }

    function recalc() {
      const isDelivery = currentType() === 'delivery';
      if (deliveryFields) deliveryFields.style.display = isDelivery ? '' : 'none';

      let cost = 0;
      let message = 'Самовывоз бесплатный.';
      if (isDelivery) {
        if (itemsTotal < minOrder) {
          message = `Минимальная сумма заказа для доставки — ${minOrder.toFixed(0)} ₽. Добавьте в корзину ещё на ${(minOrder - itemsTotal).toFixed(0)} ₽ или выберите самовывоз.`;
        } else if (itemsTotal >= freeThreshold) {
          message = 'Доставка бесплатная!';
        } else {
          cost = paidCost;
          message = `Добавьте ещё на ${(freeThreshold - itemsTotal).toFixed(0)} ₽ до бесплатной доставки.`;
        }
      }
      if (sumDelivery) sumDelivery.textContent = cost.toFixed(0) + ' ₽';
      if (sumTotal) sumTotal.textContent = (itemsTotal + cost).toFixed(0) + ' ₽';
      if (deliveryMessage) deliveryMessage.textContent = message;
    }

    radios.forEach(function (radio) { radio.addEventListener('change', recalc); });
    recalc();

    // ---- Geolocation delivery zone check -----------------------------
    const checkZoneBtn = checkoutForm.querySelector('[data-check-zone]');
    const zoneResult = checkoutForm.querySelector('[data-zone-result]');
    const distanceInput = checkoutForm.querySelector('[data-distance-input]');

    if (checkZoneBtn) {
      checkZoneBtn.addEventListener('click', function () {
        if (!navigator.geolocation) {
          zoneResult.textContent = 'Геолокация не поддерживается этим браузером — укажите адрес вручную.';
          return;
        }
        zoneResult.textContent = 'Определяем местоположение…';
        navigator.geolocation.getCurrentPosition(function (position) {
          const formData = new FormData();
          formData.append('lat', position.coords.latitude);
          formData.append('lon', position.coords.longitude);
          fetch('/cart/check-zone/', {
            method: 'POST', body: formData,
            headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfToken() },
          })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data.ok) {
                zoneResult.textContent = data.message;
                zoneResult.classList.toggle('field-error', !data.within_zone);
                if (distanceInput) distanceInput.value = data.distance_km;
              } else {
                zoneResult.textContent = data.error || 'Не удалось проверить адрес.';
              }
            })
            .catch(function () { zoneResult.textContent = 'Не удалось проверить адрес.'; });
        }, function () {
          zoneResult.textContent = 'Не удалось определить местоположение — разрешите доступ к геолокации или укажите адрес вручную.';
        });
      });
    }
  }
})();
