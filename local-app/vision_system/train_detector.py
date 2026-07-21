import os
import sys
import yaml
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models
from collections import defaultdict

def load_config():
    # Dynamically locate config.yaml relative to this script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")
    if not os.path.exists(config_path):
        config_path = "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def compute_real_metrics(model, data_loader, device, num_classes):
    """
    Compute REAL per-class Precision, Recall, F1 from actual model predictions.
    Returns macro-averaged precision, recall, f1 and per-class breakdown.
    """
    model.eval()
    # Confusion matrix: true_positives, false_positives, false_negatives per class
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)

    with torch.no_grad():
        for images, labels in data_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            _, predicted = torch.max(outputs, 1)

            for pred, true in zip(predicted.cpu().numpy(), labels.cpu().numpy()):
                if pred == true:
                    tp[true] += 1
                else:
                    fp[pred] += 1
                    fn[true] += 1

    # Compute per-class precision, recall, f1
    precisions = []
    recalls = []
    f1s = []
    for c in range(num_classes):
        p = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) > 0 else 0.0
        r = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        precisions.append(p)
        recalls.append(r)
        f1s.append(f1)

    # Macro average
    macro_precision = sum(precisions) / num_classes if num_classes > 0 else 0.0
    macro_recall = sum(recalls) / num_classes if num_classes > 0 else 0.0
    macro_f1 = sum(f1s) / num_classes if num_classes > 0 else 0.0

    return macro_precision, macro_recall, macro_f1


def freeze_backbone(model, backbone, unfreeze_last_n=2):
    """
    Freeze all backbone layers EXCEPT the last `unfreeze_last_n` blocks.
    This prevents overfitting by keeping early pretrained features fixed
    and only fine-tuning the higher-level layers + classification head.
    """
    if backbone == "resnet18":
        # ResNet18 has: conv1, bn1, relu, maxpool, layer1, layer2, layer3, layer4, fc
        layers = [model.conv1, model.bn1, model.layer1, model.layer2, model.layer3, model.layer4]
        freeze_count = max(0, len(layers) - unfreeze_last_n)
        for layer in layers[:freeze_count]:
            for param in layer.parameters():
                param.requires_grad = False
        frozen_names = ["conv1+bn1", "layer1", "layer2", "layer3", "layer4"][:freeze_count]
        unfrozen_names = ["conv1+bn1", "layer1", "layer2", "layer3", "layer4"][freeze_count:]
        print(f"  Frozen layers: {frozen_names}")
        print(f"  Trainable layers: {unfrozen_names} + fc")
    else:  # mobilenet_v3
        features = list(model.features)
        freeze_count = max(0, len(features) - unfreeze_last_n)
        for layer in features[:freeze_count]:
            for param in layer.parameters():
                param.requires_grad = False
        print(f"  Frozen: first {freeze_count}/{len(features)} feature blocks")
        print(f"  Trainable: last {len(features) - freeze_count} blocks + classifier")

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  Parameters: {trainable:,} trainable / {total:,} total ({trainable/total*100:.1f}%)")


def check_data_integrity(train_dir, val_dir, classes):
    """
    Check for potential data issues that cause fake-perfect validation scores.
    """
    warnings = []

    # Count images per class
    train_counts = {}
    val_counts = {}
    for cls in classes:
        train_cls_dir = os.path.join(train_dir, cls)
        val_cls_dir = os.path.join(val_dir, cls)
        train_counts[cls] = len(os.listdir(train_cls_dir)) if os.path.exists(train_cls_dir) else 0
        val_counts[cls] = len(os.listdir(val_cls_dir)) if os.path.exists(val_cls_dir) else 0

    total_val = sum(val_counts.values())
    total_train = sum(train_counts.values())

    # Check 1: Very small validation set
    if total_val < 50:
        warnings.append(f"⚠️  Very small validation set ({total_val} images). Results may be unreliable.")

    # Check 2: Validation set too small relative to training
    if total_train > 0 and total_val / total_train < 0.10:
        ratio = total_val / total_train * 100
        warnings.append(f"⚠️  Val set is only {ratio:.0f}% of train set. Recommended: 15-25%.")

    # Check 3: Class imbalance
    if train_counts:
        max_count = max(train_counts.values())
        min_count = min(train_counts.values())
        if max_count > 0 and min_count / max_count < 0.5:
            warnings.append(f"⚠️  Class imbalance detected: {min_count} vs {max_count} images.")

    # Check 4: Val > Train accuracy suggests data leakage
    # (This is checked during training, not here)

    return warnings, train_counts, val_counts


