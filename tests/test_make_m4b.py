from make_m4b import unit_sort_key


def test_unit_sort_key_orders_numerically():
    keys = ["unit1", "unit10", "unit2", "unit21", "unit3"]
    assert sorted(keys, key=unit_sort_key) == ["unit1", "unit2", "unit3", "unit10", "unit21"]


def test_unit_sort_key_extracts_index():
    assert unit_sort_key("unit0") == 0
    assert unit_sort_key("unit15") == 15
