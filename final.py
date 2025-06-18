
import json,os
import requests,time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient
from mega import Mega
import zipfile,shutil


CHROMEDRIVER_PATH = r"chromedriver"

def get_total_episodes(anime_id):
    try:
        url = "https://graphql.anilist.co"
        query = {
            "query": """
            query ($id: Int) {
              Media(id: $id, type: ANIME) {
                title {
                  romaji
                }
                episodes
              }
            }
            """,
            "variables": {"id": anime_id}
        }

        response = requests.post(url, json=query)

        if response.status_code == 200:
            data = response.json()
            print("Fetched total episodes successfully")
            return data['data']['Media']['episodes']
        else:
            print(f"Error fetching episodes: Status code {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception in get_total_episodes: {e}")
        return None


class WebDriverManager:
    def __init__(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920x1080")
        self.driver = webdriver.Chrome(options=options)

    def get_video_url(self, url):
        # print(f"Fetching video URL for: {url}")
        self.driver.get(url)

        for attempt in range(3):
            try:
                time.sleep(5)  # Give time for page to load JS
                video_element = self.driver.find_element(By.TAG_NAME, 'source')
                video_url = video_element.get_attribute("src")

                if video_url and '[object' not in video_url:
                    # print(f"✅ Valid video URL found on attempt {attempt + 1}")
                    return video_url
                else:
                    print(f"⚠️ Invalid video URL on attempt {attempt + 1}: {video_url}")
            except Exception as e:
                print(f"❌ Exception on attempt {attempt + 1}: {e}")

        print("🚫 Failed to fetch valid video URL after 3 attempts.")
        return None



    def close(self):
        self.driver.quit()


def fetch_all_episode_urls(anime_id, index):
    try:
        print("Fetching total episodes...")
        total_episodes = get_total_episodes(anime_id)
        if total_episodes is None:
            print("Episodes count not found ... skipping")
            return

        print(f"Total episodes: {total_episodes}")

        driver_manager = WebDriverManager()
        video_urls = []
        total_episodes = total_episodes if total_episodes >0 else None
        
        
        for episode_num in range(1, total_episodes + 1):
            # print("\033[F\033[K" * 2, end='')
            # print(f"Processing episode {episode_num}/{total_episodes}...")

            try:
                episode_url = f"https://www.miruro.tv/watch?id={anime_id}&ep={episode_num}"
                video_src = driver_manager.get_video_url(episode_url)

                if video_src:
                    # print(f"Video URL for episode {episode_num}")
                    video_urls.append({"episode": episode_num, "video_url": video_src})
                else:
                    print(f"No video URL found for episode {episode_num}")
            except Exception as ep_err:
                print(f"Error processing episode {episode_num}: {ep_err}")

        if (index + 1) % 10 == 0:
            print("10 ids limit reached, restarting driver")
            driver_manager.close()
            time.sleep(3)
            # os.system("cls")

        # Save data to JSON
        try:
            with open(f"./json_files/{anime_id}_data.json", "w", encoding="utf-8") as file:
                json.dump(video_urls, file, indent=4)
            # print("All episode URLs saved to data.json")
        except Exception as write_err:
            print(f"Error writing JSON: {write_err}")
        

    except Exception as e:
        print(f"Unexpected error in fetch_all_episode_urls for anime_id {anime_id}: {e}")


def zip_json_folder(start_id, index):
    folder_name = 'json_files'
    zip_filename = f"{start_id}_{index}_json_files"

    if not os.path.exists(folder_name):
        print(f"Folder '{folder_name}' does not exist. Skipping zipping.")
        return

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_name):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=folder_name)
                zipf.write(file_path, arcname)

    print(f"Folder '{folder_name}' zipped successfully into '{zip_filename}'")
    keys = os.getenv("M_TOKEN")
    keys = keys.split("_")
    mega = Mega()
    m = mega.login(keys[0],keys[1])
    
    try:
        m.upload(zip_filename)
    except Exception as e:
        print("Error : ",e)
    finally:
        shutil.rmtree(folder_name)
        os.remove(zip_filename)
    

def start():
    json_folder = "json_files"
    if not os.path.exists(json_folder):
        os.makedirs(json_folder)

    client = None
    try:
        mongo_url = os.getenv("MONGO_URL")
        client = MongoClient(mongo_url)
        db = client['miruai_tv_1']
        collection = db['coll_1']

        # Fetch or initialize tracking doc
        tracking_doc = collection.find_one({"id": "action_1"})
        if tracking_doc is None:
            print("No tracking document found. Initializing with default values.")
            tracking_doc = {
                "id": "action_1",
                "start_id": 1,
                "last_saved_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            collection.insert_one(tracking_doc)

        start_id = tracking_doc["start_id"]
        processed_count = 0

        while True:
            try:
                print(f"🔄 Processing anime_id: {start_id}")
                fetch_all_episode_urls(start_id, start_id)

                # Update progress in DB immediately
                collection.update_one(
                    {"id": "action_1"},
                    {
                        "$set": {
                            "start_id": start_id + 1,
                            "last_saved_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        }
                    }
                )

                processed_count += 1
                if processed_count % 10 == 0:
                    zip_json_folder(start_id - 9, start_id)

                start_id += 1

            except Exception as loop_err:
                print(f"❌ Error during processing of anime_id {start_id}: {loop_err}")
                # Optional: wait before retrying next
                time.sleep(2)
                start_id += 1  # Skip problematic ID

    finally:
        if client:
            client.close()
start()
