import json
import os

def get_asana_project_id(channel_id):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    channel_map_path = os.path.join(current_dir, 'channel_map.json')
    
    try:
        with open(channel_map_path, 'r') as f:
            channel_map = json.load(f)
    except FileNotFoundError:
        raise Exception(f"channel_map.json not found at {channel_map_path}")
    except json.JSONDecodeError:
        raise Exception("channel_map.json contains invalid JSON")
    
    if channel_id not in channel_map:
        raise Exception(f"Channel {channel_id} not mapped to any Asana project. Please add it to channel_map.json")
    
    return channel_map[channel_id]