#!/usr/bin/env python3
import requests
import time
import os
import json
import sys

BASE_URL = ""
USER_ID = ""
API_KEY = ""

class BooruDownloader:
    def __init__(self, video_only, output_folder):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BooruDownloader/1.0"})
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=2
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.base_url = BASE_URL
        self.user_id = USER_ID
        self.api_key = API_KEY
        self.video_only = video_only
        self.output_folder = output_folder
        self.limit_per_request = 100
        self.min_interval = 1.0
        self.last_request_time = 0
        self.is_running = True
        self.video_exts = frozenset({"mp4", "webm", "mov", "avi", "mkv", "swf", "gifv", "flv", "m4v"})
        self._folder_created = False

    def log(self, msg):
        print(msg)

    def _wait(self):
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval and self.last_request_time:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def search_posts(self, tags, page=0):
        self._wait()
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": 1,
            "tags": tags,
            "pid": page,
            "limit": self.limit_per_request,
            "user_id": self.user_id,
            "api_key": self.api_key
        }
        self.log(f"  Fetching page {page+1}...")
        
        try:
            
            resp = self.session.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
           
            if not resp.text.strip():
                self.log("Empty response from server")
                return None
                
            try:
                return resp.json()
            except json.JSONDecodeError:
                self.log(f" Invalid JSON response (got HTML or error page)")
                self.log(f"  Response preview: {resp.text[:200]}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.log(f"Request error: {e}")
            return None

    def download_file(self, url, folder):
        if not url or not self.is_running:
            return
        self._wait()
        
        
        filename = url.rsplit('/', 1)[-1].split('?')[0]
        if not filename or "." not in filename:
            filename = f"{int(time.time())}.mp4"
        allowed = "._-"
        filename = ''.join(c for c in filename if c.isalnum() or c in allowed)
        
        if not self._folder_created:
            os.makedirs(folder, exist_ok=True)
            self._folder_created = True
            
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return
            
        try:
            headers = {"Referer": self.base_url.replace("/index.php", "")}
            r = self.session.get(url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()
            
           
            with open(path, "wb") as f:
                for chunk in r.iter_content(65536): 
                    if not self.is_running:
                        return
                    f.write(chunk)
            self.log(f" {filename}")
        except Exception as e:
            self.log(f"{filename} - {e}")

    def extract_posts(self, data):
        if data is None:
            return []
            
        if isinstance(data, list):
            return data
            
        if isinstance(data, dict):
            posts = data.get("post")
            if posts:
                return posts if isinstance(posts, list) else [posts]
            
            for key in ("posts", "results", "data", "items"):
                if key in data:
                    posts = data[key]
                    if isinstance(posts, list):
                        return posts
                    elif isinstance(posts, dict):
                        return [posts]
        
        return []

    def download_character(self, character, extra_tags="", max_pages=50):
        tags = f"{character} {extra_tags}".strip() if extra_tags else character
        self.log(f"\nDownloading '{character}' (tags: {tags})")

        folder = self.output_folder
        os.makedirs(folder, exist_ok=True)

        total = 0
        page = 0
        no_posts_count = 0
        
        while page < max_pages and self.is_running:
            data = self.search_posts(tags, page)
            
            if data is None:
                no_posts_count += 1
                if no_posts_count >= 3:
                    self.log("Server not responding. Stopping.")
                    break
                page += 1
                continue
                
            posts = self.extract_posts(data)
            
            if not posts:
                self.log(f"No posts found on page {page+1}")
                break

            filtered = []
            is_video_only = self.video_only
            video_exts = self.video_exts
            
            for post in posts:
                if not isinstance(post, dict):
                    continue
                    
                file_url = post.get("file_url", "")
                if not file_url:
                    continue
                    
                file_ext = post.get("file_ext")
                if not file_ext:
                    file_ext = os.path.splitext(file_url)[1].lstrip('.').lower()
                else:
                    file_ext = file_ext.lower()
                    
                is_video = file_ext in video_exts
                
                if is_video == is_video_only:
                    filtered.append(post)

            if filtered:
                self.log(f"  Page {page+1}: {len(filtered)} {'videos' if self.video_only else 'images'} found")
                for post in filtered:
                    url = post.get("file_url")
                    if not url:
                        url = post.get("sample_url") or post.get("preview_url")
                    if url:
                        self.download_file(url, folder)
                        total += 1
            else:
                self.log(f"  Page {page+1}: {len(posts)} total, 0 match your filter")

            if len(posts) < self.limit_per_request:
                break
            page += 1

        self.log(f"Downloaded {total} files to: {folder}\n")
        return total


def save_config_to_file():
    script_path = os.path.abspath(__file__)
    
    with open(script_path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.startswith('BASE_URL ='):
            new_lines.append(f'BASE_URL = "{BASE_URL}"\n')
        elif line.startswith('USER_ID ='):
            new_lines.append(f'USER_ID = "{USER_ID}"\n')
        elif line.startswith('API_KEY ='):
            new_lines.append(f'API_KEY = "{API_KEY}"\n')
        else:
            new_lines.append(line)
    
    with open(script_path, 'w') as f:
        f.writelines(new_lines)
    
    print("\nConfiguration saved to file!")


def main():
    global BASE_URL, USER_ID, API_KEY
    
    print("\n" + "="*60)
    print("Booru Art Downloader 67thousand")
    print("="*60)
    
    print("\n[1] Continue (Start your)")
    print("[2] Enter missing configuration")
    
    choice = input("\nSelect option [1/2]: ").strip()
    
    if choice == "2":
        print("\n" + "-"*60)
        print("Enter your configuration:")
        
        if not BASE_URL:
            BASE_URL = input("BASE_URL (e.g., https://website.name): ").strip()
        
        if not USER_ID:
            USER_ID = input("USER_ID (your numeric user ID): ").strip()
        
        if not API_KEY:
            API_KEY = input("API_KEY (your API key): ").strip()
        
        print("-"*60)
        
        save_choice = input("\nSave these settings to the file? [y/n]: ").strip().lower()
        if save_choice == 'y':
            save_config_to_file()
        else:
            print("Settings will only be used for this session.")
        
        print()
    
    if not all([BASE_URL, USER_ID, API_KEY]):
        print("\nERROR: Missing required configuration!")
        print("Please set BASE_URL, USER_ID, and API_KEY in the script or choose option 2.")
        return

    character = input("Character name (Example: Character_Name_(Game_Name)): ").strip()
    if not character:
        print("Character name is required.")
        return

    extra = input("Extra tags: ").strip()
    extra_tags = extra.replace(",", " ").strip()

    media = input("Download (v)ideos or (i)mages? [v/i]: ").strip().lower()
    video_only = media.startswith("v")

    download_folder = os.path.join("downloads", character.replace(' ', '_'))

    print(f"\n Saving to: {download_folder}")
    print("Starting...\n")

    downloader = BooruDownloader(video_only=video_only, output_folder=download_folder)
    downloader.download_character(character, extra_tags, max_pages=50)

    print(f"\nAll done! Files are in: {download_folder}")

    if os.name == 'posix':
        os.system(f'xdg-open "{download_folder}"')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n Cancelled by user.")
    except Exception as e:
        print(f"\n Error: {e}")
        import traceback
        traceback.print_exc()
