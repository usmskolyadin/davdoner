from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand

from accounts.models import Profile
from menu.models import Addon, Category, Product
from orders.models import DeliverySettings, Order, OrderItem
from pages.models import Benefit, HeroBanner, SiteSettings

IMG_DIR = __import__('pathlib').Path(__file__).resolve().parent.parent.parent / 'seed_images'

User = get_user_model()


def img(name):
    path = IMG_DIR / name
    if not path.exists():
        return None
    return File(open(path, 'rb'), name=name)


CATEGORIES = [
    dict(name='Мангал', slug='mangal', icon='🔥', order=1,
         description='Шашлыки, люля и стейки, приготовленные на углях.', cover='banner_mangal.jpg'),
    dict(name='Боулы и салаты', slug='bowls-salads', icon='🥗', order=2,
         description='Сбалансированные блюда из свежих ингредиентов.', cover='banner_bowls.jpg'),
    dict(name='Донеры и роллы', slug='doner-rolly', icon='🌯', order=3,
         description='Сочные донеры и роллы в лаваше, готовим после заказа.', cover='banner_doner.jpg'),
    dict(name='Супы', slug='soups', icon='🍲', order=4,
         description='Горячие супы для сытного обеда.', cover='banner_soup.jpg'),
    dict(name='Закуски и гарниры', slug='snacks', icon='🍟', order=5,
         description='Дополнение к любому блюду.', cover=None),
    dict(name='Десерты', slug='desserts', icon='🍰', order=6,
         description='Немного сладкого к завершению трапезы.', cover='banner_dessert.jpg'),
    dict(name='Напитки', slug='drinks', icon='🥤', order=7,
         description='Классические напитки — фото скоро добавим.', cover=None),
]

ADDONS = [
    ('Острый соус', 30), ('Сырный соус', 40), ('Соус тахини', 40),
    ('Авокадо', 80), ('Сыр фета', 60), ('Доп. порция мяса', 150), ('Лаваш дополнительно', 50),
]

