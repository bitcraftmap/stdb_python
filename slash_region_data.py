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

def slash_data(in_file, out_file):
    with open(in_file, 'r') as file:
        data = json.load(file)
    filtered_json = [obj for obj in data if obj.get('dimension') == 1]
    new_json = remove_keys_from_dict(filtered_json, remove_keys)
    with open(out_file, 'w') as file:
        json.dump(new_json, file, separators=(',', ':'))

region1 = 'data/terrain_chunk_state/region_1/'
region2 = 'data/terrain_chunk_state/region_2/'
region3 = 'data/terrain_chunk_state/region_3/'
region4 = 'data/terrain_chunk_state/region_4/'
region5 = 'data/terrain_chunk_state/region_5/'
region6 = 'data/terrain_chunk_state/region_6/'
region7 = 'data/terrain_chunk_state/region_7/'
region8 = 'data/terrain_chunk_state/region_8/'
region9 = 'data/terrain_chunk_state/region_9/'

in_file_name = 'terrain_chunk_state.json'
out_file_name = 'terrain_chunk_state_new.json'

slash_data(region1 + in_file_name, region1 + out_file_name)
slash_data(region2 + in_file_name, region2 + out_file_name)
slash_data(region3 + in_file_name, region3 + out_file_name)
slash_data(region4 + in_file_name, region4 + out_file_name)
slash_data(region5 + in_file_name, region5 + out_file_name)
slash_data(region6 + in_file_name, region6 + out_file_name)
slash_data(region7 + in_file_name, region7 + out_file_name)
slash_data(region8 + in_file_name, region8 + out_file_name)
slash_data(region9 + in_file_name, region9 + out_file_name)