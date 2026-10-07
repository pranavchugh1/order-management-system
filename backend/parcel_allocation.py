"""Exact whole-set allocation without database calls or external AI services."""
from functools import lru_cache
from math import gcd


@lru_cache(maxsize=512)
def allocate_sets(sizes, target):
    count = len(sizes)
    if not 1 <= target <= 1000000 or not sizes or any(p <= 0 for p in sizes):
        raise ValueError('Parcel size must be between 1 and 1,000,000 pieces.')
    if len(set(sizes)) == 1:
        unit = sizes[0] * count
        if target % unit:
            raise ValueError(f'Equal sets require a parcel size divisible by {unit} pieces. Change the target.')
        result = (target // unit,) * count
    elif count == 2:
        a, b = sizes
        divisor = gcd(a, b)
        if target % divisor:
            raise ValueError('This target cannot be filled with whole sets. Change the parcel size.')
        step = b // divisor
        first = ((target // divisor) * pow(a // divisor, -1, step)) % step if step > 1 else 0
        minimum = max(1, (target - 100000 * b + a - 1) // a)
        maximum = min(100000, (target - b) // a)
        low = max(0, (minimum - first + step - 1) // step)
        high = (maximum - first) // step
        if low > high:
            raise ValueError('Each item needs at least one whole set. Change the parcel size.')
        ideal = (target - 2 * a * first) // (2 * a * step)
        candidates = {max(low, min(high, ideal)), max(low, min(high, ideal + 1))}
        x = min((first + k * step for k in candidates), key=lambda x: (abs(2 * a * x - target), x))
        result = (x, (target - a * x) // b)
    else:
        # Bounded exact DP: minimize deviation from equal pieces, not fractional sets.
        states = {0: (0, ())}
        remaining = sum(sizes)
        operations = 0
        for size in sizes:
            remaining -= size
            next_states = {}
            for subtotal, (cost, path) in states.items():
                for sets in range(1, min(100000, (target - remaining - subtotal) // size) + 1):
                    operations += 1
                    if operations > 250000:
                        raise ValueError('Automatic allocation is too large. Use smaller parcels or compose this parcel in the order editor.')
                    pieces = sets * size
                    total = subtotal + pieces
                    score = cost + (count * pieces - target) ** 2
                    if total not in next_states or score < next_states[total][0]:
                        next_states[total] = (score, (*path, sets))
            states = next_states
        if target not in states:
            raise ValueError('This target cannot include every item in whole sets. Change the parcel size.')
        result = states[target][1]
    if any(not 1 <= sets <= 100000 for sets in result):
        raise ValueError('Each item must contain between 1 and 100,000 sets.')
    return result