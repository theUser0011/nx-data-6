import json, os, time, requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from pymongo import MongoClient
from mega import Mega


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
            print("✅ Fetched total episodes")
            return data['data']['Media']['episodes']
        else:
            print(f"❌ Error fetching episodes: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exception in get_total_episodes: {e}")
        return None


class WebDriverManager:
    def __init__(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920x1080")
        self.driver = webdriver.Chrome(options=options)

    def get_video_url(self, url):
        self.driver.get(url)

        for attempt in range(3):
            try:
                time.sleep(5)
                video_element = self.driver.find_element(By.TAG_NAME, 'source')
                video_url = video_element.get_attribute("src")

                if video_url and '[object' not in video_url:
                    return video_url
                else:
                    print(f"⚠️ Invalid video URL on attempt {attempt + 1}")
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
            print("⚠️ Episodes not found, skipping ID")
            return

        print(f"📺 Total episodes: {total_episodes}")

        driver_manager = WebDriverManager()
        video_urls = []

        for episode_num in range(1, total_episodes + 1):
            try:
                episode_url = f"https://www.miruro.tv/watch?id={anime_id}&ep={episode_num}"
                video_src = driver_manager.get_video_url(episode_url)

                if video_src:
                    video_urls.append({"episode": episode_num, "video_url": video_src})
                else:
                    print(f"⚠️ No video URL for episode {episode_num}")
            except Exception as ep_err:
                print(f"❌ Error processing episode {episode_num}: {ep_err}")

        driver_manager.close()

        # Save data to JSON
        json_folder = "json_files"
        os.makedirs(json_folder, exist_ok=True)
        json_path = os.path.join(json_folder, f"{anime_id}_data.json")

        # try:
        #     with open(json_path, "w", encoding="utf-8") as file:
        #         json.dump(video_urls, file, indent=4)
        #     print(f"✅ Saved: {json_path}")
        # except Exception as write_err:
        #     print(f"❌ Error writing JSON: {write_err}")
        #     return

        # Upload to Mega and save public link to DB
        try:
            # keys = os.getenv("M_TOKEN").split("_")
            # mega = Mega()
            # m = mega.login(keys[0], keys[1])
            # file = m.upload(json_path)
            # public_link = m.get_upload_link(file)
            # print(f"✅ Uploaded to Mega: {public_link}")

            mongo_url = os.getenv("MONGO_URL")
            client = MongoClient(mongo_url)
            db = client['miruai_tv_1']
            cloud_coll = db['cloud_files']

            cloud_coll.insert_one({
                "filename": f"{anime_id}_data.json",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "file_data": video_urls,
                "message": "Data successfully uploaded"
            })

        except Exception as e:
            print(f"❌ Upload or DB insert error: {e}")
            try:
                cloud_coll.insert_one({
                    "filename": f"{anime_id}_data.json",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "message": "File upload failed"
                })
            except:
                pass

        # # Delete local file
        # try:
        #     os.remove(json_path)
        #     print(f"🧹 Removed local file: {json_path}")
        # except:
        #     print(f"⚠️ Could not delete local file: {json_path}")

    except Exception as e:
        print(f"❌ Unexpected error for anime_id {anime_id}: {e}")


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

        tracking_doc = collection.find_one({"id": "action_1"})
        if tracking_doc is None:
            print("Initializing tracking document...")
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
                print(f"\n🔄 Processing anime_id: {start_id}")
                fetch_all_episode_urls(start_id, start_id)

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
                start_id += 1

            except Exception as loop_err:
                print(f"❌ Error during anime_id {start_id}: {loop_err}")
                time.sleep(2)
                start_id += 1

    finally:
        if client:
            client.close()


# Run the script
start()