PRODUCTS = [
    # category_slug, name, short_desc, composition, weight, unit, price, old_price, popular, stop, calories/prot/fat/carb, image, addons
    ('mangal', 'Шашлык из курицы', 'Сочное куриное филе в фирменном маринаде',
     'Куриное филе, фирменный маринад на специях, лук, зелень.', 300, 'г', 650, None, True, False,
     (410, 34, 22, 6), 'mangal_1.jpg', ['Острый соус']),
    ('mangal', 'Каре ягнёнка', 'Нежные рёбрышки ягнёнка, маринад с травами и специями',
     'Каре ягнёнка, розмарин, чеснок, оливковое масло, специи.', 350, 'г', 1290, None, False, False,
     (520, 29, 40, 3), 'mangal_2.jpg', []),
    ('mangal', 'Люля-кебаб из говядины', 'Классический люля-кебаб с ароматными специями',
     'Рубленая говядина, лук, специи, зелень, маринованный лук.', 300, 'г', 790, 890, True, False,
     (470, 26, 36, 5), 'mangal_3.jpg', ['Острый соус']),
    ('mangal', 'Стейк из лосося', 'Лосось на мангале с лимоном и оливковым маслом',
     'Стейк лосося, спаржа, лимон, оливковое масло, розмарин.', 280, 'г', 1190, None, True, False,
     (390, 32, 24, 2), 'mangal_4.jpg', []),

    ('bowls-salads', 'Боул с курицей', 'Куриное филе на мангале, киноа, авокадо, черри, соус тахини',
     'Куриное филе на мангале, киноа, авокадо, томаты черри, микс-салат, соус тахини.', 350, 'г', 690, None,
     True, False, (480, 31, 20, 42), 'bowl_1.jpg', ['Авокадо', 'Соус тахини']),
    ('bowls-salads', 'Боул с креветками', 'Креветки, авокадо, манго, эдамаме, соус терияки',
     'Креветки, авокадо, манго, эдамаме, микс-салат, соус терияки.', 320, 'г', 890, None, True, False,
     (410, 24, 16, 38), 'bowl_2.jpg', ['Авокадо']),
    ('bowls-salads', 'Боул с тунцом', 'Тунец, авокадо, рис, чука, огурец, соус понзу',
     'Тунец, авокадо, рис, водоросли чука, огурец, кунжут, соус понзу.', 320, 'г', 990, None, False, False,
     (430, 27, 18, 40), 'bowl_3.jpg', []),
    ('bowls-salads', 'Боул с лососем', 'Лосось на мангале, авокадо, огурец, цитрусовая заправка',
     'Лосось на мангале, авокадо, огурец, кунжут, цитрусовая заправка.', 350, 'г', 1190, None, False, False,
     (460, 29, 22, 35), 'bowl_4.jpg', ['Авокадо']),
    ('bowls-salads', 'Салат с бурратой', 'Буррата, томаты, руккола, кедровые орехи, соус песто',
     'Буррата, томаты черри, руккола, кедровые орехи, соус песто.', 250, 'г', 890, None, False, False,
     (380, 16, 30, 12), 'salad_1.jpg', []),
    ('bowls-salads', 'Греческий салат', 'Томаты, огурцы, болгарский перец, красный лук, оливки, сыр фета',
     'Томаты, огурцы, болгарский перец, красный лук, оливки, сыр фета, оливковое масло.', 280, 'г', 690, None,
     False, False, (310, 9, 24, 13), 'salad_2.jpg', ['Сыр фета']),
    ('bowls-salads', 'Тёплый салат с курицей', 'Куриное филе на мангале, овощи, микс-салат',
     'Куриное филе на мангале, печёные овощи, микс-салат, заправка.', 300, 'г', 790, None, False, False,
     (360, 28, 18, 14), 'salad_3.jpg', []),
    ('bowls-salads', 'Салат с киноа', 'Киноа, авокадо, гранат, сыр фета, цитрусовая заправка',
     'Киноа, авокадо, гранат, сыр фета, микс-салат, цитрусовая заправка.', 280, 'г', 690, None, False, False,
     (340, 11, 19, 30), 'salad_4.jpg', ['Сыр фета']),

    ('doner-rolly', 'Донер с курицей', 'Курица на мангале, свежие овощи, соус йогуртовый',
     'Лаваш, курица на мангале, свежие овощи, соус йогуртовый.', 350, 'г', 420, None, True, False,
     (560, 28, 22, 54), 'doner_1.jpg', ['Острый соус', 'Сырный соус']),
    ('doner-rolly', 'Ролл с курицей', 'Лаваш, курица и овощи',
     'Лаваш, куриное филе, огурец, томаты, соус.', 300, 'г', 390, None, False, False,
     None, 'doner_2.jpg', ['Острый соус']),
    ('doner-rolly', 'Донер с овощами', 'Свежие овощи и фирменный соус',
     'Лаваш, свежие овощи, зелень, фирменный соус.', 320, 'г', 350, None, False, False,
     None, 'doner_3.jpg', []),
    ('doner-rolly', 'Ролл с начинкой', 'Лаваш и свежие ингредиенты',
     'Лаваш, куриное филе, сыр, свежие овощи.', 300, 'г', 450, 520, False, False,
     None, 'doner_4.jpg', ['Доп. порция мяса']),

    ('soups', 'Суп дня', 'Горячий суп из меню кафе', 'Состав уточняется у повара дня.', 300, 'мл', 290, None,
     False, False, None, 'soup_1.jpg', []),
    ('soups', 'Борщ', 'Наваристый борщ с говядиной и сметаной',
     'Говядина, свёкла, капуста, картофель, томаты, сметана.', 320, 'мл', 320, None, True, False,
     (210, 12, 9, 20), 'soup_2.jpg', []),
    ('soups', 'Суп с насыщенным бульоном', 'Фирменный суп с насыщенным мясным бульоном',
     'Говяжий бульон, овощи, зелень, специи.', 300, 'мл', 350, None, False, True,
     None, 'soup_3.jpg', []),
    ('soups', 'Овощной суп', 'Свежая зелень и ароматный бульон',
     'Сезонные овощи, зелень, растительный бульон.', 300, 'мл', 280, None, False, False,
     (140, 4, 5, 20), 'soup_4.jpg', []),

    ('snacks', 'Картофель по-деревенски', 'Жареные картофельные шарики с зеленью',
     'Картофель, панировка, зелень, специи.', 200, 'г', 250, None, False, False, None, 'snack_1.jpg', []),
    ('snacks', 'Овощи гриль с гарниром', 'Картофель, люля и свежие овощи',
     'Картофель, овощи гриль, свежий салат.', 280, 'г', 320, None, False, False, None, 'snack_2.jpg', []),
    ('snacks', 'Грибы запечённые', 'Шампиньоны, запечённые с зеленью',
     'Шампиньоны, зелень, специи, растительное масло.', 200, 'г', 290, None, False, False, None, 'snack_3.jpg', []),
    ('snacks', 'Крылышки куриные', 'Куриные крылышки с луком и специями',
     'Куриные крылышки, маринованный лук, специи.', 250, 'г', 390, None, False, False, None, 'snack_4.jpg', ['Острый соус']),

    ('desserts', 'Медовик', 'Нежный медовый торт с ароматом апельсина',
     'Медовые коржи, сметанный крем, цитрус.', 150, 'г', 280, None, True, False,
     (340, 5, 16, 42), 'dessert_1.jpg', []),
    ('desserts', 'Чизкейк Нью-Йорк', 'Классический чизкейк на песочной основе',
     'Сливочный сыр, песочная основа, ягодный соус.', 130, 'г', 320, None, False, False, None, None, []),
    ('desserts', 'Брауни', 'Шоколадный брауни с грецким орехом',
     'Тёмный шоколад, грецкий орех, сливочное масло.', 100, 'г', 250, None, False, False, None, None, []),
    ('desserts', 'Тирамису', 'Классический тирамису с маскарпоне',
     'Маскарпоне, савоярди, кофе, какао.', 120, 'г', 310, None, False, False, None, None, []),

    ('drinks', 'Лимонад домашний', 'Освежающий лимонад с мятой', 'Вода, лимон, мята, сахар.', 400, 'мл', 190,
     None, False, False, None, None, []),
    ('drinks', 'Морс клюквенный', 'Домашний морс из клюквы', 'Клюква, вода, сахар.', 400, 'мл', 180, None,
     False, False, None, None, []),
    ('drinks', 'Чай каркаде', 'Освежающий чай каркаде', 'Каркаде, вода, сахар по желанию.', 300, 'мл', 150,
     None, False, False, None, None, []),
    ('drinks', 'Компот домашний', 'Компот из сезонных фруктов', 'Сезонные фрукты, вода, сахар.', 300, 'мл', 160,
     None, False, False, None, None, []),
    ('drinks', 'Вода негазированная', '0.5 л', 'Питьевая вода без газа.', 500, 'мл', 100, None, False, False,
     None, None, []),
    ('drinks', 'Кола', '0.33 л', 'Газированный напиток.', 330, 'мл', 120, None, False, False, None, None, []),
]

