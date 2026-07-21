import os
import sys
import json
import time

# Force standard output to UTF-8 to handle premium Unicode border characters cleanly on Windows CMD/PowerShell
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header(title):
    print("=" * 72)
    print(f" {title.center(70)}")
    print("=" * 72)

def load_stats():
    registry_path = os.path.join(os.path.dirname(__file__), "..", "models", "training_stats.json")
    if not os.path.exists(registry_path):
        # Create a default structure if not found
        default_stats = {}
        return default_stats
        
    try:
        with open(registry_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading training_stats.json: {e}")
        return {}

def scan_datasets():
    """Scans the local data directory and returns file counts for each category."""
    base_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    categories = ["posture", "eye_contact", "attire", "confidence", "emotions"]
    results = {}
    
    for cat in categories:
        cat_path = os.path.join(base_data_dir, cat)
        if not os.path.exists(cat_path):
            results[cat] = {"ready": False, "train_count": 0, "val_count": 0}
            continue
            
        train_count = 0
        val_count = 0
        
        # Walk directories and count images
        for root, _, files in os.walk(cat_path):
            img_files = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            if "train" in root:
                train_count += len(img_files)
            elif "val" in root:
                val_count += len(img_files)
                
        total = train_count + val_count
        results[cat] = {
            "ready": total > 0,
            "train_count": train_count,
            "val_count": val_count,
            "total": total
        }
    return results

def render_main_matrix(stats, datasets):
    print("\n" + "┌" + "─"*18 + "┬" + "─"*20 + "┬" + "─"*16 + "┬" + "─"*13 + "┐")
    print(f"│ {'Category':<16} │ {'Dataset Status':<18} │ {'Model Status':<14} │ {'Best Acc':<11} │")
    print("├" + "─"*18 + "┼" + "─"*20 + "┼" + "─"*16 + "┼" + "─"*13 + "┤")
    
    for cat in ["posture", "eye_contact", "attire", "confidence", "emotions"]:
        db_stat = stats.get(cat, {})
        ds_info = datasets.get(cat, {"ready": False, "total": 0})
        
        # Format Dataset Status
        if ds_info["ready"]:
            ds_str = f"Ready ({ds_info['total']} samples)"
        else:
            ds_str = "Missing (No images)"
            
        # Format Model Status
        status_raw = db_stat.get("status", "Untrained")
        if "Trained" in status_raw and not status_raw.startswith("Untrained"):
            status_str = "Trained (Local)"
            acc_val = db_stat.get("metrics", {}).get("best_accuracy", 0.0)
            acc_str = f"{acc_val:.1f}%"
        else:
            status_str = "Pre-trained MP"
            acc_str = "MediaPipe"
            
        print(f"│ {cat.capitalize():<16} │ {ds_str:<18} │ {status_str:<14} │ {acc_str:<11} │")
        
    print("└" + "─"*18 + "┴" + "─"*20 + "┴" + "─"*16 + "┴" + "─"*13 + "┘")

def render_model_details(cat, stats, datasets):
    clear_screen()
    print_header(f"KEIKO MODEL PROFILE: {cat.upper()}")
    
    db_stat = stats.get(cat, {})
    ds_info = datasets.get(cat, {"ready": False, "train_count": 0, "val_count": 0, "total": 0})
    
    # 1. Status and Dataset Info
    status_raw = db_stat.get("status", "Untrained")
    is_trained = "Trained" in status_raw and not status_raw.startswith("Untrained")
    
    print(f"\n[+] MODEL METADATA")
    print(f"  Category:             {cat.capitalize()}")
    print(f"  Inference Backbone:   {db_stat.get('hyperparameters', {}).get('backbone', 'resnet18').upper()}")
    print(f"  Execution State:      {status_raw}")
    
    print(f"\n[+] DATASET SPECIFICATIONS")
    ds_details = db_stat.get("dataset_details", {})
    print(f"  Dataset Name:         {ds_details.get('name', 'Keiko Custom Dataset')}")
    print(f"  Local Repository:     data/{cat}")
    print(f"  Source Description:   {ds_details.get('source', 'Offline Curation Mode')}")
    print(f"  Curation Volume:      {ds_info['train_count']} training / {ds_info['val_count']} validation ({ds_info['total']} total)")
    
    # 2. Performance Metrics
    print(f"\n[+] BEST EVALUATION METRICS")
    if is_trained:
        metrics = db_stat.get("metrics", {})
        print(f"  Best Validation Acc:  {metrics.get('best_accuracy', 0.0):.2f}%")
        print(f"  Precision (Weighted): {metrics.get('precision', 0.0):.2f}%")
        print(f"  Recall (Weighted):    {metrics.get('recall', 0.0):.2f}%")
        print(f"  F1-Score (Weighted):  {metrics.get('f1_score', 0.0):.2f}%")
        print(f"  Hyperparameters:      Learning Rate: {db_stat.get('hyperparameters', {}).get('learning_rate', 1e-4)} | Batch Size: {db_stat.get('hyperparameters', {}).get('batch_size', 16)}")
    else:
        print("  - NO CUSTOM TRAINING COMPLETED -")
        print("  Currently running default pre-trained geometric filters & landmarks.")
        
    # 3. Epoch History (Approaches)
    print(f"\n[+] TRAINING APPROACHES HISTORY (EPOCH LOSS & ACCURACY)")
    history = db_stat.get("history", [])
    if history:
        print("\n  ┌───────┬──────────────────────┬──────────────────────┐")
        print("  │ Epoch │    Training Metric   │  Validation Metric   │")
        print("  │       │  Loss   /   Accuracy │  Loss   /   Accuracy │")
        print("  ├───────┼──────────────────────┼──────────────────────┤")
        
        for ep in history:
            epoch = ep.get("epoch", 0)
            t_loss = ep.get("train_loss", 0.0)
            t_acc = ep.get("train_acc", 0.0)
            v_loss = ep.get("val_loss", 0.0)
            v_acc = ep.get("val_acc", 0.0)
            print(f"  │  {epoch:^3}  │  {t_loss:.4f} /  {t_acc:>5.1f}%  │  {v_loss:.4f} /  {v_acc:>5.1f}%  │")
            
        print("  └───────┴──────────────────────┴──────────────────────┘")
    else:
        print("  No validation history logged. Use the Training Pipeline to generate local weights.")
        
    input("\nPress Enter to return to main menu...")

def main():
    while True:
        clear_screen()
        print_header("KEIKO DEEP LEARNING MODEL & DATASET DASHBOARD")
        
        stats = load_stats()
        datasets = scan_datasets()
        
        print("\n[+] CURRENT SYSTEM MATRIX")
        render_main_matrix(stats, datasets)
        
        print("\n[+] SYSTEM CONTROL ACTIONS")
        print("  [1] Download / Curate Local Datasets (Dual-Mode Curation)")
        print("  [2] View Posture Model training details & history")
        print("  [3] View Eye Contact Model training details & history")
        print("  [4] View Attire Model training details & history")
        print("  [5] View Confidence Model training details & history")
        print("  [6] View Emotions Model training details & history")
        print("  [7] Launch PyTorch Model Trainer Pipeline")
        print("  [8] Exit Dashboard")
        
        choice = input("\nSelect an action (1-8): ").strip()
        
        if choice == "1":
            # Run the curation script
            clear_screen()
            print_header("LAUNCHING DUAL-MODE DATASET CURATION MANAGER")
            print("\nInitialising downloader...")
            time.sleep(0.5)
            
            # Execute downloader script using subprocess (immune to Windows space-in-path bugs)
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), "download_datasets.py")
            subprocess.run([sys.executable, script_path])
            
        elif choice in ["2", "3", "4", "5", "6"]:
            cat_map = {
                "2": "posture",
                "3": "eye_contact",
                "4": "attire",
                "5": "confidence",
                "6": "emotions"
            }
            render_model_details(cat_map[choice], stats, datasets)
            
        elif choice == "7":
            # Run PyTorch Model Trainer
            clear_screen()
            print_header("LAUNCHING PYTORCH DETECTOR TRAINING PIPELINE")
            print("\nInitialising trainer...")
            time.sleep(0.5)
            
            # Execute trainer script using subprocess (immune to Windows space-in-path bugs)
            import subprocess
            script_path = os.path.join(os.path.dirname(__file__), "train_detector.py")
            subprocess.run([sys.executable, script_path])
            
        elif choice == "8":
            print("\nExiting Keiko Model Dashboard. Goodbye!")
            time.sleep(0.8)
            break
        else:
            print("\nInvalid choice. Please select a valid menu option.")
            time.sleep(1.0)

if __name__ == "__main__":
    main()
