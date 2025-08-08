import json
import requests
from websockets.sync.client import connect
from websockets import Subprotocol
from pathlib import Path
import time
from datetime import datetime
import concurrent.futures
from threading import Lock
import urllib.parse

# Load Bearer Token & Region Module from Files
bearer_file = Path(r".env")

auth_token = bearer_file.read_text().strip()
region_module = "bitcraft-9"  # Regional database - THIS IS REGION 2 ONLY
region_host = "bitcraft-early-access.spacetimedb.com"

# Load resource configuration from file
def load_resource_config():
    """Load resource name and ID from resources.txt file"""
    config_file = Path("resources.txt")
    
    # Create default config file if it doesn't exist
    if not config_file.exists():
        default_config = """# Resource Configuration File
# Format: ResourceName|ResourceID|IconName
# Example: Jute|1917261269|jute
# Example: Traveler's Fruit|182331452|travelers_fruit

Jute|1917261269|jute
"""
        config_file.write_text(default_config)
        print(f"📝 Created default resources.txt file")
        print(f"   Edit this file to add your resources in format: ResourceName|ResourceID|IconName")
        return None, None, None
    
    # Read and parse config file
    content = config_file.read_text().strip()
    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#')]
    
    if not lines:
        print(f"❌ No resources found in resources.txt")
        print(f"   Add resources in format: ResourceName|ResourceID|IconName")
        return None, None, None
    
    # Use the first non-comment line
    resource_line = lines[0]
    parts = resource_line.split('|')
    
    if len(parts) != 3:
        print(f"❌ Invalid format in resources.txt: {resource_line}")
        print(f"   Expected format: ResourceName|ResourceID|IconName")
        return None, None, None
    
    resource_name, resource_id_str, icon_name = [part.strip() for part in parts]
    
    try:
        resource_id = int(resource_id_str)
    except ValueError:
        print(f"❌ Invalid resource ID: {resource_id_str}")
        return None, None, None
    
    return resource_name, resource_id, icon_name

# Load resource configuration
resource_name, resource_id, icon_name = load_resource_config()

if not resource_name:
    print(f"\n❌ Could not load resource configuration. Exiting.")
    exit(1)

print(f"OPTIMIZED Resource Location Query - Configurable Resources with Parallel Processing")
print(f"Database: {region_module} (REGION 9 ONLY)")
print("=" * 80)

print(f"🎯 Target: {resource_name} (Resource ID: {resource_id})")
print(f"🗺️ Icon: {icon_name}")
print(f"📊 Target Sample Size: 10,000 locations")

proto = Subprotocol('v1.json.spacetimedb')
ws_uri = f"wss://{region_host}/v1/database/{region_module}/subscribe"

# Thread-safe results storage
results_lock = Lock()
successful_locations = []
failed_queries = []

def get_resource_entities(resource_id, timeout=20):
    """Get all entity_ids for a resource (Step 2)"""
    print(f"\n🔍 STEP 2: Getting all entity_ids for resource {resource_id}...")
    
    try:
        with connect(
            ws_uri,
            additional_headers={"Authorization": auth_token},
            subprotocols=[proto],
            max_size=None,
            ping_timeout=timeout
        ) as ws:
            
            ws.recv()
            
            query = f"SELECT * FROM resource_state WHERE resource_id = {resource_id};"
            subscription = {
                "Subscribe": {
                    "request_id": 1,
                    "query_strings": [query]
                }
            }
            
            ws.send(json.dumps(subscription))
            
            start_time = time.time()
            for msg in ws:
                if time.time() - start_time > timeout:
                    print(f"   ⏰ Timeout after {timeout}s")
                    return []
                
                data = json.loads(msg)
                
                if 'InitialSubscription' in data:
                    tables = data['InitialSubscription']['database_update']['tables']
                    if tables and tables[0].get('updates') and tables[0]['updates'][0].get('inserts'):
                        rows = tables[0]['updates'][0]['inserts']
                        entries = [json.loads(row) for row in rows]
                        
                        entity_ids = [entry['entity_id'] for entry in entries if 'entity_id' in entry]
                        print(f"   ✅ Found {len(entity_ids)} entity IDs")
                        return entity_ids
                    else:
                        print(f"   ⚪ No entries found")
                        return []
                
                elif 'TransactionUpdate' in data and 'Failed' in data['TransactionUpdate']['status']:
                    error = data['TransactionUpdate']['status']['Failed']
                    print(f"   ❌ Query failed: {error}")
                    return []
                
                break
                
    except Exception as e:
        print(f"   🔴 Error: {str(e)}")
        return []

