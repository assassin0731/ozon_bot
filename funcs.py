import requests
import pandas as pd


class WrongIdKey(Exception):
    pass


class WrongFile(Exception):
    pass


class Goods:
    def __init__(self):
        self.oz_goods = None
        self.shop_stock = None


stock_dict = dict()


def get_sales_data(headers, func):
    """Возвращает товары, участвующие в акции. Подсчитывает скидку по акции."""
    get_url = 'https://api-seller.ozon.ru/v1/actions'
    id_code = requests.get(get_url, headers=headers).json()
    sale_id = {sale['id']: sale['participating_products_count'] for sale in id_code['result']}
    get_url = 'https://api-seller.ozon.ru/v1/actions/products'
    goods_in_sale = set() if func == 'check_sale' else dict()
    for id_, count in sale_id.items():
        json_data = {
            "action_id": id_,
            "limit": min(count, 1000),
            "offset": 0
        }
        id_code = requests.post(get_url, headers=headers, json=json_data).json()
        for good in id_code['result']['products']:
            if func == 'check_profit':
                goods_in_sale[good['id']] = (good['price'] - good['action_price']) / good['price'] * 100
            else:
                goods_in_sale.add(good['id'])

    get_url = 'https://api-seller.ozon.ru/v1/report/products/create'
    json_data = {
        "language": "DEFAULT",
        "offer_id": [],
        "search": "",
        "sku": [],
        "visibility": "ALL"
    }
    id_code = requests.post(get_url, headers=headers, json=json_data).json()
    while True:
        resp_data = requests.post("https://api-seller.ozon.ru/v1/report/info", headers=headers,
                                  json=id_code["result"]).json()
        if resp_data['result']['status'] == 'success':
            break

    xl_file = pd.read_csv(resp_data["result"]["file"], on_bad_lines='skip', delimiter=';')
    goods_with_id = dict()

    for art, id_ in zip(xl_file['Артикул'], xl_file['Ozon Product ID']):
        if art[1:].startswith(needed_art):
            goods_with_id[id_] = art[1:]
    return goods_with_id, goods_in_sale


def check_if_empty(message):
    """Проверяет, какие товары отсутсвуют на складе поставщика"""
    oz_goods = stock_dict[message.chat.id].oz_goods
    shop_stock = stock_dict[message.chat.id].shop_stock
    oz_goods = {key: val for key, val in oz_goods.items() if val != 0}
    zero_stock = set(oz_goods.keys()) - set(shop_stock.keys())
    return zero_stock


def check_if_not_empty(message):
    """Проверяет, какие товары отсутствуют на озн-складе"""
    oz_goods = stock_dict[message.chat.id].oz_goods
    shop_stock = stock_dict[message.chat.id].shop_stock
    empty_stock = {key: val for key, val in oz_goods.items() if val == 0}
    not_empty = set(empty_stock.keys()) & set(shop_stock.keys())
    return not_empty


needed_art = ('JSL', 'JBP', 'JAA', 'JAS', 'JDW', 'JSB', 'JDA', 'JFM', 'JPP', 'JDK', 'JBS', 'JSR')