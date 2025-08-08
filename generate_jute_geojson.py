import json

def generate_jute_geojson(json_key):
    return [json_key['x'], json_key['z']]

with open('more_jute.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

jute_geojson = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {
            "iconName": "jute"
        },
        "geometry": {
            "type": "MultiPoint",
            "coordinates": [generate_jute_geojson(key) for key in data]
        }
    }]
}

with open('more_jute.geojson', 'w') as file:
    json.dump(jute_geojson, file, separators=(',', ':'))