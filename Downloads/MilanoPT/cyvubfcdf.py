import json

def find_keys(obj, keys):
    found = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                found[k] = v
            else:
                result = find_keys(v, keys)
                if result:
                    found.update(result)
    elif isinstance(obj, list):
        for item in obj:
            result = find_keys(item, keys)
            if result:
                found.update(result)
    return found

with open('gtfs_cache.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

filtered = find_keys(data, {"T3", "T9"})

with open('gtfs_cache_demo.json', 'w', encoding='utf-8') as f:
    json.dump(filtered, f, indent=2, ensure_ascii=False)

print(json.dumps(filtered, indent=2, ensure_ascii=False))