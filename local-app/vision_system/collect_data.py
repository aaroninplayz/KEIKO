import cv2
import os
import sys
import time
import random
import yaml

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    print("================================================================")
    print("                 LIVE DATA COLLECTOR UTILITY")
    print("================================================================")
    
    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading config.yaml: {e}")
        input("Press Enter to exit...")
        return

    categories = list(config["detectors"].keys())
    print("\nSelect a category to collect data for:")
    for idx, cat in enumerate(categories, 1):
        print(f"  [{idx}] {cat.capitalize()}")
    
    try:
        choice = int(input("\nSelection (number): ").strip())
        category = categories[choice - 1]
    except Exception:
        print("Invalid selection.")
        input("Press Enter to exit...")
        return

    labels = config["detectors"][category]["labels"]
    print(f"\nSelect a label for {category.capitalize()}:")
    for idx, lbl in enumerate(labels, 1):
        print(f"  [{idx}] {lbl.capitalize()}")
        
    try:
        choice = int(input("\nSelection (number): ").strip())
        label = labels[choice - 1]
    except Exception:
        print("Invalid selection.")
        input("Press Enter to exit...")
        return

    # Create directories
    base_dir = os.path.join("data", category)
    train_dir = os.path.join(base_dir, "train", label)
    val_dir = os.path.join(base_dir, "val", label)
    
    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)

    print(f"\nDirectories prepared:")
    print(f"  Train: {train_dir}")
    print(f"  Val:   {val_dir}")
    
    # Initialize Camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("\nERROR: Could not access the webcam/camera.")
        input("Press Enter to exit...")
        return

    print("\n" + "=" * 50)
    print("  CAMERA CONTROL INSTRUCTIONS")
    print("=" * 50)
    print("  [Space] - HOLD or TAP to capture frames continuously")
    print("  [C]     - Capture a single frame manually")
    print("  [Q]     - Quit data collector")
    print("=" * 50)

    count = 0
    capturing = False
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break
            
        display_frame = frame.copy()
        
        # UI overlays
        status_text = f"Category: {category.upper()} | Label: {label.upper()}"
        cv2.putText(display_frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        count_text = f"Captured this session: {count}"
        cv2.putText(display_frame, count_text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        if capturing:
            cv2.putText(display_frame, "CAPTURING...", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
        cv2.imshow("HR Data Collector", display_frame)
        
        key = cv2.waitKey(1) & 0xFF
        
        # Logic to decide train or validation folder (80% train, 20% validation)
        is_train = random.random() < 0.80
        save_path = train_dir if is_train else val_dir
        
        if key == ord('c') or key == ord('C'):
            # Single capture
            filename = f"cap_{int(time.time() * 1000)}.jpg"
            full_path = os.path.join(save_path, filename)
            cv2.imwrite(full_path, frame)
            count += 1
            print(f"[{count}] Saved single frame to {'train' if is_train else 'val'}: {filename}")
            
        elif key == 32: # Spacebar
            capturing = not capturing
            
        elif key == ord('q') or key == ord('Q'):
            print("\nExiting data collector...")
            break
            
        if capturing:
            # Continuous capture at ~5 FPS
            filename = f"cap_{int(time.time() * 1000)}.jpg"
            full_path = os.path.join(save_path, filename)
            cv2.imwrite(full_path, frame)
            count += 1
            print(f"[{count}] Saved frame to {'train' if is_train else 'val'}: {filename}")
            time.sleep(0.15) # Throttle to prevent saving thousands of frames in a second

    cap.release()
    cv2.destroyAllWindows()
    print(f"\nFinished session! Captured {count} images.")
    input("\nPress Enter to return to launcher...")

if __name__ == "__main__":
    main()