def main():
    print("================================================================")
    print("                 DETECTOR TRAINING PIPELINE")
    print("              (with Anti-Overfitting Measures)")
    print("================================================================")

    # Check CUDA
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using Device: {str(device).upper()}")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
    print("=" * 60)

    try:
        config = load_config()
    except Exception as e:
        print(f"Error loading config.yaml: {e}")
        input("Press Enter to exit...")
        return

    categories = list(config["detectors"].keys())
    print("\nSelect a category to train:")
    for idx, cat in enumerate(categories, 1):
        print(f"  [{idx}] {cat.capitalize()}")
        
    try:
        choice = int(input("\nSelection (number): ").strip())
        category = categories[choice - 1]
    except Exception:
        print("Invalid selection.")
        input("Press Enter to exit...")
        return

    # Dynamically locate the root 'data' directory (outside the vision_system folder)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.abspath(os.path.join(script_dir, "..", "data", category))
    train_dir = os.path.join(data_dir, "train")
    val_dir = os.path.join(data_dir, "val")

    if not os.path.exists(train_dir) or not os.listdir(train_dir):
        print(f"\nERROR: No training data found in {train_dir}!")
        print("Please run the collect_data.py script to capture images first.")
        input("Press Enter to exit...")
        return

    # Automatically scan classes from directory structure
    classes = sorted(os.listdir(train_dir))
    num_classes = len(classes)
    print(f"\nDetected {num_classes} classes: {classes}")

    # Data integrity check
    print("\n--- Data Integrity Check ---")
    warnings, train_counts, val_counts = check_data_integrity(train_dir, val_dir, classes)
    for cls in classes:
        print(f"  {cls}: {train_counts.get(cls, 0)} train / {val_counts.get(cls, 0)} val")
    if warnings:
        print()
        for w in warnings:
            print(f"  {w}")
        print()
    else:
        print("  ✅ Data looks healthy.\n")

    # Settings panel (Interactive customizability)
    print("--- Hyperparameter Settings ---")
    
    # Defaults
    epochs_def = 15
    lr_def = 3e-4
    batch_def = 16
    backbone_def = config["detectors"][category].get("backbone", "resnet18")
    
    epochs_input = input(f"Enter epochs [{epochs_def}]: ").strip()
    epochs = int(epochs_input) if epochs_input else epochs_def
    
    lr_input = input(f"Enter learning rate [{lr_def}]: ").strip()
    lr = float(lr_input) if lr_input else lr_def
    
    batch_input = input(f"Enter batch size [{batch_def}]: ").strip()
    batch_size = int(batch_input) if batch_input else batch_def
    
    backbone_input = input(f"Enter backbone (resnet18/mobilenet_v3) [{backbone_def}]: ").strip().lower()
    backbone = backbone_input if backbone_input in ["resnet18", "mobilenet_v3"] else backbone_def

    # ── Anti-Overfitting: Strong Data Augmentation ──────────────
    train_transform = transforms.Compose([
        transforms.Resize((256, 256)),                              # Resize slightly larger
        transforms.RandomCrop(224),                                 # Random crop to 224
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.3, contrast=0.3,       # Color variation
                               saturation=0.2, hue=0.1),
        transforms.RandomAffine(degrees=10, translate=(0.1, 0.1),  # Spatial jitter
                                scale=(0.85, 1.15)),
        transforms.RandomPerspective(distortion_scale=0.2, p=0.3), # Camera angle sim
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.25, scale=(0.02, 0.2)),       # Occlusion sim
    ])
    
    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    print("\nLoading datasets...")
    train_dataset = datasets.ImageFolder(train_dir, transform=train_transform)
    val_dataset = datasets.ImageFolder(val_dir, transform=val_transform)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    print(f"Total training images: {len(train_dataset)}")
    print(f"Total validation images: {len(val_dataset)}")

    # ── Initialize Model with Dropout ───────────────────────────
    print(f"\nInitializing pre-trained {backbone} model...")
    if backbone == "resnet18":
        model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        in_features = model.fc.in_features
        # Add dropout before the final classification layer
        model.fc = nn.Sequential(
            nn.Dropout(p=0.4),
            nn.Linear(in_features, num_classes)
        )
    else:  # mobilenet_v3
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
        in_features = model.classifier[3].in_features
        # Replace classifier with dropout version
        model.classifier[3] = nn.Sequential(
            nn.Dropout(p=0.4),
            nn.Linear(in_features, num_classes)
        )

    # ── Anti-Overfitting: Freeze Early Backbone Layers ──────────
    print("\n--- Transfer Learning Layer Freezing ---")
    freeze_backbone(model, backbone, unfreeze_last_n=2)

    model = model.to(device)

    # ── Anti-Overfitting: Label Smoothing + Weight Decay ────────
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # ── Anti-Overfitting: Learning Rate Scheduler ───────────────
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', patience=3, factor=0.5, verbose=True
    )

    # ── Anti-Overfitting: Early Stopping ────────────────────────
    early_stop_patience = 5
    early_stop_counter = 0
    best_val_loss = float('inf')

    # Make models folder
    models_dir = os.path.join(script_dir, "..", "models")
    os.makedirs(models_dir, exist_ok=True)
    best_acc = 0.0
    weights_filename = os.path.join(models_dir, f"{category}.pth")
    
    # Initialize history list for tracking epochs
    history = []

    print("\n--- Anti-Overfitting Configuration ---")
    print(f"  Data Augmentation: ColorJitter + RandomAffine + RandomPerspective + RandomErasing + RandomCrop")
    print(f"  Optimizer: AdamW (weight_decay=1e-4)")
    print(f"  Label Smoothing: 0.1")
    print(f"  Dropout: 0.4 (before classifier)")
    print(f"  LR Scheduler: ReduceLROnPlateau (patience=3, factor=0.5)")
    print(f"  Early Stopping: patience={early_stop_patience} epochs")
    print(f"  Backbone Freezing: first layers frozen (transfer learning)")

    print("\nStarting training loop...")
    print("=" * 60)

    leakage_warned = False

    for epoch in range(1, epochs + 1):
        # Training Phase
        model.train()
        running_loss = 0.0
        correct_train = 0
        total_train = 0
        
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            # Gradient clipping to stabilize training
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            
            running_loss += loss.item() * images.size(0)
            _, predicted = torch.max(outputs, 1)
            total_train += labels.size(0)
            correct_train += (predicted == labels).sum().item()

        epoch_loss = running_loss / len(train_dataset)
        epoch_acc = (correct_train / total_train) * 100

        # Validation Phase
        model.eval()
        val_loss = 0.0
        correct_val = 0
        total_val = 0
        
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                
                val_loss += loss.item() * images.size(0)
                _, predicted = torch.max(outputs, 1)
                total_val += labels.size(0)
                correct_val += (predicted == labels).sum().item()

        val_epoch_loss = val_loss / len(val_dataset)
        val_epoch_acc = (correct_val / total_val) * 100

        # Step the LR scheduler based on val loss
        current_lr = optimizer.param_groups[0]['lr']
        scheduler.step(val_epoch_loss)
        new_lr = optimizer.param_groups[0]['lr']

        lr_note = f" [LR: {new_lr:.1e}]" if new_lr != current_lr else ""

        print(f"Epoch [{epoch}/{epochs}] | "
              f"Train Loss: {epoch_loss:.4f} - Acc: {epoch_acc:.1f}% | "
              f"Val Loss: {val_epoch_loss:.4f} - Acc: {val_epoch_acc:.1f}%{lr_note}")

        # Data leakage warning: val acc >> train acc is suspicious
        if val_epoch_acc > epoch_acc + 10 and epoch >= 2 and not leakage_warned:
            print(f"  ⚠️  WARNING: Val acc ({val_epoch_acc:.1f}%) is much higher than train acc ({epoch_acc:.1f}%).")
            print(f"      This often indicates data leakage or a trivially easy validation set.")
            print(f"      Consider reshuffling your train/val split.")
            leakage_warned = True

        # Save weights if we have the best validation loss (not accuracy — more robust)
        if val_epoch_loss < best_val_loss:
            best_val_loss = val_epoch_loss
            best_acc = val_epoch_acc
            torch.save(model.state_dict(), weights_filename)
            print(f"  --> Best model saved! (val_loss={best_val_loss:.4f}, val_acc={best_acc:.2f}%)")
            early_stop_counter = 0
        else:
            early_stop_counter += 1
            if early_stop_counter >= early_stop_patience:
                print(f"\n  ⛔ Early stopping triggered! No improvement for {early_stop_patience} epochs.")
                break

        # Record history
        history.append({
            "epoch": epoch,
            "train_loss": float(f"{epoch_loss:.4f}"),
            "train_acc": float(f"{epoch_acc:.2f}"),
            "val_loss": float(f"{val_epoch_loss:.4f}"),
            "val_acc": float(f"{val_epoch_acc:.2f}"),
            "lr": float(f"{new_lr:.6f}")
        })

    print("=" * 60)
    print(f"\nTraining Complete! Best Val Loss: {best_val_loss:.4f} | Best Val Accuracy: {best_acc:.2f}%")
    print(f"Model saved to: {weights_filename}")
    
    # Save the label mapping
    mapping_file = os.path.join(models_dir, f"{category}_labels.txt")
    with open(mapping_file, "w") as f:
        f.write("\n".join(classes))
    print(f"Label mappings saved to: {mapping_file}")

    # ── Compute REAL Metrics ────────────────────────────────────
    print("\nComputing real Precision/Recall/F1 from validation predictions...")
    
    # Load best model for metric computation
    best_state = torch.load(weights_filename, map_location=device, weights_only=True)
    model.load_state_dict(best_state)
    
    precision, recall, f1 = compute_real_metrics(model, val_loader, device, num_classes)
    
    print(f"  Precision: {precision * 100:.2f}%")
    print(f"  Recall:    {recall * 100:.2f}%")
    print(f"  F1 Score:  {f1 * 100:.2f}%")

    # Save training statistics to training_stats.json registry
    try:
        registry_path = os.path.join(models_dir, "training_stats.json")
        
        # Load existing stats or create fallback
        if os.path.exists(registry_path):
            with open(registry_path, "r") as f:
                stats = json.load(f)
        else:
            stats = {}
            
        if category not in stats:
            stats[category] = {}
            
        # Update details
        stats[category]["status"] = "Trained (Local Model Active)"
        stats[category]["dataset_details"] = {
            "name": f"Keiko Custom {category.capitalize()} Dataset",
            "train_samples": len(train_dataset),
            "val_samples": len(val_dataset),
            "local_path": data_dir,
            "source": f"Locally curated and annotated {category} training split"
        }
        stats[category]["hyperparameters"] = {
            "epochs": epoch,  # actual epochs run (may be less due to early stopping)
            "max_epochs": epochs,
            "learning_rate": lr,
            "batch_size": batch_size,
            "backbone": backbone,
            "weight_decay": 1e-4,
            "label_smoothing": 0.1,
            "dropout": 0.4,
            "early_stopping_patience": early_stop_patience
        }
        
        # REAL metrics computed from actual predictions
        stats[category]["metrics"] = {
            "best_accuracy": float(f"{best_acc:.2f}"),
            "best_val_loss": float(f"{best_val_loss:.4f}"),
            "precision": float(f"{precision * 100:.2f}"),
            "recall": float(f"{recall * 100:.2f}"),
            "f1_score": float(f"{f1 * 100:.2f}"),
            "epochs_run": epoch
        }
        stats[category]["history"] = history
        
        os.makedirs(os.path.dirname(registry_path), exist_ok=True)
        with open(registry_path, "w") as f:
            json.dump(stats, f, indent=2)
        print("\nTraining statistics successfully recorded in models/training_stats.json!")
    except Exception as e:
        print(f"Warning: Could not save training statistics to registry: {e}")

    input("\nPress Enter to return to menu...")

if __name__ == "__main__":
    main()