def get_single_location(entity_id, timeout=8):
    """Get location for a single entity_id - optimized for parallel execution"""
    try:
        with connect(
            ws_uri,
            additional_headers={"Authorization": auth_token},
            subprotocols=[proto],
            max_size=None,
            ping_timeout=timeout
        ) as ws:
            
            ws.recv()  # Welcome message
            
            query = f"SELECT * FROM location_state WHERE entity_id = {entity_id};"
            subscription = {
                "Subscribe": {
                    "request_id": 1,
                    "query_strings": [query]
                }
            }
            
            ws.send(json.dumps(subscription))
            
            start_time = time.time()
            for msg in ws:
                if time.time() - start_time > timeout:
                    with results_lock:
                        failed_queries.append(f"Timeout: {entity_id}")
                    return None
                
                data = json.loads(msg)
                
                if 'InitialSubscription' in data:
                    tables = data['InitialSubscription']['database_update']['tables']
                    if tables and tables[0].get('updates') and tables[0]['updates'][0].get('inserts'):
                        rows = tables[0]['updates'][0]['inserts']
                        if rows:
                            location = json.loads(rows[0])
                            
                            # Add the entity_id to the location data
                            location['entity_id'] = entity_id
                            
                            with results_lock:
                                successful_locations.append(location)
                            
                            return location
                    
                    # No location found
                    with results_lock:
                        failed_queries.append(f"No location: {entity_id}")
                    return None
                    
                elif 'TransactionUpdate' in data and 'Failed' in data['TransactionUpdate']['status']:
                    error = data['TransactionUpdate']['status']['Failed']
                    with results_lock:
                        failed_queries.append(f"Query failed: {entity_id} - {error}")
                    return None
                
                break
                
    except Exception as e:
        with results_lock:
            failed_queries.append(f"Connection error: {entity_id} - {str(e)}")
        return None

def get_parallel_locations(entity_ids, sample_size=10000, max_workers=15):
    """Get locations for entity IDs using parallel processing - optimized for 10K locations"""
    print(f"\n📍 STEP 3: Getting locations with parallel processing...")
    print(f"   Target sample size: {sample_size:,} entities")
    print(f"   Parallel workers: {max_workers}")
    print(f"   Estimated time: {sample_size // max_workers // 3}-{sample_size // max_workers // 2} minutes")
    
    # Take a sample of entity IDs (10,000 or all if less than 10,000)
    actual_sample_size = min(sample_size, len(entity_ids))
    sample_entity_ids = entity_ids[:actual_sample_size]
    
    print(f"   Actual processing: {actual_sample_size:,} entities")
    
    # Clear previous results
    global successful_locations, failed_queries
    with results_lock:
        successful_locations.clear()
        failed_queries.clear()
    
    # Process in parallel
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = [executor.submit(get_single_location, entity_id) for entity_id in sample_entity_ids]
        
        # Process results as they complete
        completed = 0
        last_update = 0
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            
            # Progress updates every 250 completions or every 30 seconds
            elapsed = time.time() - start_time
            if completed % 250 == 0 or (elapsed - last_update) >= 30:
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = len(sample_entity_ids) - completed
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60
                
                success_rate = (len(successful_locations) / completed * 100) if completed > 0 else 0
                
                print(f"   Progress: {completed:,}/{len(sample_entity_ids):,} ({completed/len(sample_entity_ids)*100:.1f}%) | "
                      f"Success: {len(successful_locations):,} ({success_rate:.1f}%) | "
                      f"ETA: {eta_minutes:.1f}min")
                last_update = elapsed
    
    end_time = time.time()
    total_time = end_time - start_time
    total_minutes = total_time / 60
    
    print(f"\n   ⏱️ Parallel processing completed in {total_minutes:.1f} minutes ({total_time:.1f} seconds)")
    print(f"   ✅ Success: {len(successful_locations):,} locations found")
    print(f"   ❌ Failed: {len(failed_queries):,} queries failed")
    
    return successful_locations.copy()

