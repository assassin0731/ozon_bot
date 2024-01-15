from funcs import *
import telebot
from telebot import types
from math import ceil
from dotenv import load_dotenv
import os

load_dotenv()

bot = telebot.TeleBot(os.getenv('TOKEN'))


@bot.message_handler(commands=['start'])
def start(message):
    msg = bot.send_message(message.chat.id, 'Введите id и ключ')
    bot.register_next_step_handler(msg, enter_key)


def enter_key(message):
    """Функция требует ввода id и ключа для подключения к Ozon-Api."""
    try:
        id_, key = message.text.split()
        headers = {
            "Host": "api-seller.ozon.ru",
            "Client-Id": id_,
            "Api-Key": key,
            "Content-Type": "application/json"
        }
        get_url = "https://api-seller.ozon.ru/v1/report/warehouse/stock"
        json_data = {"language": "DEFAULT",
                     "warehouseId": ["1020000673766000"]}

        id_code = requests.post(get_url, headers=headers, json=json_data).json()
        if 'code' in id_code:
            raise WrongIdKey('Wrong Id or Key')
        goods = Goods()
        goods.oz_goods = load_ozon_stock(headers, id_code)
        stock_dict[message.chat.id] = goods
        main_menu(message, headers)
    except ValueError:
        msg = bot.send_message(message.chat.id, 'Некорректный ввод, введите Id и ключ через пробел')
        bot.register_next_step_handler(msg, enter_key)
    except WrongIdKey:
        msg = bot.send_message(message.chat.id, 'Неправильный Id или ключ')
        bot.register_next_step_handler(msg, enter_key)


