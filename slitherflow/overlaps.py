"""Find labels, icons and lines that collide in a rendered map."""
import math


def overlaps(a, b, pad=0):
    return a[0] - pad < b[2] and b[0] - pad < a[2] and a[1] - pad < b[3] and b[1] - pad < a[3]


def sample(pts, step=3):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
        for i in range(n + 1):
            yield x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n


def check_overlaps(cv):
    half = cv.s["line_width"] / 2 + 1
    found = []
    labels = {}
    for box, desc in cv.texts:   # merge the two lines of one label into one box
        b = labels.get(desc)
        labels[desc] = box if b is None else (min(b[0], box[0]), min(b[1], box[1]), max(b[2], box[2]), max(b[3], box[3]))
    items = list(labels.items())
    for i, (d1, b1) in enumerate(items):
        for d2, b2 in items[i + 1:]:
            if overlaps(b1, b2, 1):
                found.append(f"{d1} overlaps {d2}")
        for b2, d2 in cv.icons:
            if overlaps(b1, b2, 1):
                found.append(f"{d1} overlaps {d2}")
        for pts, lid in cv.lines:
            if any(b1[0] - half < x < b1[2] + half and b1[1] - half < y < b1[3] + half for x, y in sample(pts)):
                found.append(f"{d1} overlaps line '{lid}'")
    for b1, d1 in cv.icons:
        for pts, lid in cv.lines:
            if any(b1[0] - half < x < b1[2] + half and b1[1] - half < y < b1[3] + half for x, y in sample(pts)):
                found.append(f"{d1} sits on line '{lid}'")
    for b1, members, d1 in cv.stations:
        if not members and d1 == cv.terminus:        # a lone trunk station needs no lines
            found.append(f"{d1} has no lines going into it (give a line `to: terminus`)")
        for pts, lid in cv.lines:
            if lid in members:
                continue
            if any(b1[0] - half < x < b1[2] + half and b1[1] - half < y < b1[3] + half for x, y in sample(pts)):
                found.append(f"{d1} sits on line '{lid}' (looks like a shared stop)")
    return sorted(set(found))