def generate_bitcraftmap_link(map_format_data, icon_name, resource_name):
    """Generate clickable bitcraftmap.com link"""
    
    # Create GeoJSON data
    def generate_coordinates(json_key):
        return [json_key['x'], json_key['z']]
    
    geojson_data = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "iconName": icon_name
            },
            "geometry": {
                "type": "MultiPoint",
                "coordinates": [generate_coordinates(key) for key in map_format_data]
            }
        }]
    }
    
    # Convert to JSON string and URL encode
    geojson_string = json.dumps(geojson_data, separators=(',', ':'))
    encoded_geojson = urllib.parse.quote(geojson_string)
    
    # Create the full URL
    map_url = f"https://bitcraftmap.com/#{encoded_geojson}"
    
    return map_url, geojson_data

# Execute the optimized process for configurable resources
print(f"\n⚡ PROCESSING START FOR {resource_name.upper()}...")

# Step 2: Get all entity IDs
entity_ids = get_resource_entities(resource_id)

if entity_ids:
    print(f"\n🎯 Processing strategy:")
    print(f"   Total entities available: {len(entity_ids):,}")
    print(f"   Target processing: 10,000 locations")
    print(f"   Using 15 parallel workers for faster processing")
    print(f"   Expected processing time: 5-8 minutes")
    
    # Get 10,000 locations using parallel processing
    sample_locations = get_parallel_locations(entity_ids, sample_size=10000, max_workers=15)
    
    if sample_locations:
        print(f"\n🎉 SUCCESS! Found {len(sample_locations):,} {resource_name} locations!")
        
        # Show sample coordinates
        print(f"\n📍 SAMPLE {resource_name.upper()} COORDINATES (first 10):")
        for i, loc in enumerate(sample_locations[:10]):
            x, z = loc.get('x'), loc.get('z')
            entity_id = loc.get('entity_id')
            chunk_index = loc.get('chunk_index')
            print(f"   {i+1}: {resource_name} at ({x}, {z}) chunk {chunk_index} (Entity: {entity_id})")
        
        if len(sample_locations) > 10:
            print(f"   ... and {len(sample_locations) - 10:,} more locations")
        
        # Save results in your exact map framework format
        print(f"\n💾 SAVING {len(sample_locations):,} {resource_name.upper()} DATA...")
        
        # Create clean filename from resource name
        clean_name = resource_name.lower().replace("'", "").replace(" ", "_")
        
        # Your exact format: list of location dicts
        map_format_data = []
        for loc in sample_locations:
            map_format_data.append({
                'entity_id': loc.get('entity_id'),
                'chunk_index': loc.get('chunk_index'),
                'x': loc.get('x'),
                'z': loc.get('z'),
                'dimension': loc.get('dimension', 1)
            })
        
        # Save in your exact format (main file for map framework)
        with open(f"{clean_name}_map_format.json", 'w') as f:
            json.dump(map_format_data, f, separators=(',', ': '))
        
        # Also save enriched version for reference
        resource_results = []
        for loc in sample_locations:
            resource_results.append({
                'resource_name': resource_name,
                'resource_id': resource_id,
                'entity_id': loc.get('entity_id'),
                'x': loc.get('x'),
                'z': loc.get('z'),
                'dimension': loc.get('dimension', 1),
                'chunk_index': loc.get('chunk_index')
            })
        
        with open(f"{clean_name}_bulk_locations.json", 'w') as f:
            json.dump(resource_results, f, indent=2)
        
        # Generate clickable bitcraftmap.com link
        print(f"\n🗺️ GENERATING BITCRAFTMAP.COM LINK...")
        map_url, geojson_data = generate_bitcraftmap_link(map_format_data, icon_name, resource_name)
        
        # Save GeoJSON file
        with open(f"{clean_name}.geojson", 'w') as f:
            json.dump(geojson_data, f, separators=(',', ':'))
        
        # Save the clickable link
        with open(f"{clean_name}_bitcraft_link.txt", 'w') as f:
            f.write(f"BitCraft Map Link for {resource_name}:\n")
            f.write(f"{map_url}\n\n")
            f.write(f"Click this link to view {len(sample_locations):,} {resource_name} locations on bitcraftmap.com\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Create CSV for reference
        import csv
        with open(f"{clean_name}_coordinates.csv", 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['name', 'x', 'z', 'dimension', 'entity_id', 'chunk_index'])
            
            for resource in resource_results:
                writer.writerow([
                    resource_name,
                    resource['x'],
                    resource['z'],
                    resource['dimension'],
                    resource['entity_id'],
                    resource['chunk_index']
                ])
        
        print(f"\n💾 FILES CREATED:")
        print(f"   🎯 {clean_name}_map_format.json - MAIN FILE FOR MAP FRAMEWORK ({len(map_format_data):,} locations)")
        print(f"   🌐 {clean_name}_bitcraft_link.txt - CLICKABLE BITCRAFTMAP.COM LINK!")
        print(f"   🗺️ {clean_name}.geojson - GeoJSON format")
        print(f"   📄 {clean_name}_bulk_locations.json - Full enriched data")
        print(f"   📊 {clean_name}_coordinates.csv - For spreadsheets")
        
        # Show the clickable link
        print(f"\n🔗 BITCRAFT MAP LINK:")
        print(f"   Copy and paste this link to view your {resource_name} locations:")
        print(f"   {map_url}")
        
        # Show performance stats
        coverage = len(sample_locations) / len(entity_ids) * 100
        success_rate = len(sample_locations) / (len(sample_locations) + len(failed_queries)) * 100
        
        print(f"\n📊 PROCESSING ANALYSIS:")
        print(f"   🎯 Resource: {resource_name}")
        print(f"   🔢 Locations found: {len(sample_locations):,}")
        print(f"   📈 Success rate: {success_rate:.1f}%")
        print(f"   🌍 Coverage: {coverage:.1f}% of all {resource_name} in Region 2")
        print(f"   ⚡ Processing rate: ~{len(sample_locations)/(time.time()-start_time)*60:.0f} locations/minute")
        
        if failed_queries:
            print(f"\n⚠️ FAILED QUERIES (first 5):")
            for fail in failed_queries[:5]:
                print(f"   {fail}")
            if len(failed_queries) > 5:
                print(f"   ... and {len(failed_queries) - 5:,} more failures")
        
    else:
        print(f"\n😞 No locations found for {resource_name}")
        if failed_queries:
            print(f"\n❌ Common failure reasons:")
            for fail in failed_queries[:10]:
                print(f"   {fail}")

else:
    print(f"\n😞 Could not get entity IDs for {resource_name} (Resource ID: {resource_id})")

print(f"\n🌍 CONFIGURATION INSTRUCTIONS:")
print(f"   📝 Edit 'resources.txt' to change resources")
print(f"   📋 Format: ResourceName|ResourceID|IconName")
print(f"   🔄 Run script again to process different resources")

print(f"\n⚡ OPTIMIZATION SUMMARY:")
print(f"   • Configurable resources via resources.txt")
print(f"   • Automatic clickable bitcraftmap.com links")
print(f"   • 15 parallel workers for maximum speed")
print(f"   • Clean filenames based on resource names")