#!/usr/bin/env python3
"""
Simple ROC Curve Viewer
Opens all generated ROC analysis images
"""

import os
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# Path to ROC analysis folder
ROC_DIR = "roc_analysis"

# Image files to display
images = [
    ("roc_curve.png", "ROC Curve"),
    ("confusion_matrix.png", "Confusion Matrix"),
    ("score_distribution.png", "Score Distribution"),
    ("det_curve.png", "DET Curve")
]

def view_roc_curves():
    """Display all ROC analysis images"""
    print("=" * 80)
    print("ROC CURVE VIEWER")
    print("=" * 80)
    print("\nDisplaying ROC analysis images...")
    print("Close each window to see the next image.\n")
    
    for img_file, title in images:
        img_path = os.path.join(ROC_DIR, img_file)
        
        if not os.path.exists(img_path):
            print(f"⚠️  {img_file} not found!")
            continue
        
        print(f"📊 Showing: {title}")
        
        # Load and display image
        img = mpimg.imread(img_path)
        
        plt.figure(figsize=(12, 8))
        plt.imshow(img)
        plt.axis('off')
        plt.title(title, fontsize=16, fontweight='bold', pad=20)
        plt.tight_layout()
        plt.show()
    
    print("\n✓ All images displayed!")
    print(f"\nImages are saved in: {ROC_DIR}/")
    print("You can also open them directly with any image viewer.")

if __name__ == "__main__":
    view_roc_curves()
