# build_dictionary.py
import glob
import os
import shutil
import sys
import time

import requests

from src.dictionary.customdict import Dictionary


def main():
    print("downloading jmdict...")
    download_url = 'http://ftp.edrdg.org/pub/Nihongo/JMdict.gz'
    open('JMdict', 'wb').write(requests.get(download_url).content)

    print("processing jmdict -> json...")
    exec(open('scripts/process.py').read()) # python scripts/process.py - see https://github.com/wareya/nazeka/blob/master/etc/process.py
    [shutil.copy(f, os.path.join('data', os.path.basename(f))) for f in glob.glob('JMdict*.json')] # mv JMdict*.json data
    os.remove('JMdict') # rm JMdict
    [os.remove(f) for f in glob.glob('JMdict*.json')] # rm JMdict*.json

    print("Starting dictionary build process...")
    data_dir = 'data'
    output_path = 'jmdict_enhanced.pkl'
    
    jmdict_files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.startswith('JMdict') and f.endswith('.json')]
    deconjugator_path = os.path.join(data_dir, 'deconjugator.json')
    priority_path = os.path.join(data_dir, 'priority.json')

    if not all(os.path.exists(p) for p in jmdict_files + [deconjugator_path, priority_path]):
        print(f"Error: Missing required dictionary files in '{data_dir}' folder.", file=sys.stderr)
        print("Please place JMdict*.json, deconjugator.json, and priority.json in the data folder.", file=sys.stderr)
        sys.exit(1)

    print("Loading dictionary data from JSON files...")
    start_time = time.time()
    
    dictionary = Dictionary()
    
    # Load and process all data
    dictionary.import_jmdict_json(jmdict_files)
    dictionary.import_deconjugator(deconjugator_path)
    dictionary.import_priority(priority_path)

    duration = time.time() - start_time
    print(f"All data imported and processed in {duration:.2f} seconds.")
    print(f"Total entries processed: {len(dictionary.entries)}")

    print(f"Saving processed dictionary to: {output_path}")
    start_time = time.time()
    dictionary.save_dictionary(output_path)
    duration = time.time() - start_time
    print(f"Dictionary saved in {duration:.2f} seconds.")
    print("Build complete.")

if __name__ == "__main__":
    main()