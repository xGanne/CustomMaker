import requests
import json

def test_danbooru():
    url = "https://danbooru.donmai.us/posts.json"
    headers = {"User-Agent": "CustomMakerv2/1.0 (by xGanne on GitHub)"}
    
    queries = [
        {"tags": "uzumaki_naruto", "limit": 1}
    ]

    for params in queries:
        print(f"\n--- Testing params: {params} ---")
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Items found: {len(data)}")
                if len(data) > 0:
                    post = data[0]
                    print("Keys found:", list(post.keys()))
                    print("Preview URL:", post.get('preview_url'))
                    print("File URL:", post.get('file_url'))
                    print("Media Asset:", post.get('media_asset'))
            else:
                print("Response:", response.text[:200])
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    test_danbooru()
