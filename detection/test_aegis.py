"""
Not important delete later just a test to check the model

"""
import torch
from ultralytics import YOLO

# CPU optimization
torch.set_num_threads(4)

print("✅ PyTorch version:", torch.__version__)
print("🔄 Loading YOLOv8n-pose model...")
model = YOLO("yolov8n-pose.pt")
print("✅ Model loaded!")

# Run on a sample public image (no video needed for this test)
print("🔄 Running inference on test image...")
results = model(
    "https://ultralytics.com/images/bus.jpg",
    imgsz=320,
    verbose=False
)

res = results[0]
print(f"✅ Detected {len(res.boxes)} people/objects in the test image")
print("🎉 Phase 1 complete — your environment is ready!")

# Show image (comment out if running headlessly)
try:
    res.show()
except Exception:
    print("ℹ️  Could not display image (headless mode). That's fine.")
