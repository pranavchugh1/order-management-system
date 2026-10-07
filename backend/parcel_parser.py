import copy
import re
import unicodedata

from parcel_allocation import allocate_sets


def key(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value).casefold())


def volume_alias(value):
    return re.sub(r'^(?:volume|vol)[.\s-]*', '', key(value))


def catalogue_index(catalogues):
    index = {}
    for cat in catalogues:
        for vol in cat['volumes']:
            names = {vol['name']}
            if key(vol['name']).startswith(key(cat['name'])):
                names.add(key(vol['name'])[len(key(cat['name'])):])
            aliases = {(key(cat['name']), key(vol['name']))}
            for name in names:
                aliases.update({key(cat['name']) + key(name), key(cat['name']) + volume_alias(name), key(cat['name']) + 'vol' + volume_alias(name)})
            for alias in aliases:
                index.setdefault(alias, {})[(cat['id'], vol['id'])] = (cat, vol)
    return index


def resolve(name, index):
    name = name.strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('""', '"')
    if '|' in name:
        parts = name.split('|')
        lookup = tuple(key(p) for p in parts)
    else:
        lookup = re.sub(r'(?:volume|vol)[.\s-]*(\d+)', r'vol\1', key(name))
    found = index.get(lookup, {}) or index.get(key(name), {})
    if len(found) != 1:
        raise ValueError(f'Catalogue/volume not found or ambiguous: {name[:120]}. Select it from the dropdown or use "Catalogue | Volume".')
    return next(iter(found.values()))


def split_items(expression, index):
    # A real catalogue name containing "and" is not mistaken for a separator.
    try:
        return [resolve(expression, index)]
    except ValueError:
        pass
    parts, start = [], 0
    for token in re.finditer(r'"(?:[^"]|"")*"|[&+]|\band\b', expression, re.I):
        if token.group().startswith('"'):
            continue
        parts.append(expression[start:token.start()].strip())
        start = token.end()
    parts.append(expression[start:].strip())
    if not all(parts) or len(parts) > 100:
        raise ValueError('Use between 1 and 100 catalogue/volume items per parcel.')
    items = [resolve(part, index) for part in parts]
    if len({(c['id'], v['id']) for c, v in items}) != len(items):
        raise ValueError('A catalogue/volume is repeated in this parcel. Include each item once.')
    return items


def parse_line(line, index):
    explicit = re.search(r'\s*(?:@|\bof\b|\|)\s*(\d{1,7})\s*(?:pcs|pieces?)\s*$', line, re.I)
    target = int(explicit[1]) if explicit else None
    if explicit:
        line = line[:explicit.start()].strip()
    quantity = re.search(r'\s+(\d{1,7})\s+parcels?\s*$', line, re.I)
    count = int(quantity[1]) if quantity else 1
    if quantity:
        line = line[:quantity.start()].strip()
    if not 1 <= count <= 100:
        raise ValueError('Parcel quantity must be between 1 and 100.')
    items = split_items(line, index)
    sizes = tuple(v['pieces_per_set'] for _, v in items)
    if target is None:
        if not set(sizes).issubset({6, 10}):
            raise ValueError('This pieces/set size needs an explicit parcel target, e.g. @ 72 pcs.')
        target = 80 if all(p == 10 for p in sizes) else 72
    sets = allocate_sets(sizes, target)
    return {'target': target, 'status': 'Pending', 'compositions': [
        {'catalogue_id': cat['id'], 'catalogue_name': cat['name'], 'volume_id': vol['id'], 'volume_name': vol['name'], 'pieces_per_set': vol['pieces_per_set'], 'sets': qty}
        for (cat, vol), qty in zip(items, sets)
    ]}, count


def parse_parcels(text, index):
    parcels, errors, cache = [], [], {}
    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            if line not in cache:
                cache[line] = parse_line(line, index)
            parcel, count = cache[line]
            if len(parcels) + count > 100:
                raise ValueError('Limit 100 parcels per order.')
            parcels.extend(copy.deepcopy(parcel) for _ in range(count))
        except ValueError as exc:
            errors.append({'line': line_no, 'text': line[:200], 'message': str(exc)})
    return parcels, errors