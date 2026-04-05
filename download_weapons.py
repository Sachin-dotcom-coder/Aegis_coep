import urllib.request
import os

url = "https://huggingface.co/Subh775/Threat-Detection-YOLOv8n/resolve/main/best.pt"
filename = "yolov8s-weapons.pt"

print(f"Downloading {filename} from HuggingFace...")
try:
    urllib.request.urlretrieve(url, filename)
    print("✅ Download complete! File size:", os.path.getsize(filename) // (1024*1024), "MB")
except Exception as e:
    print("❌ Error downloading file:")
    print(e)
