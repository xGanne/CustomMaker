import requests
import time

class DanbooruClient:
    def __init__(self, user_agent="CustomMakerv2/1.0 (by xGanne on GitHub)"):
        self.base_url = "https://danbooru.donmai.us"
        self.headers = {"User-Agent": user_agent}

    def search_posts(self, tags, limit=20, page=1):
        """
        Searches posts on Danbooru.
        tags: space separated string of tags
        """
        url = f"{self.base_url}/posts.json"
        params = {
            "tags": tags,
            "limit": limit,
            "page": page
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                print("Rate limit reached. Waiting...")
                time.sleep(1)
                return []
            print(f"HTTP Error: {e}")
            return []
        except Exception as e:
            print(f"Error searching posts: {e}")
            return []

    def fetch_tags(self, query):
        """
        Fetches tags starting with 'query' from Danbooru.
        """
        if not query or len(query) < 2: return []
        
        url = f"{self.base_url}/tags.json"
        params = {
            "search[name_matches]": f"{query}*",
            "search[order]": "count",
            "limit": 10
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=5)
            # response.raise_for_status() # 404/422 can happen, ignore
            if response.status_code == 200:
                data = response.json()
                # Return list of tag names
                return [t['name'] for t in data if 'name' in t]
            return []
        except:
             return []

    def download_image(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"Download failed for {url}: {e}")
            return None
