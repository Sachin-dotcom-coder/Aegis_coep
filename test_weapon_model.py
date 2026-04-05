import cv2
from ultralytics import YOLO

model = YOLO('yolov8s-weapons.pt')
cap = cv2.VideoCapture('evaluation.mp4')

print("Starting custom weapon detection test...")
frame_id = 0
found = False

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    frame_id += 1
    
    # Run at super low confidence to see if it even triggers
    results = model.predict(frame, imgsz=640, conf=0.10, verbose=False)
    
    if len(results[0].boxes) > 0:
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            name = model.names[cls_id]
            print(f"Frame {frame_id}: {name} ({conf:.2f})")
            found = True

if not found:
    print("Zero weapons detected across the entire video even at 10% confidence!")
cap.release()