BENEFITS = [
    ('🌿', 'Свежие продукты', 'Закупаем каждый день'),
    ('🔥', 'Блюда на мангале', 'Готовим на углях'),
    ('🥗', 'Сбалансированное меню', 'Боулы, салаты и супы'),
    ('❤️', 'Готовим с заботой', 'Без лишних добавок'),
]


class Command(BaseCommand):
    help = 'Заполняет сайт демонстрационными данными: категории, блюда, баннер, настройки доставки.'

    def handle(self, *args, **options):
        self.seed_site_settings()
        self.seed_delivery_settings()
        self.seed_benefits()
        categories = self.seed_categories()
        self.seed_banner()
        addons = self.seed_addons()
        self.seed_products(categories, addons)
        self.seed_users_and_order(categories)
        self.stdout.write(self.style.SUCCESS('Демо-данные успешно загружены.'))

    def seed_site_settings(self):
        s = SiteSettings.load()
        s.site_name = 'Dav Doner Club'
        s.tagline = 'Здоровый стритфуд'
        s.phone = '+7 (495) 123-45-67'
        s.footer_text = 'Донеры, боулы, блюда на мангале и десерты из свежих ингредиентов. Готовим после заказа.'
        s.instagram_url = 'https://instagram.com/'
        s.telegram_url = 'https://t.me/'
        s.save()

    def seed_delivery_settings(self):
        d = DeliverySettings.load()
        d.cafe_address = 'Москва, Кутузовский проспект, 36, строение 15'
        d.cafe_lat = Decimal('55.739037')
        d.cafe_lon = Decimal('37.532955')
        d.delivery_radius_km = Decimal('1.0')
        d.min_order_amount = Decimal('1000')
        d.free_delivery_threshold = Decimal('3000')
        d.paid_delivery_cost = Decimal('250')
        d.phone = '+7 (495) 123-45-67'
        d.work_hours = 'Ежедневно, 10:00 – 23:00'
        d.preferred_time_enabled = True
        d.save()

    def seed_benefits(self):
        Benefit.objects.all().delete()
        for order, (icon, title, subtitle) in enumerate(BENEFITS, start=1):
            Benefit.objects.create(icon=icon, title=title, subtitle=subtitle, order=order)

    def seed_categories(self):
        categories = {}
        for data in CATEGORIES:
            cover_name = data.pop('cover')
            cat, _ = Category.objects.update_or_create(slug=data['slug'], defaults=data)
            if cover_name:
                cat.cover.save(cover_name, img(cover_name), save=True)
            categories[data['slug']] = cat
        return categories

    def seed_banner(self):
        HeroBanner.objects.all().delete()
        banner = HeroBanner(
            title='Вкусный и полезный стритфуд',
            subtitle='Донеры, боулы, салаты и блюда на мангале из свежих ингредиентов.',
            badge_text='Готовим на мангале каждый день',
            cta_text='Смотреть меню',
            cta_link='/menu/',
            is_active=True,
        )
        image_file = img('hero_main.jpg')
        if image_file:
            banner.image.save('hero_main.jpg', image_file, save=False)
        banner.save()

    def seed_addons(self):
        addons = {}
        for name, price in ADDONS:
            addon, _ = Addon.objects.update_or_create(name=name, defaults={'price': Decimal(price)})
            addons[name] = addon
        return addons

    def seed_products(self, categories, addons):
        Product.objects.all().delete()
        order_counter = {}
        for row in PRODUCTS:
            (cat_slug, name, short_desc, composition, weight, unit, price, old_price,
             popular, stop, nutrition, image_name, addon_names) = row
            order_counter[cat_slug] = order_counter.get(cat_slug, 0) + 1

            product = Product(
                category=categories[cat_slug],
                name=name,
                slug=self._slugify(name),
                short_description=short_desc,
                composition=composition,
                weight_value=weight,
                weight_unit=unit,
                price=Decimal(price),
                old_price=Decimal(old_price) if old_price else None,
                is_active=True,
                is_stop_list=stop,
                is_popular=popular,
                order=order_counter[cat_slug],
            )
            if nutrition:
                product.calories, product.proteins, product.fats, product.carbs = nutrition
            if image_name:
                image_file = img(image_name)
                if image_file:
                    product.image.save(image_name, image_file, save=False)
            product.save()
            if addon_names:
                product.addons.set([addons[n] for n in addon_names if n in addons])

    def seed_users_and_order(self, categories):
        if not User.objects.filter(is_superuser=True).exists():
            admin = User.objects.create_superuser('admin', 'admin@davdoner.local', 'DavDoner2026!')
            self.stdout.write(self.style.WARNING(
                f'Создан суперпользователь: {admin.username} / DavDoner2026! — смените пароль после входа.'
            ))

        demo_user, created = User.objects.get_or_create(
            username='demo_client', defaults={'first_name': 'Алина', 'email': 'demo@davdoner.local'},
        )
        if created:
            demo_user.set_password('DemoClient2026!')
            demo_user.save()
        Profile.objects.update_or_create(
            user=demo_user, defaults={'phone': '+7 (999) 123-45-67', 'default_address': 'Москва, Кутузовский проспект, 10'},
        )

        if not Order.objects.exists():
            donor = Product.objects.filter(category__slug='doner-rolly').first()
            bowl = Product.objects.filter(category__slug='bowls-salads').first()
            order = Order.objects.create(
                user=demo_user,
                customer_name='Алина',
                phone='+7 (999) 123-45-67',
                delivery_type=Order.DeliveryType.DELIVERY,
                address='Москва, Кутузовский проспект, 10',
                distance_km=Decimal('0.6'),
                comment='Позвонить за 10 минут, пожалуйста.',
                preferred_time='Как можно скорее',
                items_total=donor.price + bowl.price,
                delivery_cost=Decimal('0'),
                total=donor.price + bowl.price,
                status=Order.Status.COMPLETED,
                payment_method=Order.PaymentMethod.CARD_ON_DELIVERY,
                payment_status=Order.PaymentStatus.PAID,
            )
            for product in (donor, bowl):
                OrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    unit_price=product.price, quantity=1, line_total=product.price,
                )

    @staticmethod
    def _slugify(name):
        translit = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z',
            'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
            'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '-', '-': '-',
        }
        result = ''.join(translit.get(ch, ch) for ch in name.lower())
        result = ''.join(ch for ch in result if ch.isalnum() or ch == '-')
        while '--' in result:
            result = result.replace('--', '-')
        return result.strip('-')
