import json

#This script will take the chunk files and remove some key to reduce the size of the json file

'''
{
    'chunk_index': 196132,
    'chunk_x': 131,
    'chunk_z': 196,
    'dimension': 1,
    'biomes': array[],
    'elevations': array[],
    'water_levels': array[],
    'water_body_types': array[],
    'zoning_types': array[],
    'original_elevations': array[],
}

'''

chunk_data_file = 'data/terrain_chunk_state/region_3/terrain_chunk_state.json'
chunk_data_file_new = 'data/terrain_chunk_state/region_3/terrain_chunk_state_new.json'

remove_keys = [
    'dimension',
    'elevations',
    'water_levels',
    'water_body_types',
    'zoning_types',
    'original_elevations'
]

def remove_keys_from_dict(data, keys_to_remove):
    if isinstance(data, dict):
        return {k: remove_keys_from_dict(v, keys_to_remove) 
                for k, v in data.items() if k not in keys_to_remove}
    elif isinstance(data, list):
        return [remove_keys_from_dict(item, keys_to_remove) for item in data]
    else:
        return data

with open(chunk_data_file, 'r') as file:
    data = json.load(file)

filtered_json = [obj for obj in data if obj.get('dimension') == 1]
new_json = remove_keys_from_dict(filtered_json, remove_keys)
print(str(len(new_json)) + ' chunks in the array')

with open(chunk_data_file_new, 'w') as file:
    json.dump(new_json, file, separators=(',', ':'))