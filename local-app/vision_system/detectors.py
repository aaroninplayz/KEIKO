import os
import time
import queue
import threading
import yaml
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import numpy as np

class VisionClassifier(nn.Module):
    def __init__(self, backbone, num_classes):
        super().__init__()
        self.backbone_name = backbone
        if backbone == "resnet18":
            self.model = models.resnet18(weights=None)
            in_features = self.model.fc.in_features
            self.model.fc = nn.Sequential(
                nn.Dropout(p=0.4),
                nn.Linear(in_features, num_classes)
            )
        else: # mobilenet_v3
            self.model = models.mobilenet_v3_small(weights=None)
            in_features = self.model.classifier[3].in_features
            self.model.classifier[3] = nn.Sequential(
                nn.Dropout(p=0.4),
                nn.Linear(in_features, num_classes)
            )

    def forward(self, x):
        return self.model(x)


class AsyncDetectorManager:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.models = {}
        self.label_mappings = {}
        
        # Load configuration
        self.load_config()

        # Threading infrastructure
        self.frame_queue = queue.Queue(maxsize=1) # Keep only the freshest frame (no delay accumulation)
        self.results = {}
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # Input transforms matching training pipeline
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        # Load trained weights
        self.init_models()

    def load_config(self):
        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

    def init_models(self):
        print(f"\nInitializing Vision Detectors on device: {str(self.device).upper()}")
        for key, cfg in self.config["detectors"].items():
            labels = cfg["labels"]
            backbone = cfg["backbone"]
            model_path = cfg["model_path"]
            
            # Read label mapping sidecar file if exists to make sure indices align perfectly
            mapping_path = model_path.replace(".pth", "_labels.txt")
            if os.path.isfile(mapping_path):
                with open(mapping_path, "r") as f:
                    labels = [line.strip() for line in f.readlines() if line.strip()]
                print(f"  [{key}] Loaded label mappings: {labels}")
            
            self.label_mappings[key] = labels
            
            # Initialize model architecture
            model = VisionClassifier(backbone, len(labels))
            
            # Load weights if trained
            if os.path.isfile(model_path):
                try:
                    model.load_state_dict(torch.load(model_path, map_location=self.device))
                    model.to(self.device)
                    model.eval()
                    self.models[key] = model
                    print(f"  [{key}] Successfully loaded trained weights from {model_path}")
                except Exception as e:
                    print(f"  [{key}] WARNING: Error loading weights: {e}. Running in un-trained mode.")
                    self.models[key] = None
            else:
                print(f"  [{key}] UNTRAINED (Weights not found: {model_path})")
                self.models[key] = None
                
            # Initialize default baseline result
            self.results[key] = {
                "label": "untrained" if self.models[key] is None else labels[0],
                "confidence": 0.0 if self.models[key] is None else 1.0 / len(labels),
                "all_scores": {lbl: 0.0 for lbl in labels},
                "trained": self.models[key] is not None,
                "enabled": cfg["enabled"]
            }

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.thread.start()
            print("Vision Inference Background Worker Started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            print("Vision Inference Background Worker Stopped.")

    def update_frame(self, frame):
        """Pushes the freshest webcam frame to the processing queue."""
        if not self.frame_queue.full():
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass
        else:
            # Drain queue and insert freshest frame to prevent lag
            try:
                self.frame_queue.get_nowait()
                self.frame_queue.put_nowait(frame)
            except queue.Empty:
                self.frame_queue.put_nowait(frame)

    def get_latest_results(self):
        """Thread-safe retrieval of latest inference metrics."""
        with self.lock:
            return self.results.copy()

    def _worker_loop(self):
        while self.running:
            try:
                # Wait for a new frame (timeout prevents thread getting stuck on stop)
                frame = self.frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Convert BGR frame from OpenCV to RGB PIL Image
            rgb_frame = cv2_to_pil(frame)
            input_tensor = self.transform(rgb_frame).unsqueeze(0).to(self.device)

            # Reload config live in background to catch on-the-fly slider/toggle updates
            try:
                self.load_config()
            except Exception:
                pass

            updated_results = {}
            
            with torch.no_grad():
                for key, model in self.models.items():
                    cfg = self.config["detectors"][key]
                    enabled = cfg["enabled"]
                    temperature = cfg.get("temperature", 1.0)
                    labels = self.label_mappings[key]
                    
                    if not enabled:
                        updated_results[key] = {
                            "label": "disabled",
                            "confidence": 0.0,
                            "all_scores": {lbl: 0.0 for lbl in labels},
                            "trained": model is not None,
                            "enabled": False
                        }
                        continue

                    if model is None:
                        # Graceful untrained baseline representation
                        updated_results[key] = {
                            "label": "Not Trained",
                            "confidence": 0.0,
                            "all_scores": {lbl: 0.0 for lbl in labels},
                            "trained": False,
                            "enabled": True
                        }
                        continue

                    # Run forward pass
                    logits = model(input_tensor)
                    
                    # Apply Softmax Temperature scaling
                    scaled_logits = logits / max(temperature, 0.01)
                    probabilities = torch.softmax(scaled_logits, dim=1).squeeze(0).cpu().numpy()
                    
                    max_idx = np.argmax(probabilities)
                    max_label = labels[max_idx]
                    confidence = float(probabilities[max_idx])
                    
                    all_scores = {labels[i]: float(probabilities[i]) for i in range(len(labels))}

                    updated_results[key] = {
                        "label": max_label,
                        "confidence": confidence,
                        "all_scores": all_scores,
                        "trained": True,
                        "enabled": True
                    }

            # Thread-safe write back
            with self.lock:
                # Retain original keys status but overwrite metrics
                for key, val in updated_results.items():
                    self.results[key] = val


def cv2_to_pil(cv_img):
    """Converts OpenCV BGR image to PIL RGB Image."""
    cv_img_rgb = cv2_img[:, :, ::-1] # BGR to RGB
    return Image.fromarray(cv_img_rgb)
