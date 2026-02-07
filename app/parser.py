def _find_price_block(product_obj):
    """Ищет цену в недрах JSON"""
    sizes = product_obj.get('sizes', [])
    if sizes and 'price' in sizes[0]:
        return sizes[0]['price']
    
    for size in sizes:
        if 'price' in size:
            return size['price']
    return None

def parse_card_data(data, divider=100):
    """
    Разбирает ответ API.
    Возвращает словарь с ценами или None, если данных нет.
    """
    products = data.get('data', {}).get('products') or data.get('products') or []
    
    if not products:
        return None

    product_obj = products[0]
    price_data = _find_price_block(product_obj)
    
    if not price_data:
        return None

    # Расчеты
    p_val = price_data.get('product', 0) / divider
    l_val = price_data.get('logistics', 0) / divider
    r_val = price_data.get('return', 0) / divider
    total = p_val + l_val + r_val

    return {
        'product': p_val,
        'logistics': l_val,
        'return': r_val,
        'total': total
    }