def main_menu(message, headers):
    """Главное меню бота."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("1. Сравнить остатки на складах")
    btn2 = types.KeyboardButton("2. Список товаров вне акций")
    btn3 = types.KeyboardButton("3. Обновить цены на товары")
    btn4 = types.KeyboardButton("4. Невыгодные скидки по акции")
    markup.add(btn1, btn2, btn3, btn4)
    msg = bot.send_message(message.chat.id, '1. Позволяет получить список товаров, которые отсутствуют на складе '
                                            'поставщика, но имеют ненулевые остатки на озон-складе, и наоборот. \n'
                                            '2. Возвращает список артикулов товаров, которые не участвуют в акциях. \n'
                                            '3. Обновляет цены на  из файла-каталога от поставщика.\n'
                                            '4. Возвращает список артикулов товаров с невыгодной ценой по акции.',
                           reply_markup=markup)
    bot.register_next_step_handler(msg, main_menu_chose, headers)


def main_menu_chose(message, headers):
    """Вызов функций в зависимости от выбора в главном меню"""
    if message.text == "1. Сравнить остатки на складах":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("Вернуться в меню")
        markup.add(btn1)
        msg = bot.send_message(message.chat.id, 'Загрузите файл с данными об остатках', reply_markup=markup)
        bot.register_next_step_handler(msg, load_xlsx, headers)
    if message.text == "3. Обновить цены на товары":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("Вернуться в меню")
        markup.add(btn1)
        msg = bot.send_message(message.chat.id, 'Загрузите файл с ценами поставщика', reply_markup=markup)
        bot.register_next_step_handler(msg, update_prices, headers)
    if message.text == "4. Невыгодные скидки по акции":
        no_profit_price(message, headers)
    if message.text == "2. Список товаров вне акций":
        goods_not_in_sale(message, headers)


def no_profit_price(message, headers):
    """Выводит артикулы товаров с невыгодной ценой"""
    goods_with_id, goods_in_sale = get_sales_data(headers, 'check_profit')

    bad_profit = set()

    for good, discount in goods_in_sale.items():
        if not 39.99 < discount < 45.01 and good in goods_with_id:
            bad_profit.add(goods_with_id[good])

    bot.reply_to(message, '\n'.join(bad_profit))
    main_menu(message, headers)


def goods_not_in_sale(message, headers):
    """Выводит артикулы товаров, не учавствующих в акциях"""
    goods_with_id, goods_in_sale = get_sales_data(headers, 'check_sale')

    not_in_sale_id = set(goods_with_id.keys()) - goods_in_sale
    not_in_sale_article = set()
    not_zero_stock = {key for key, val in stock_dict[message.chat.id].oz_goods.items() if val != 0}
    for val in not_in_sale_id:
        if goods_with_id[val] in not_zero_stock:
            not_in_sale_article.add(goods_with_id[val])

    if not not_in_sale_article:
        bot.reply_to(message, 'Все товары в акции')
    else:
        bot.reply_to(message, '\n'.join(not_in_sale_article))
    main_menu(message, headers)


def update_prices(message, headers):
    """Обновляет цены на товары, новые цены берутся из файла-каталога поставщика"""
    if not message.document.file_name.endswith(('xls', 'xlsx')):
        raise WrongFile('Not Excel file')
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    shop_stock = pd.read_excel(downloaded_file, header=5)
    if 'Катал. номер' not in shop_stock or 'ОПТ' not in shop_stock:
        raise WrongFile('Wrong Excel File')
    shop_stock['article'] = shop_stock.pop('Катал. номер')
    shop_stock['price'] = shop_stock.pop('ОПТ')

    shop_prices = dict()
    for art, price in zip(shop_stock['article'], shop_stock['price']):
        if str(art).startswith(needed_art):
            shop_prices[str(art)] = ceil(price)

    json_data = {
        "prices": []
    }

    articles = set(stock_dict[message.chat.id].oz_goods.keys())
    for art, price in shop_prices.items():
        if art in articles:
            json_data['prices'].append(
                {
                    "auto_action_enabled": "UNKNOWN",
                    "currency_code": "RUB",
                    "offer_id": str(art),
                    "price": str(ceil((1.3 * price + 100) / (0.75 * 0.65))),
                    "price_strategy_enabled": "UNKNOWN"
                }
            )
    get_url = 'https://api-seller.ozon.ru/v1/product/import/prices'
    requests.post(get_url, headers=headers, json=json_data)
    bot.reply_to(message, 'Цены обновлены')
    main_menu(message, headers)


def load_ozon_stock(headers, id_code):
    """Выгрузка товаров из ЛК Ozon-Seller"""
    while True:
        resp_data = requests.post("https://api-seller.ozon.ru/v1/report/info", headers=headers,
                                  json=id_code["result"]).json()
        if resp_data['result']['status'] == 'success':
            break

    xl_file = pd.read_excel(resp_data["result"]["file"], header=0)

    xl_file['article'] = xl_file.pop('Unnamed: 2') if 'Unnamed: 2' in xl_file else xl_file.pop('Артикул')
    xl_file['count'] = xl_file.pop('Unnamed: 4') if 'Unnamed: 4' in xl_file \
        else xl_file.pop('Доступно на моем складе, шт')

    goods = dict()
    for art, count in zip(xl_file['article'], xl_file['count']):
        if art.startswith(needed_art) and not art.endswith(('_', '_1', '_2', '_3', '_4')):
            goods[art] = count
    return goods


def load_xlsx(message, headers):
    """Выгрузка товаров из файла-каталога поставщика"""
    if message.text == "Вернуться в меню":
        main_menu(message, headers)
    else:
        try:
            if not message.document.file_name.endswith(('xls', 'xlsx')):
                raise WrongFile('Not Excel file')
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            shop_stock = pd.read_excel(downloaded_file, header=5)
            if 'Катал. номер' not in shop_stock or 'НГЛ' not in shop_stock:
                raise WrongFile('Wrong Excel File')
            shop_stock['article'] = shop_stock.pop('Катал. номер')
            shop_stock['count'] = shop_stock.pop('НГЛ')
            stock = stock_dict[message.chat.id]

            stock.shop_stock = dict()
            for art, count in zip(shop_stock['article'], shop_stock['count']):
                if str(art).startswith(needed_art) and len(art) <= 10:
                    stock.shop_stock[art] = count

            menu_stock(message, headers)

        except Exception as e:
            msg = bot.send_message(message.chat.id, e)
            bot.register_next_step_handler(msg, load_xlsx)


def menu_stock(message, headers):
    """Меню для сравнения остатков товара"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Нулевые на моем складе")
    btn2 = types.KeyboardButton("Нулевые на складе поставщика")
    btn3 = types.KeyboardButton("В главное меню")
    markup.add(btn1, btn2, btn3)
    msg = bot.send_message(message.chat.id, 'Что нужно сделать?', reply_markup=markup)
    bot.register_next_step_handler(msg, choose_action, headers)


def choose_action(message, headers):
    """Вызов соответствующей функции в зависимости от выбора в меню"""
    if message.text == "Нулевые на моем складе":
        bot.send_message(message.chat.id, '\n'.join(check_if_not_empty(message)))
        menu_stock(message, headers)
    if message.text == "Нулевые на складе поставщика":
        bot.send_message(message.chat.id, '\n'.join(check_if_empty(message)))
        menu_stock(message, headers)
    if message.text == "В главное меню":
        main_menu(message, headers)


if __name__ == '__main__':
    bot.polling(non_stop=True)
